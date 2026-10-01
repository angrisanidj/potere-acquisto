// Genera le immagini statiche della pagina con un browser Chromium headless (Edge o
// Chrome) via DevTools Protocol, senza dipendenze:
//   assets/og-image.png        1200 x 630, da assets/og-image.html (anteprima sui social)
//   assets/favicon-32.png      32 x 32, da assets/favicon.svg
//   assets/apple-touch-icon.png 180 x 180, da assets/favicon.svg
// Uso: node scripts/build_images.mjs   (percorso del browser in BROWSER, se serve)
// Si rilancia solo quando cambiano il modello o la favicon.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const ASSETS = join(ROOT, 'assets');
const JOBS = [
  { src: 'og-image.html', out: 'og-image.png', w: 1200, h: 630, transparent: false },
  { src: 'favicon.svg', out: 'favicon-32.png', w: 32, h: 32, transparent: true },
  { src: 'favicon.svg', out: 'apple-touch-icon.png', w: 180, h: 180, transparent: false }
];
const CANDIDATES = [
  process.env.BROWSER,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/microsoft-edge', '/usr/bin/google-chrome', '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
].filter(Boolean);
const browser = CANDIDATES.find((p) => existsSync(p));
if (!browser) { console.error('ERRORE: nessun browser Chromium trovato (imposta BROWSER).'); process.exit(1); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PORT = 9400 + Math.floor(Math.random() * 400);
const profile = mkdtempSync(join(tmpdir(), 'potere-acquisto-img-'));
const proc = spawn(browser, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--hide-scrollbars', '--force-device-scale-factor=1', 'about:blank'], { stdio: 'ignore' });

let ws;
try {
  let targets = [];
  for (let i = 0; i < 60 && !targets.length; i++) {
    try { targets = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).filter((t) => t.type === 'page'); } catch {}
    if (!targets.length) await sleep(250);
  }
  if (!targets.length) throw new Error('il browser non risponde');
  ws = new WebSocket(targets[0].webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.addEventListener('open', r); ws.addEventListener('error', j); });
  let id = 0; const pending = {};
  ws.addEventListener('message', (ev) => { const m = JSON.parse(ev.data); if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; } });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const i = ++id;
    pending[i] = (m) => (m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result));
    ws.send(JSON.stringify({ id: i, method, params }));
  });

  await send('Page.enable');
  for (const job of JOBS) {
    await send('Emulation.setDeviceMetricsOverride', { width: job.w, height: job.h, deviceScaleFactor: 1, mobile: false });
    await send('Emulation.setDefaultBackgroundColorOverride',
      { color: job.transparent ? { r: 0, g: 0, b: 0, a: 0 } : { r: 255, g: 255, b: 255, a: 1 } });
    // L'SVG va dentro una pagina che lo adatta alle dimensioni richieste (incorporato
    // come data URI: una pagina data: non può leggere file locali).
    const svg = job.src.endsWith('.svg') && readFileSync(join(ASSETS, job.src)).toString('base64');
    const url = svg
      ? 'data:text/html,' + encodeURIComponent(`<!doctype html><style>html,body{margin:0;background:transparent}</style>` +
          `<img src="data:image/svg+xml;base64,${svg}" width="${job.w}" height="${job.h}" style="display:block">`)
      : pathToFileURL(join(ASSETS, job.src)).href;
    await send('Page.navigate', { url });
    await sleep(1200);
    const shot = await send('Page.captureScreenshot',
      { format: 'png', clip: { x: 0, y: 0, width: job.w, height: job.h, scale: 1 } });
    const out = join(ASSETS, job.out), tmp = out + '.tmp';
    writeFileSync(tmp, Buffer.from(shot.data, 'base64'));
    renameSync(tmp, out);
    console.log(`${job.out}: ${job.w} x ${job.h}`);
  }
} catch (e) {
  console.error(`ERRORE: ${e.message}`);
  process.exitCode = 1;
} finally {
  if (ws) ws.close();
  proc.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
