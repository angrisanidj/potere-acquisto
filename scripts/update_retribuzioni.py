#!/usr/bin/env python3
"""Scarica dall'API SDMX ISTAT gli indici mensili delle retribuzioni contrattuali
per dipendente, per raggruppamento contrattuale, e li salva in
data/retribuzioni.json.

Solo libreria standard. Riusa da update_foi.py il client HTTP con tentativi e
backoff, così il comportamento in caso di errore è lo stesso.

Individuazione di dataflow e chiave (interrogando i metadati, ottobre 2026)
---------------------------------------------------------------------------
- GET /dataflow/IT1 -> due famiglie di retribuzioni contrattuali mensili:
    155_358_DF_DCSC_RETRATECO1_*  per settore economico ATECO 2007 (382 codici)
    155_318_DF_DCSC_RETRCONTR1C_* per raggruppamento contrattuale (113 codici)
  Si usa la seconda, perché chi usa il calcolatore conosce il proprio contratto
  più che il proprio codice ATECO. Dataflow in base 2021:
  "155_318_DF_DCSC_RETRCONTR1C_4", DSD IT1:DCSC_RETRCONTR1C.
- GET /datastructure/IT1/DCSC_RETRCONTR1C/1.0?references=children -> dimensioni
  FREQ.REF_AREA.DATA_TYPE.ADJUSTMENT.PROF_STATUS_EMP.MAIN_AGREEMENT_GROUP:
    FREQ                 M            = mensile
    REF_AREA             IT           = Italia
    DATA_TYPE            WAGE_E_2021  = indice delle retribuzioni contrattuali
                                        per dipendente, base dicembre 2021=100
                         (WAGE_H_2021 = indice orario, scartato: il calcolatore
                          ragiona su stipendi mensili)
    ADJUSTMENT           N            = dati grezzi
    PROF_STATUS_EMP      10           = totale dipendenti esclusi i dirigenti
    MAIN_AGREEMENT_GROUP Z3620 totale economia, Z2520 settore privato,
                         Z2540 pubblica amministrazione, e via via settori,
                         comparti e raggruppamenti di contratti (codelist
                         IT1:CL_TIPO_CONTRATTO, con gerarchia nel campo parent).
  Chiave usata: M.IT.WAGE_E_2021.N.10. (tutti i raggruppamenti).
- L'API non arriva al singolo CCNL: i codici sono raggruppamenti contrattuali.
  Alcuni coincidono di fatto con un solo contratto (es. Z1960 giornalisti,
  Z0910 gruppo Fiat), ma in generale non sono "il tuo CCNL".

Basi e raccordo
---------------
Esistono quattro dataflow (_3 base 2005, _2 base 2010, _1 base 2015, _4 base
2021), ma partono tutti da gennaio 2005: prima del 2005 l'API non ha dati.
Il dataflow in base 2021 contiene già la serie ricostruita da ISTAT dal 2005.
Controllo fatto: fino a dicembre 2021 il rapporto base2021/base2015 è costante
(totale economia 0,953-0,954, metalmeccanica 0,964-0,965, commercio 0,966-0,967,
con differenze dovute all'arrotondamento a un decimale). Il raccordo è quindi già
applicato da ISTAT e qui non serve alcun coefficiente.
La serie in base 2000 (anni precedenti) esiste solo come file Excel
(dataflow DF_BULK_WAGESACCOR) e senza coefficienti di raccordo ufficiali verso
la base 2021: non viene usata.
Le etichette italiane dei raggruppamenti si ottengono chiedendo la codelist con
"Accept-Language: it".

Validazione
-----------
Come per il FOI: nessun mese mancante, nessun valore <= 0, last_month non
anteriore a quello salvato, nessuna scrittura in caso di errore.
La soglia di variazione mensile del FOI (±5%) non è applicabile ai contratti: i
rinnovi producono scatti veri del 7-35% in un mese (es. trasporto aereo +34,1% ad
aprile 2023) e a dicembre 2023 l'anticipo una tantum nella PA vale +25-38% in un
mese, poi rientra. Soglie usate: ±10% per il totale economia (massimo storico
+4,6%), ±50% per i singoli raggruppamenti (massimo storico +37,6%).
In più, poiché un cambio di base crea un nuovo dataflow e quello vecchio smette
di aggiornarsi, lo script fallisce se l'ultimo mese è più vecchio di 4 mesi.

Picchi temporanei
-----------------
Il campo temporary_peaks elenca, per ogni raggruppamento, i mesi con un aumento
superiore al 3% che rientra di oltre il 3% il mese successivo (oggi solo
dicembre 2023, in 12 raggruppamenti). Con una soglia di salita al 5% sfuggiva il
totale economia (+4,6% e poi -3,7%); fra il 2% e il 4% il risultato non cambia,
quindi la regola non produce falsi positivi sui dati attuali. È ricavato dai dati, non scritto a mano, e serve alla pagina per
non usare un picco una tantum come punto di partenza o di arrivo.
"""

import csv
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

from update_foi import API, UpdateError, http_get, next_month

DATAFLOW = "155_318_DF_DCSC_RETRCONTR1C_4"
DATA_TYPE = "WAGE_E_2021"
KEY = f"M.IT.{DATA_TYPE}.N.10."
CODELIST = "CL_TIPO_CONTRATTO"
TOTAL = "Z3620"

MAX_CHANGE_TOTAL = 0.10
MAX_CHANGE_GROUP = 0.50
MAX_AGE_MONTHS = 4
PEAK_UP, PEAK_DOWN = 0.03, -0.03
# Avviso (non errore) se l'ultimo mese salta oltre questa soglia su questi codici:
# un picco una tantum sull'ultimo mese si riconosce solo col mese successivo.
WARN_JUMP = 0.05
WARN_CODES = {TOTAL: "totale economia", "Z2540": "pubblica amministrazione"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "retribuzioni.json")
FOI = os.path.join(ROOT, "data", "foi.json")

STRUCT = "application/vnd.sdmx.structure+json;version=1.0"


def check_metadata():
    meta = json.loads(http_get(f"{API}/availableconstraint/{DATAFLOW}/all/all/all", STRUCT))
    try:
        kv = meta["data"]["contentConstraints"][0]["cubeRegions"][0]["keyValues"]
    except (KeyError, IndexError) as e:
        raise UpdateError(f"metadati inattesi per {DATAFLOW}: {e}")
    values = {k["id"]: set(k.get("values", [])) for k in kv}
    for dim, code in [("FREQ", "M"), ("REF_AREA", "IT"), ("DATA_TYPE", DATA_TYPE),
                      ("ADJUSTMENT", "N"), ("PROF_STATUS_EMP", "10"),
                      ("MAIN_AGREEMENT_GROUP", TOTAL)]:
        if code not in values.get(dim, set()):
            raise UpdateError(f"il dataflow {DATAFLOW} non contiene {dim}={code}")


def fetch_labels():
    """Etichette italiane e gerarchia dei raggruppamenti contrattuali."""
    url = f"{API}/codelist/IT1/{CODELIST}"
    data = json.loads(http_get(url, STRUCT, {"Accept-Language": "it"}))
    labels = {}
    for c in data["data"]["codelists"][0]["codes"]:
        names = c.get("names") or {}
        labels[c["id"]] = {
            "name": names.get("it") or names.get("en") or c.get("name") or c["id"],
            "parent": c.get("parent"),
        }
    return labels


def fetch_series():
    text = http_get(f"{API}/data/IT1,{DATAFLOW},1.0/{KEY}",
                    "application/vnd.sdmx.data+csv;version=1.0.0")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise UpdateError("risposta dati vuota")
    series = {}
    for r in rows:
        if (r.get("DATA_TYPE"), r.get("REF_AREA"), r.get("ADJUSTMENT"), r.get("PROF_STATUS_EMP")) != (DATA_TYPE, "IT", "N", "10"):
            continue
        month = r["TIME_PERIOD"]
        if len(month) != 7 or month[4] != "-":
            raise UpdateError(f"periodo inatteso: {month}")
        flag = (r.get("OBS_STATUS") or "").strip()
        if flag:
            raise UpdateError(f"osservazione con flag {flag!r} in {r['MAIN_AGREEMENT_GROUP']} {month}")
        try:
            val = float(r["OBS_VALUE"])
        except (TypeError, ValueError):
            raise UpdateError(f"valore non numerico in {r['MAIN_AGREEMENT_GROUP']} {month}")
        series.setdefault(r["MAIN_AGREEMENT_GROUP"], {})[month] = val
    return {c: dict(sorted(s.items())) for c, s in sorted(series.items())}


def months_between(a, b):
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def validate(series, previous):
    if TOTAL not in series:
        raise UpdateError(f"manca il totale economia ({TOTAL})")
    last = max(s and list(s)[-1] for s in series.values())
    for code, s in series.items():
        months = list(s)
        if months[-1] != last:
            raise UpdateError(f"{code}: ultimo mese {months[-1]} diverso da {last}")
        m = months[0]
        for actual in months:
            if actual != m:
                raise UpdateError(f"{code}: mese mancante {m}")
            m = next_month(m)
        limit = MAX_CHANGE_TOTAL if code == TOTAL else MAX_CHANGE_GROUP
        prev = None
        for month, v in s.items():
            if not v > 0:
                raise UpdateError(f"{code}: valore non positivo in {month}: {v}")
            if prev is not None and abs(v / prev - 1) > limit:
                raise UpdateError(f"{code}: variazione anomala in {month}: {100 * (v / prev - 1):+.1f}%")
            prev = v
    if previous and previous.get("last_month") and last < previous["last_month"]:
        raise UpdateError(f"ultimo mese {last} anteriore a quello già salvato {previous['last_month']}")
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    if months_between(last, today) > MAX_AGE_MONTHS:
        raise UpdateError(
            f"ultimo mese {last} più vecchio di {MAX_AGE_MONTHS} mesi: probabile nuova base "
            "in un nuovo dataflow, controllare i metadati ISTAT"
        )
    return last


def temporary_peaks(series):
    peaks = {}
    for code, s in series.items():
        months = list(s)
        for p, q, r in zip(months, months[1:], months[2:]):
            if s[q] / s[p] - 1 > PEAK_UP and s[r] / s[q] - 1 < PEAK_DOWN:
                peaks.setdefault(code, []).append(q)
    return peaks


def nearest_parent(code, labels, series):
    """Primo antenato con dati: es. Z2760 agenzie fiscali -> Z2720 (senza dati)
    -> Z2560 comparti di contrattazione collettiva della PA."""
    p = labels[code]["parent"]
    while p and p not in series:
        p = labels.get(p, {}).get("parent")
    return p


def warn(msg):
    # Sintassi delle annotazioni di GitHub Actions: compare nel riepilogo del run
    # senza far fallire il job.
    print(f"::warning::{msg}")


def emit_warnings(series, peaks, previous, last):
    for code, name in WARN_CODES.items():
        s = series.get(code)
        months = list(s) if s else []
        if len(months) >= 2 and months[-1] == last:
            ch = s[months[-1]] / s[months[-2]] - 1
            if abs(ch) > WARN_JUMP:
                warn(f"Retribuzioni {name} ({code}): {ch * 100:+.1f}% a {last} rispetto al mese prima. "
                     "Potrebbe essere un picco una tantum: si saprà con il mese successivo.")
    if previous is None:
        return
    old = {(c, m) for c, ms in (previous.get("temporary_peaks") or {}).items() for m in ms}
    new = sorted((c, m) for c, ms in peaks.items() for m in ms if (c, m) not in old)
    for c, m in new:
        warn(f"Nuovo picco temporaneo nelle retribuzioni: {c} a {m}. La pagina userà il mese precedente.")


def write_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(obj)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def dump(out):
    """JSON leggibile ma compatto: una riga per serie (circa 200 KB invece di 600)."""
    head = {k: v for k, v in out.items() if k != "series"}
    text = json.dumps(head, ensure_ascii=False, indent=1)[:-2]
    lines = []
    for code, s in out["series"].items():
        lines.append(f' {json.dumps(code)}: {{"start": {json.dumps(s["start"])}, '
                     f'"values": {json.dumps(s["values"])}}}')
    return text + ',\n "series": {\n' + ",\n".join(lines) + "\n }\n}\n"


def main():
    previous = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            previous = json.load(f)

    print(f"Metadati {DATAFLOW}...")
    check_metadata()
    print(f"Etichette {CODELIST}...")
    labels = fetch_labels()
    print(f"Dati {KEY}...")
    series = fetch_series()
    last = validate(series, previous)

    unknown = [c for c in series if c not in labels]
    if unknown:
        raise UpdateError(f"codici senza etichetta nella codelist: {unknown}")

    first = min(list(s)[0] for s in series.values())
    comparti = [
        {"code": c, "name": labels[c]["name"], "parent": nearest_parent(c, labels, series),
         "first_month": list(s)[0]}
        for c, s in series.items()
    ]
    peaks = temporary_peaks(series)
    out = {
        "source": "ISTAT - Indici delle retribuzioni contrattuali per dipendente, "
                  f"API SDMX {API}, dataflow IT1:{DATAFLOW}, chiave {KEY}",
        "index": "Retribuzioni contrattuali per dipendente (esclusi i dirigenti), "
                 "per raggruppamento contrattuale, Italia, mensile, dati grezzi",
        "base_note": "Base dicembre 2021=100. Serie ricostruita da ISTAT dal gennaio 2005, già "
                     "raccordata con le basi precedenti. L'indice misura le retribuzioni "
                     "previste dai contratti (minimi tabellari e voci contrattuali), non "
                     "anzianità, superminimi e promozioni.",
        "first_month": first,
        "last_month": last,
        "last_checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_code": TOTAL,
        "comparti": comparti,
        "temporary_peaks": peaks,
        "series": {c: {"start": list(s)[0], "values": list(s.values())} for c, s in series.items()},
    }
    text = dump(out)
    if json.loads(text) != out:  # il testo deve rileggersi identico prima di scriverlo
        raise UpdateError("serializzazione JSON non coerente")
    write_atomic(OUT, text)
    emit_warnings(series, peaks, previous, last)

    changed = previous is None or previous.get("series") != out["series"]
    tot = series[TOTAL]
    print(f"Scritto {os.path.relpath(OUT, ROOT)} ({'serie aggiornate' if changed else 'serie invariate'})")
    print(f"Primo mese: {first}")
    print(f"Ultimo mese: {last}")
    print(f"Raggruppamenti: {len(series)}")
    if "2021-01" in tot:
        print(f"Totale economia {last}/2021-01: {100 * (tot[last] / tot['2021-01'] - 1):+.1f}%")
    if out["temporary_peaks"]:
        months = sorted({m for v in out["temporary_peaks"].values() for m in v})
        print(f"Picchi temporanei: {', '.join(months)} ({len(out['temporary_peaks'])} raggruppamenti)")
    if os.path.exists(FOI):
        with open(FOI, encoding="utf-8") as f:
            foi_last = json.load(f).get("last_month")
        if foi_last:
            print(f"Ultimo mese comune con il FOI: {min(foi_last, last)}")


if __name__ == "__main__":
    try:
        main()
    except UpdateError as e:
        print(f"ERRORE: {e}. data/retribuzioni.json NON modificato.", file=sys.stderr)
        sys.exit(1)
