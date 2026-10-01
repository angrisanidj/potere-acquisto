#!/usr/bin/env python3
"""Coefficienti per portare le retribuzioni INPS (data/inps.json, anno N)
all'ultimo mese disponibile con l'indice ISTAT delle retribuzioni contrattuali
per ATECO. Scrive data/indice_ateco.json.

Fonte: ISTAT, 155_358_DF_DCSC_RETRATECO1_7, chiave M.IT.WAGE_E_2021.N.10.
(retribuzioni contrattuali per dipendente, base dicembre 2021, esclusi i
dirigenti). Una richiesta, con il limite di 40 s di update_foi.http_get.

Coefficiente = indice dell'ultimo mese / media dell'indice nell'anno N, per
ogni sezione ATECO B-T presente nell'indice; per Italia e regioni si usa 0015
(industria e servizi di mercato, B-N), perche' l'indice non ha il solo settore
privato. I mesi di picco temporaneo (oltre +3% che rientra di oltre il 3% il
mese dopo) sono sostituiti dal mese precedente.
"""
import csv
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

from update_foi import API, UpdateError, http_get

INDEX = "155_358_DF_DCSC_RETRATECO1_7"
KEY = "M.IT.WAGE_E_2021.N.10."
TOTAL_INDEX = "0015"
SECTIONS = list("BCDEFGHIJKLMNPQRST")
FACTOR_RANGE = (0.9, 1.6)
PEAK_UP, PEAK_DOWN = 0.03, -0.03

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPS = os.path.join(ROOT, "data", "inps.json")
OUT = os.path.join(ROOT, "data", "indice_ateco.json")


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
    with open(INPS, encoding="utf-8") as f:
        year = json.load(f)["year"]
    previous = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            previous = json.load(f)

    print(f"Dati {INDEX} dal {year}-01...")
    text = http_get(f"{API}/data/IT1,{INDEX},1.0/{KEY}?startPeriod={year}-01",
                    "application/vnd.sdmx.data+csv;version=1.0.0")
    index = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("OBS_VALUE"):
            index.setdefault(r["ECON_ACTIVITY_NACE_2007"], {})[r["TIME_PERIOD"]] = float(r["OBS_VALUE"])
    if not index:
        raise UpdateError("risposta vuota dell'indice contrattuale")
    last = max(m for s in index.values() for m in s)
    if previous and previous.get("year") == year and last < previous.get("index_last_month", ""):
        raise UpdateError(f"ultimo mese {last} anteriore a quello salvato")

    factors = {}
    for code in SECTIONS + [TOTAL_INDEX]:
        s = index.get(code, {})
        if last not in s or not all(f"{year}-{i:02d}" in s for i in range(1, 13)):
            if code == TOTAL_INDEX:
                raise UpdateError(f"serie {code} incompleta")
            continue  # sezione senza serie completa: la pagina usera' 0015 e lo dichiarera'
        f = factor(s, year, last)
        if not FACTOR_RANGE[0] <= f <= FACTOR_RANGE[1]:
            raise UpdateError(f"coefficiente anomalo per {code}: {f:.4f}")
        factors[code] = round(f, 5)

    out = {
        "source": f"ISTAT, indice delle retribuzioni contrattuali per dipendente per ATECO, IT1:{INDEX}",
        "base_note": f"Coefficiente = indice di {last} / media dell'indice nel {year} (anno dei dati INPS). "
                     f"Italia e regioni: {TOTAL_INDEX} (industria e servizi di mercato B-N).",
        "year": year,
        "index_last_month": last,
        "last_checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_code": TOTAL_INDEX,
        "factors": factors,
    }
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    os.replace(tmp, OUT)
    missing = [c for c in SECTIONS if c not in factors]
    print(f"Scritto data/indice_ateco.json: base {year}, indice fino a {last}, coefficiente {TOTAL_INDEX} "
          f"{factors[TOTAL_INDEX]:.4f}" + (f"; sezioni senza serie: {missing}" if missing else ""))


if __name__ == "__main__":
    try:
        main()
    except UpdateError as e:
        print(f"ERRORE: {e}. data/indice_ateco.json NON modificato.", file=sys.stderr)
        sys.exit(1)
