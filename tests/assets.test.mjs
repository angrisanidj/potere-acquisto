// Favicon e immagine per i social: i file citati nella testata di index.html devono
// esistere e avere le dimensioni dichiarate.
// Esegui con: node --test tests/assets.test.mjs
// Se un'immagine manca o è vecchia: node scripts/build_images.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';

const file = (f) => new URL(`../${f}`, import.meta.url);
const html = readFileSync(file('index.html'), 'utf8');
const PAGE = 'https://angrisanidj.github.io/potere-acquisto/';
const meta = (prop) => {
  const m = html.match(new RegExp(`<meta (?:property|name)="${prop}" content="([^"]*)">`));
  return m && m[1];
};
// larghezza e altezza dall'intestazione IHDR del PNG
const pngSize = (f) => {
  const b = readFileSync(file(f));
  assert.equal(b.toString('latin1', 1, 4), 'PNG', `${f} non è un PNG`);
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
};

test('favicon: i file citati esistono', () => {
  const links = [...html.matchAll(/<link rel="(?:icon|apple-touch-icon)" href="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(links, ['assets/favicon.svg', 'assets/favicon-32.png', 'assets/apple-touch-icon.png']);
  links.forEach((l) => assert.ok(existsSync(file(l)), `${l} mancante`));
  assert.deepEqual(pngSize('assets/favicon-32.png'), [32, 32]);
  assert.deepEqual(pngSize('assets/apple-touch-icon.png'), [180, 180]);
  assert.match(readFileSync(file('assets/favicon.svg'), 'utf8'), /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" viewBox="0 0 64 64">/);
});

test('immagine per i social: URL assoluto, file presente, 1200 x 630', () => {
  const img = meta('og:image');
  assert.ok(img && img.startsWith(PAGE), `og:image non assoluto: ${img}`);
  const rel = img.slice(PAGE.length);
  assert.ok(existsSync(file(rel)), `${rel} mancante`);
  assert.deepEqual(pngSize(rel), [+meta('og:image:width'), +meta('og:image:height')]);
  assert.deepEqual(pngSize(rel), [1200, 630]);
  assert.equal(meta('og:url'), PAGE);
  assert.equal(meta('twitter:card'), 'summary_large_image');
  for (const p of ['og:title', 'og:description', 'og:image:alt']) assert.ok((meta(p) || '').length > 20, `${p} mancante`);
});
