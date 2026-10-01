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
const parseImporto = new Function(block[1] + '\nreturn parseImporto;')();

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
