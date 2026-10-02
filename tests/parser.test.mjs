// Test del parser degli importi in formato italiano.
// Esegui con: node --test tests/parser.test.mjs
// Il parser viene estratto da index.html (blocco tra "parser-start" e
// "parser-end"), così si testa esattamente il codice pubblicato.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const block = html.match(/\/\/ --- parser-start ---([\s\S]*?)\/\/ --- parser-end ---/);
assert.ok(block, 'blocco del parser non trovato in index.html');
const { parseImporto, formatImporto } = new Function(block[1] + '\nreturn { parseImporto, formatImporto };')();

const ok = (input, expected, opts) => {
  const r = parseImporto(input, opts);
  assert.equal(r.ok, true, `"${input}" dovrebbe essere valido, errore: ${r.error}`);
  assert.equal(r.value, expected, `"${input}"`);
};
const ko = (input, opts, pattern) => {
  const r = parseImporto(input, opts);
  assert.equal(r.ok, false, `"${input}" dovrebbe essere rifiutato, ottenuto ${r.value}`);
  assert.equal(typeof r.error, 'string');
  assert.ok(r.error.length > 10, 'messaggio troppo corto');
  if (pattern) assert.match(r.error, pattern);
};

test('esempi del brief', () => {
  ok('1.500', 1500);
  ok('1.500,50', 1500.5);
  ok('2.500.000', 2500000, { lire: true });
});

test('importi validi in euro', () => {
  ok('1500', 1500);
  ok('1500,5', 1500.5);
  ok('1,5', 1.5);
  ok('0,50', 0.5);
  ok('999', 999);
  ok('12.345,67', 12345.67);
  ok('  1.500  ', 1500);
  ok('€ 1.500', 1500);
  ok('1.500 €', 1500);
  ok('1.500 €', 1500);
  ok('1.000.000', 1000000);
});

test('importi validi in lire', () => {
  ok('2500000', 2500000, { lire: true });
  ok('1.800.000', 1800000, { lire: true });
  ok('1.800.000 lire', 1800000, { lire: true });
  ok('50.000', 50000, { lire: true });
});

test('forme ambigue rifiutate', () => {
  ko('1.50', null, /ambiguo/i);
  ko('1.5', null, /ambiguo/i);
  ko('1,500', null, /ambiguo/i);
  ko('2,500000', null, /ambiguo/i);
  ko('1,5000', null, /ambiguo/i);
});

test('formato inglese o separatori malformati rifiutati', () => {
  ko('1,500.50', null, /punto/i);
  ko('1.500.00', null, /tre cifre/i);
  ko('15.00.000', null, /tre cifre/i);
  ko('1500.000', null, /tre cifre/i);
  ko('.500', null, /tre cifre/i);
  ko('1.', null, /tre cifre/i);
  ko('1,5,0', null, /virgola/i);
  ko('1.500,', null, /dopo la virgola/i);
  ko(',50', null, /parte intera/i);
  ko('1 500', null, /spazi/i);
});

test('input non numerici rifiutati', () => {
  ko('', null, /inserisci/i);
  ko('   ', null, /inserisci/i);
  ko(null, null, /inserisci/i);
  ko('abc', null, /non valido/i);
  ko('1.500a', null, /non valido/i);
  ko('1e3', null, /non valido/i);
  ko('mille', null, /non valido/i);
  ko('$1500', null, /non valido/i);
});

test('zero e negativi rifiutati', () => {
  ko('0', null, /maggiore di zero/i);
  ko('0,00', null, /maggiore di zero/i);
  ko('-1500', null, /maggiore di zero/i);
  ko('−1.500', null, /maggiore di zero/i);
});

test('controlli di plausibilità', () => {
  ko('1.000.001', null, /troppo alto/i);
  ko('2.500,50', { lire: true }, /decimali/i);
  ko('1.500', { lire: true }, /in lire/i);
  ko('3.000.000.000', { lire: true }, /troppo alto/i);
});

test('formattazione all\'uscita dal campo: punto delle migliaia anche sotto 10.000', () => {
  assert.equal(formatImporto(60000), '60.000');
  assert.equal(formatImporto(1500), '1.500');
  assert.equal(formatImporto(1500.5), '1.500,50');
  assert.equal(formatImporto(1500.05), '1.500,05');
  assert.equal(formatImporto(999), '999');
  assert.equal(formatImporto(0.5), '0,50');
  assert.equal(formatImporto(1234567.89), '1.234.567,89');
  assert.equal(formatImporto(2500000, true), '2.500.000');
  assert.equal(formatImporto(1500000, true), '1.500.000');
});

test('formattazione: l\'importo scritto dall\'utente diventa quello formattato', () => {
  const blur = (raw, lire) => { const r = parseImporto(raw, { lire }); return r.ok ? formatImporto(r.value, lire) : raw; };
  assert.equal(blur('60000'), '60.000');
  assert.equal(blur('1500'), '1.500');
  assert.equal(blur('1500,5'), '1.500,50');
  assert.equal(blur('1.500'), '1.500');
  assert.equal(blur('€ 1500'), '1.500');
  assert.equal(blur('2500000', true), '2.500.000');
  // importi non validi restano come sono, con il loro messaggio d'errore
  assert.equal(blur('1.50'), '1.50');
  assert.equal(blur('abc'), 'abc');
});

test('formattazione: il risultato è sempre riletto uguale', () => {
  for (const v of [1, 9.99, 10, 999, 1000, 1500.5, 9999.99, 10000, 26000, 45000.1, 999999.99]) {
    const r = parseImporto(formatImporto(v));
    assert.equal(r.ok, true, `${v} → ${formatImporto(v)}: ${r.error}`);
    assert.equal(r.value, v);
  }
  for (const v of [50000, 1500000, 2500000, 999999999]) {
    const r = parseImporto(formatImporto(v, true), { lire: true });
    assert.equal(r.ok, true, `${v} lire: ${r.error}`);
    assert.equal(r.value, v);
  }
});

test('formattazione solo sui campi d\'importo', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  // i soli campi formattati sono i quattro importi; gli anni e i mesi sono menu
  // una definizione e due chiamate: importi del calcolo e importi del blocco retribuzione
  assert.equal((html.match(/formatField\(/g) || []).length, 3);
  assert.match(html, /\[el\.ralIn, el\.premiIn\]\.forEach\(function \(inp\) \{[\s\S]{0,400}formatField\(inp, false\)/);
  assert.match(html, /\[el\.sal0, el\.sal1\]\.forEach\(function \(inp\) \{[\s\S]{0,400}formatField\(inp, inp === el\.sal0/);
  for (const id of ['sal0', 'sal1', 'ral-in', 'premi-in']) {
    assert.match(html, new RegExp(`data-fg="${id}" type="text" inputmode="decimal"`), `${id}: inputmode`);
  }
  assert.match(html, /el\.sal0\.setAttribute\('inputmode', lire \? 'numeric' : 'decimal'\)/);
});
