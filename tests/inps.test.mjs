// Test delle funzioni sulle distribuzioni INPS (percentile e quantili per classi).
// Esegui con: node --test tests/inps.test.mjs
// Le funzioni vengono estratte da index.html (blocco tra "inps-start" e
// "inps-end") e provate sui dati veri di data/inps.json.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const block = html.match(/\/\/ --- inps-start ---([\s\S]*?)\/\/ --- inps-end ---/);
assert.ok(block, 'blocco INPS non trovato in index.html');
const { inpsDist, inpsPercentile, inpsQuantile, inpsPctText, inpsGap } = new Function(
  block[1] + '\nreturn { inpsDist, inpsPercentile, inpsQuantile, inpsPctText, inpsGap };')();
const INPS = JSON.parse(readFileSync(new URL('../data/inps.json', import.meta.url), 'utf8'));
const dist = (entry) => inpsDist(INPS.classes, entry);
const near = (a, b, eps, msg) => assert.ok(Math.abs(a - b) < eps, `${msg}: ${a} invece di ${b}`);

test('totali nazionali verificati con l\'export manuale', () => {
  assert.equal(dist(INPS.italia.Operaio).total, 3244096);
  assert.equal(dist(INPS.italia.Impiegato).total, 3169824);
  assert.equal(dist(INPS.italia.Quadro).total, 475121);
  assert.equal(dist(INPS.italia.Dirigente).total, 122796);
});

test('ogni combinazione con dati ha un totale uguale alla somma delle classi pubblicate', () => {
  let n = 0;
  const check = (e) => {
    if (!e || e.non_disponibile) return;
    const d = dist(e);
    assert.ok(d, `soglia non riconosciuta: ${e.soglia}`);
    assert.equal(d.total, e.total);
    n++;
  };
  Object.values(INPS.italia).forEach(check);
  for (const g of ['sezioni', 'regioni']) {
    for (const v of Object.values(INPS[g])) { check(v.tutte); Object.values(v.quals).forEach(check); }
  }
  assert.ok(n >= 151, `combinazioni con dati: ${n}`);
});

test('combinazioni non disponibili e soglie sconosciute', () => {
  assert.equal(dist(INPS.sezioni.D.quals.Operaio), null);
  assert.equal(dist(undefined), null);
  assert.equal(dist({ soglia: 'boh', counts: { '5000-9999': 1 } }), null);
});

test('percentile per interpolazione lineare nella classe', () => {
  const e = { soglia: 'nessuna', counts: { '20000-24999': 50, '25000-29999': 50 } };
  const d = dist(e);
  near(inpsPercentile(d, 22500).p, 0.25, 1e-9, 'metà della prima classe');
  near(inpsPercentile(d, 25000).p, 0.5, 1e-9, 'confine fra le classi');
  near(inpsPercentile(d, 30000).p, 1, 1e-9, 'oltre l\'ultima classe piena');
  near(inpsQuantile(d, 0.5).v, 25000, 1e-9, 'mediana');
  near(inpsQuantile(d, 0.75).v, 27500, 1e-9, '3° quartile');
});

test('quantile e percentile sono l\'uno l\'inverso dell\'altro', () => {
  const d = dist(INPS.sezioni.G.quals.Operaio);
  for (const q of [0.1, 0.25, 0.5, 0.75, 0.9]) {
    const v = inpsQuantile(d, q).v;
    near(inpsPercentile(d, v).p, q, 1e-9, `q=${q}`);
  }
});

test('classe aperta: niente stima oltre 80.000 €', () => {
  const d = dist(INPS.italia.Dirigente);
  const r = inpsPercentile(d, 120000);
  assert.equal(r.open, true);
  near(r.p, 1 - 114501 / 122796, 1e-12, 'quota sotto la classe aperta');
  assert.equal(inpsQuantile(d, 0.5).open, true);
  const nobody = dist({ soglia: 'nessuna', counts: { '20000-24999': 10 } });
  assert.deepEqual(inpsPercentile(nobody, 90000), { p: 1 });
});

test('soglie: il percentile riguarda solo le classi pubblicate', () => {
  const quadri = dist(INPS.sezioni.G.quals.Quadro);   // da 20.000
  assert.equal(quadri.from, 20000);
  assert.deepEqual(inpsPercentile(quadri, 18000), { out: true });
  assert.equal(inpsPercentile(quadri, 20000).p, 0);
  const imp = dist(INPS.sezioni.K.quals.Impiegato);    // esclusa 5000-9999
  assert.equal(imp.skipped.label, '5000-9999');
  assert.deepEqual(inpsPercentile(imp, 7000), { out: true });
  assert.ok(inpsPercentile(imp, 12000).p > 0);
});

test('testo del percentile: 5 punti con "circa", estremi e classe aperta', () => {
  const t = (P) => { const r = inpsPctText(P); return r && r.pre + r.num; };
  assert.equal(t({ p: 0.4219 }), 'circa il 40%');
  assert.equal(t({ p: 0.4251 }), 'circa il 45%');
  assert.equal(t({ p: 0.79 }), 'circa l’80%');
  assert.equal(t({ p: 0.02 }), 'meno del 5%');
  assert.equal(t({ p: 0.98 }), 'più del 95%');
  assert.equal(t({ open: true, p: 0.69 }), 'oltre il 65%');
  assert.equal(t({ open: true, p: 0.83 }), 'oltre l’80%');
  assert.equal(inpsGap(26000, 27033.7), '−4%');
  assert.equal(inpsGap(30000, 30040), '0%');
  assert.equal(inpsGap(33600, 30000), '+12%');
});

// I tre esempi di controllo con coefficiente 1,0: RAL già in valori dell'anno INPS,
// così il risultato non cambia con l'indice mensile.
test('i tre esempi di controllo, coefficiente 1,0', () => {
  const ex = (entry, x) => {
    const d = dist(entry), T = inpsPctText(inpsPercentile(d, x));
    return [T.pre + T.num, inpsGap(x, inpsQuantile(d, 0.5).v)];
  };
  assert.deepEqual(ex(INPS.sezioni.G.quals.Operaio, 26000), ['circa il 40%', '−4%']);
  assert.deepEqual(ex(INPS.regioni.Lombardia.quals.Operaio, 26000), ['circa il 30%', '−11%']);
  assert.deepEqual(ex(INPS.sezioni.K.quals.Impiegato, 45000), ['circa il 50%', '−1%']);
  assert.deepEqual(ex(INPS.sezioni.C.quals.Quadro, 70000), ['circa il 40%', '−8%']);
});

// Istruzione e sanità: l'indice di sezione comprende i contratti pubblici, quindi
// indice_ateco.json indica l'indice da usare al suo posto ("use").
test('coefficienti: sezioni P e Q con un indice del solo privato', () => {
  const IDX = JSON.parse(readFileSync(new URL('../data/indice_ateco.json', import.meta.url), 'utf8'));
  assert.deepEqual(IDX.use, { P: 'Z2360', Q: IDX.total_code });
  for (const code of Object.values(IDX.use)) {
    assert.ok(IDX.factors[code] > 0.9 && IDX.factors[code] < 1.6, `coefficiente di ${code}: ${IDX.factors[code]}`);
  }
});
