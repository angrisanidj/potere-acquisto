#!/usr/bin/env python3
"""Scarica da Eurostat la retribuzione media annua per grande gruppo professionale
(ISCO-08 a una cifra) e sezione NACE dall'indagine sulla struttura delle
retribuzioni (SES), Italia, e i coefficienti per portarla all'ultimo mese con
l'indice ISTAT delle retribuzioni contrattuali per sezione. Scrive data/ses.json.

Solo libreria standard; client HTTP e tentativi da update_foi.py (il limite di
40 s fra le richieste vale solo per l'API ISTAT).

Fonti (verificate, ottobre 2026)
-------------------------------
Eurostat earn_ses22_49 "Mean annual earnings by sex, occupation and economic
activity (2022)", API https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data
  - filtri: geo=IT, sex=T, indic_se=ERN (retribuzione lorda), unit=EUR,
    sizeclas=GE10 (per l'Italia l'unica classe: unita' con almeno 10 dipendenti);
  - isco08: OC1 dirigenti, OC2 professioni intellettuali, OC3 tecniche,
    OC4 impiegati d'ufficio, OC5 vendite e servizi, OC7 artigiani e operai
    specializzati, OC8 conduttori di impianti, OC9 professioni elementari
    (pubblicati solo a una cifra; OC6 agricoltori e OC0 forze armate esclusi);
  - nace_r2: sezioni B-S e B-S_X_O (totale escluse le amministrazioni pubbliche);
  - la media annua include tredicesima, quattordicesima e premi; il totale B-S
    (37.302 euro) coincide con il dato ISTAT "ricondotto ad anno intero e tempo
    pieno" (ISTAT, La struttura delle retribuzioni in Italia, anno 2022).
  Riutilizzo: dati Eurostat riutilizzabili citando la fonte (Decisione 2011/833/UE).
Indice ISTAT delle retribuzioni contrattuali per ATECO, 155_358_DF_DCSC_RETRATECO1_7,
  chiave M.IT.WAGE_E_2021.N.10., sezioni B-S e 0015 (industria e servizi di
  mercato) per il totale, come per RACLI.

Regole
------
- Coefficiente = indice dell'ultimo mese / media dell'indice nell'anno SES; i mesi
  di picco temporaneo (oltre +3% che rientra di oltre il 3%) sono sostituiti dal
  mese precedente.
- Le celle gruppo x sezione vuote restano assenti: la pagina usa il totale
  B-S_X_O del gruppo e lo dichiara.
- L'indagine e' quadriennale: ogni mese lo script controlla se esiste la tavola
  dell'edizione successiva (earn_ses26_49 ...) e, se c'e', lo segnala con
  ::warning:: senza cambiarla da solo. In piu', indipendentemente dal nome della
  tavola, dopo il 30 giugno dell'anno SES + 7 (2029 per i dati 2022) chiede una
  verifica a mano.
"""

import csv
import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone

from update_foi import API, UpdateError, http_get

EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
SES_YEAR = "2022"
TABLE = f"earn_ses{SES_YEAR[2:]}_49"
GROUPS = ["OC1", "OC2", "OC3", "OC4", "OC5", "OC7", "OC8", "OC9"]
TOTAL = "B-S_X_O"
TOTAL_INDEX = "0015"
SECTIONS = list("BCDEFGHIJKLMNPQRS")
INDEX = "155_358_DF_DCSC_RETRATECO1_7"
KEY_INDEX = "M.IT.WAGE_E_2021.N.10."
MIN_CELLS = 100
VALUE_RANGE = (10000, 400000)
FACTOR_RANGE = (0.9, 1.8)
PEAK_UP, PEAK_DOWN = 0.03, -0.03
# Controllo indipendente dal nome della tavola: l'edizione successiva (anno + 4)
# dovrebbe essere pubblicata entro circa 3 anni; oltre questa data (30 giugno
# 2029 per i dati 2022) si chiede una verifica a mano su Eurostat.
EDITION_DEADLINE = f"{int(SES_YEAR) + 7}-06-30"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "ses.json")


def warn(msg):
    print(f"::warning::{msg}")


def jsonstat_cells(data, fixed):
    """Valori della tavola JSON-stat con le dimensioni in `fixed` bloccate."""
    ids = data["id"]
    idx = {k: data["dimension"][k]["category"]["index"] for k in ids}
    size = {k: len(idx[k]) for k in ids}
    for k, v in fixed.items():
        if v not in idx.get(k, {}):
            raise UpdateError(f"{TABLE}: la dimensione {k} non contiene {v}")
    free = [k for k in ids if k not in fixed]
    out = {}

    def walk(i, sel):
        if i == len(free):
            pos = 0
            for k in ids:
                pos = pos * size[k] + idx[k][sel[k]]
            v = data["value"].get(str(pos))
            if v is not None:
                out[tuple(sel[k] for k in free)] = v
            return
        for code in idx[free[i]]:
            sel[free[i]] = code
            walk(i + 1, sel)

    walk(0, dict(fixed))
    return free, out


def next_edition_exists():
    """True se Eurostat pubblica gia' la tavola dell'edizione successiva."""
    nxt = f"earn_ses{int(SES_YEAR[2:]) + 4:02d}_49"
    req = urllib.request.Request(f"{EUROSTAT}/{nxt}?geo=IT", headers={"User-Agent": "potere-acquisto/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status == 200, nxt
    except urllib.error.HTTPError as e:
        return (False if e.code in (400, 404) else None), nxt
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, nxt


def prev_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y - (mo == 1):04d}-{(mo - 2) % 12 + 1:02d}"


def factor(series, year, last):
    months = sorted(series)
    peaks = {q for p, q, r in zip(months, months[1:], months[2:])
             if series[q] / series[p] - 1 > PEAK_UP and series[r] / series[q] - 1 < PEAK_DOWN}

    def eff(m):
        return series[prev_month(m)] if m in peaks and prev_month(m) in series else series[m]

    return eff(last) / (sum(eff(f"{year}-{i:02d}") for i in range(1, 13)) / 12)


def main():
    previous = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            previous = json.load(f)

    print(f"Eurostat {TABLE}...")
    data = json.loads(http_get(f"{EUROSTAT}/{TABLE}?geo=IT&lang=EN", "application/json",
                               throttle=False, server="Eurostat"))
    if data.get("error"):
        raise UpdateError(f"{TABLE}: {data['error']}")
    updated = data.get("updated", "")
    if previous and previous.get("source_updated") and updated and updated < previous["source_updated"]:
        raise UpdateError(f"{TABLE}: aggiornamento {updated} anteriore a quello salvato")
    free, cells = jsonstat_cells(data, {"freq": "A", "sex": "T", "indic_se": "ERN", "unit": "EUR",
                                        "geo": "IT", "time": SES_YEAR, "sizeclas": "GE10"})
    if free != ["isco08", "nace_r2"]:
        raise UpdateError(f"{TABLE}: dimensioni inattese {free}")
    values = {}
    for g in GROUPS:
        row = {}
        for sec in SECTIONS + [TOTAL]:
            v = cells.get((g, sec))
            if v is None:
                continue
            if not VALUE_RANGE[0] <= v <= VALUE_RANGE[1]:
                raise UpdateError(f"{TABLE}: valore fuori scala per {g} {sec}: {v}")
            row[sec] = v
        if TOTAL not in row:
            raise UpdateError(f"{TABLE}: manca il totale {TOTAL} per {g}")
        values[g] = row
    n_cells = sum(len(r) for r in values.values())
    if n_cells < MIN_CELLS:
        raise UpdateError(f"{TABLE}: solo {n_cells} celle con valore (minimo {MIN_CELLS})")

    print(f"Dati {INDEX}...")
    text = http_get(f"{API}/data/IT1,{INDEX},1.0/{KEY_INDEX}?startPeriod={SES_YEAR}-01",
                    "application/vnd.sdmx.data+csv;version=1.0.0")
    index = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("OBS_VALUE"):
            index.setdefault(r["ECON_ACTIVITY_NACE_2007"], {})[r["TIME_PERIOD"]] = float(r["OBS_VALUE"])
    if not index:
        raise UpdateError("risposta vuota dell'indice contrattuale")
    last = max(m for s in index.values() for m in s)
    if previous and previous.get("index_last_month") and last < previous["index_last_month"]:
        raise UpdateError(f"ultimo mese dell'indice {last} anteriore a quello salvato")
    factors = {}
    for sec in SECTIONS + [TOTAL]:
        code = TOTAL_INDEX if sec == TOTAL else sec
        s = index.get(code, {})
        if last not in s or not all(f"{SES_YEAR}-{i:02d}" in s for i in range(1, 13)):
            raise UpdateError(f"serie {code} dell'indice incompleta")
        f = factor(s, SES_YEAR, last)
        if not FACTOR_RANGE[0] <= f <= FACTOR_RANGE[1]:
            raise UpdateError(f"coefficiente anomalo per {sec}: {f:.4f}")
        factors[sec] = round(f, 5)

    out = {
        "source": f"Eurostat {TABLE} (indagine sulla struttura delle retribuzioni, dati ISTAT) e "
                  f"indice ISTAT delle retribuzioni contrattuali IT1:{INDEX}",
        "index": "Retribuzione lorda media annua per grande gruppo professionale ISCO-08 e "
                 "sezione NACE, Italia, unita' con almeno 10 dipendenti, euro",
        "base_note": f"Valori {SES_YEAR} da moltiplicare per factor (indice contrattuale di {last} / "
                     f"media {SES_YEAR}). Totale {TOTAL} (escluse le amministrazioni pubbliche) con "
                     f"l'indice {TOTAL_INDEX}.",
        "year": SES_YEAR,
        "source_updated": updated,
        "index_last_month": last,
        "last_checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_code": TOTAL,
        "values": values,
        "factors": factors,
    }
    text = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, OUT)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    exists, nxt = next_edition_exists()
    if exists:
        warn(f"Eurostat pubblica la nuova edizione dell'indagine ({nxt}): aggiornare SES_YEAR in update_ses.py.")
    elif exists is None:
        print(f"  controllo della nuova edizione ({nxt}) non riuscito: si riprova il mese prossimo")
    if datetime.now(timezone.utc).strftime("%Y-%m-%d") > EDITION_DEADLINE:
        warn("Nuova edizione SES attesa: verificare a mano su Eurostat il nome della tavola")

    changed = previous is None or previous.get("values") != values or previous.get("factors") != factors
    print(f"Scritto {os.path.relpath(OUT, ROOT)} ({'dati aggiornati' if changed else 'dati invariati'})")
    print(f"SES {SES_YEAR} (Eurostat, aggiornato {updated[:10]}) · indice fino a {last}")
    print(f"Celle gruppo x sezione: {n_cells} · coefficiente totale {factors[TOTAL]:.4f}")
    empty = [f"{g}/{s}" for g in GROUPS for s in SECTIONS if s not in values[g]]
    print(f"Celle vuote (si usa il totale): {len(empty)}")


if __name__ == "__main__":
    try:
        main()
    except UpdateError as e:
        print(f"ERRORE: {e}. data/ses.json NON modificato.", file=sys.stderr)
        sys.exit(1)
