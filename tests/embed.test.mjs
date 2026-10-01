// Controlla che embed.html sia esattamente il blocco incorporabile di index.html
// (il div radice con stile e script, fino all'ultimo </div> prima di </body>).
// Esegui con: node --test tests/embed.test.mjs
// Se fallisce: python scripts/build_embed.py
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8');
const START = '<div id="fg-potere-acquisto-2026">';

function extract(html) {
  const i = html.indexOf(START);
  assert.ok(i !== -1, 'div radice non trovato in index.html');
  assert.equal(html.indexOf(START, i + 1), -1, 'div radice ripetuto in index.html');
  const bodyEnd = html.lastIndexOf('</body>');
  const j = html.lastIndexOf('</div>', bodyEnd);
  assert.ok(j > i, '</div> di chiusura non trovato');
  return html.slice(i, j + '</div>'.length) + '\n';
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
