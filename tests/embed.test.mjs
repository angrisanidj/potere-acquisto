// Controlla che embed.html sia esattamente il blocco incorporabile di index.html
// (il div radice con stile e script, fino al </div> che lo chiude) e che non
// contenga ciò che vale solo per la pagina autonoma, come la barra di condivisione.
// Esegui con: node --test tests/embed.test.mjs
// Se fallisce: python scripts/build_embed.py
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8');
const START = '<div id="fg-potere-acquisto-2026">';

// Stessa regola di scripts/build_embed.py: si contano i div annidati, saltando
// commenti, <style> e <script>.
function extract(html) {
  const i = html.indexOf(START);
  assert.ok(i !== -1, 'div radice non trovato in index.html');
  assert.equal(html.indexOf(START, i + 1), -1, 'div radice ripetuto in index.html');
  const token = /<!--[\s\S]*?-->|<(script|style)\b[^>]*>[\s\S]*?<\/\1>|<div\b[^>]*>|<\/div\s*>/gi;
  token.lastIndex = i;
  let depth = 0, m;
  while ((m = token.exec(html))) {
    if (m[0].startsWith('<!--') || m[1]) continue;
    depth += m[0].startsWith('</') ? -1 : 1;
    if (depth === 0) return html.slice(i, m.index + m[0].length) + '\n';
  }
  assert.fail('</div> di chiusura del div radice non trovato');
}

test('embed.html coincide con il blocco di index.html', () => {
  const expected = extract(read('index.html'));
  const embed = read('embed.html');
  if (embed === expected) return;
  const a = embed.split('\n'), b = expected.split('\n');
  let k = 0;
  while (k < a.length && a[k] === b[k]) k++;
  assert.fail('embed.html non è aggiornato: rilancia "python scripts/build_embed.py" ' +
    `(prima differenza alla riga ${k + 1} di embed.html)`);
});

test('embed.html è un blocco autonomo da incollare', () => {
  const embed = read('embed.html');
  assert.ok(embed.startsWith(START));
  assert.ok(embed.endsWith('</div>\n'));
  for (const tag of ['style', 'script']) {
    assert.equal(embed.split(`<${tag}>`).length - 1, 1, `un solo <${tag}>`);
    assert.equal(embed.split(`</${tag}>`).length - 1, 1, `un solo </${tag}>`);
  }
  for (const t of ['<html', '<head>', '<body', '<!DOCTYPE']) assert.ok(!embed.includes(t), `contiene ${t}`);
  // i dati vengono dagli URL assoluti di GitHub Pages
  for (const f of ['foi', 'retribuzioni', 'inps', 'indice_ateco']) {
    assert.ok(embed.includes(`'https://angrisanidj.github.io/potere-acquisto/data/${f}.json'`), `URL di ${f}.json`);
  }
});

// Ogni selettore del CSS deve iniziare con l'ID radice: niente regole su html, body,
// *, :root o tag da soli, che altererebbero la pagina che ospita il calcolatore.
test('ogni selettore CSS inizia con l\'ID radice', () => {
  const embed = read('embed.html');
  const css = embed.slice(embed.indexOf('<style>') + 7, embed.indexOf('</style>')).replace(/\/\*[\s\S]*?\*\//g, '');
  const ROOT = '#fg-potere-acquisto-2026';
  const selectors = [];
  // Scorre il CSS: le regole @media vengono aperte, le altre @-regole sono vietate.
  (function walk(s) {
    let i = 0;
    while (i < s.length) {
      const open = s.indexOf('{', i);
      if (open === -1) { assert.equal(s.slice(i).trim(), '', 'testo CSS fuori da una regola'); return; }
      const head = s.slice(i, open).trim();
      let depth = 1, j = open + 1;
      while (depth) { if (s[j] === '{') depth++; else if (s[j] === '}') depth--; j++; }
      const body = s.slice(open + 1, j - 1);
      if (head.startsWith('@')) {
        assert.match(head, /^@media\b/, `@-regola non ammessa: ${head}`);
        walk(body);
      } else {
        head.split(',').forEach((x) => selectors.push(x.trim().replace(/\s+/g, ' ')));
      }
      i = j;
    }
  })(css);
  assert.ok(selectors.length > 100, `selettori trovati: ${selectors.length}`);
  const bad = selectors.filter((x) => !(x === ROOT || (x.startsWith(ROOT) && /^[\s.:[>+~]/.test(x.slice(ROOT.length)))));
  assert.deepEqual(bad, [], 'selettori che non iniziano con l\'ID radice');
});

test('la barra di condivisione è solo nella pagina autonoma', () => {
  const html = read('index.html'), embed = read('embed.html');
  for (const t of ['pa-condividi', 'SHARE_ICONS', 'Condividi', 'intent/post', 'sharer.php', 'wa.me']) {
    assert.ok(!embed.includes(t), `embed.html contiene ${t}`);
  }
  // nella pagina c'è, dopo il blocco e fuori da esso, con stile e script propri
  const aside = html.indexOf('<aside id="pa-condividi"');
  assert.ok(aside > html.indexOf(START) + embed.length - 1, 'barra non dopo il blocco');
  const css = html.slice(html.indexOf('<style>', aside) + 7, html.indexOf('</style>', aside)).replace(/\/\*[\s\S]*?\*\//g, '');
  const sel = css.replace(/@media[^{]*\{/g, '').split('}').map((r) => r.split('{')[0].trim()).filter(Boolean)
    .flatMap((h) => h.split(',').map((x) => x.trim()));
  assert.ok(sel.length > 10);
  assert.deepEqual(sel.filter((x) => !/^#pa-(condividi|pagina)\b/.test(x)), [], 'selettori della barra fuori dai suoi ID');
  assert.match(html, /@media \(min-width: 900px\)[\s\S]*position: sticky/);
});

// Il pulsante del PNG deve esserci e non stare dentro un elemento nascosto: prima
// era nella sezione del grafico, nascosta finché non si inserisce lo stipendio.
test('pulsante PNG presente e visibile', () => {
  for (const f of ['index.html', 'embed.html']) {
    const doc = read(f);
    const i = doc.indexOf(START);
    const markup = doc.slice(i).replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, '').replace(/<!--[\s\S]*?-->/g, '');
    const VOID = /^(input|br|img|hr|meta|link|source|wbr)$/i;
    const stack = [];
    const tag = /<(\/?)([a-z][a-z0-9]*)\b([^>]*)>/gi;
    let m, found = null;
    while ((m = tag.exec(markup))) {
      const [, close, name, attrs] = m;
      if (close) { stack.pop(); continue; }
      if (/data-fg="png"/.test(attrs)) { found = { name, attrs, ancestors: stack.slice() }; break; }
      if (!VOID.test(name) && !attrs.trim().endsWith('/')) stack.push({ name, attrs });
    }
    assert.ok(found, `${f}: pulsante PNG assente`);
    assert.equal(found.name.toLowerCase(), 'button');
    assert.match(read('index.html'), /Scarica l’immagine \(PNG\)/);
    // l'unico antenato nascosto ammesso è il contenitore del calcolatore, mostrato a dati caricati
    const hidden = found.ancestors.filter((a) => !/data-fg="app"/.test(a.attrs))
      .filter((a) => /(^|\s)hidden(\s|=|$)/.test(a.attrs) || /display:\s*none/.test(a.attrs));
    assert.deepEqual(hidden.map((a) => a.attrs.trim()), [], `${f}: pulsante dentro un elemento nascosto`);
    assert.ok(!/(^|\s)hidden(\s|=|$)/.test(found.attrs), `${f}: pulsante nascosto`);
  }
  const css = read('embed.html').match(/<style>([\s\S]*?)<\/style>/)[1];
  for (const cls of ['fg-btn', 'fg-actions']) {
    const rules = [...css.matchAll(new RegExp(`[^}]*\\.${cls}\\b[^{]*\\{([^}]*)\\}`, 'g'))].map((x) => x[1]);
    assert.ok(rules.length, `regole per .${cls}`);
    rules.forEach((r) => assert.ok(!/display:\s*none|visibility:\s*hidden|opacity:\s*0[;\s]/.test(r), `.${cls} nascosto: ${r}`));
  }
  assert.match(read('index.html'), /el\.app\.hidden = false;/);
  // nel codice il pulsante si disattiva ma non si nasconde mai
  assert.ok(!/el\.png\.hidden|png-box'\)\.hidden|pngBox\.hidden/.test(read('index.html')));
});

test('note a comparsa, chiuse di default', () => {
  const embed = read('embed.html');
  const notes = embed.slice(embed.indexOf('<div class="fg-notes">'), embed.indexOf('</div>', embed.indexOf('<div class="fg-notes">')));
  const det = [...notes.matchAll(/<details class="fg-det"( open)?><summary>([^<]+)<\/summary>/g)];
  assert.deepEqual(det.map((d) => d[2]), ['Metodo', 'Contratto', 'Retribuzione']);
  assert.ok(det.every((d) => !d[1]), 'una nota è aperta di default');
  // note del blocco retribuzione, generate dallo script
  const titles = [...embed.matchAll(/det\('([^']+)', '/g)].map((d) => d[1]);
  assert.deepEqual(titles, ['Fonte', 'Cosa misura', 'Calcolo', 'Aggiornamento', 'Dati mancanti', 'Pubblica amministrazione']);
  assert.ok(!/\.open\s*=\s*true|setAttribute\('open'/.test(embed), 'una nota si apre da sola');
});
