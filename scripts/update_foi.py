#!/usr/bin/env python3
"""Scarica dall'API SDMX ISTAT l'indice FOI senza tabacchi (Italia, mensile),
lo raccorda in un'unica serie concatenata in base 2025=100 e lo salva in
data/foi.json.

Solo libreria standard: nessuna dipendenza da installare.

Individuazione di dataflow e chiave (interrogando i metadati, ottobre 2026)
---------------------------------------------------------------------------
- GET /dataflow/IT1 -> "169_748_DF_DCSP_FOI1B2025_1"
  "Foi - monthly data from 2026 (base 2025) - Ecoicop 2", DSD IT1:DCSP_FOI1B2025.
- GET /datastructure/IT1/DCSP_FOI1B2025/1.0?references=children -> dimensioni
  FREQ.REF_AREA.DATA_TYPE.MEASURE.ECOICOP_2, con codelist:
    FREQ        M    = mensile
    REF_AREA    IT   = Italia
    DATA_TYPE   4 / 11 / 55 / 101 = indice FOI base 1995 / 2010 / 2015 / 2025
    MEASURE     4    = numero indice
    ECOICOP_2   00ST = indice generale senza tabacchi
- GET /availableconstraint/169_748_DF_DCSP_FOI1B2025_1/all/all/all ->
  il dataflow contiene tutte e quattro le basi, dal 1996-01 in poi:
  base 1995 per 1996-2010, base 2010 per 2011-2015, base 2015 per 2016-2025,
  base 2025 dal 2026.
  Chiave usata: M.IT..4.00ST (DATA_TYPE lasciato libero per avere tutte le basi).

Coefficienti di raccordo (fonte ufficiale ISTAT)
------------------------------------------------
File "DCSP_FOI_CR_Ecoicopv2.xlsx", allegato al dataflow
DF_BULK_DCSP_FOI1B2025_TB1 ("Splicing coefficient table ... from 2015 to 2025"):
https://esploradati.istat.it/databrowser/DWL/Prezzi/DCSP_FOI1B2025/DCSP_FOI_CR_Ecoicopv2.xlsx
riga "00st - Indice generale senza tabacchi":
    da base 1995 a base 2010: 1,373
    da base 2010 a base 2015: 1,071
    da base 2015 a base 2025: 1,214
Regola ISTAT: un indice in base vecchia si porta nella base successiva
dividendolo per il coefficiente. Esempio: indice base 1995 -> base 2025 =
valore / (1,373 * 1,071 * 1,214).
(Controllo: media 2010 in base 1995 = 137,25; media 2015 in base 2010 = 107,06;
media 2025 in base 2015 = 121,39.)

Dati definitivi
---------------
Il FOI non ha stima preliminare (la "flash" riguarda NIC e IPCA) e viene
pubblicato direttamente come definitivo verso metà del mese successivo.
Per sicurezza le osservazioni con OBS_STATUS provvisorio/stimato vengono
comunque scartate; se ciò creasse un buco nella serie, lo script fallisce.
"""

import csv
import io
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://esploradati.istat.it/SDMXWS/rest"
DATAFLOW = "169_748_DF_DCSP_FOI1B2025_1"
KEY = "M.IT..4.00ST"

# DATA_TYPE -> base dell'indice
BASES = {"4": 1995, "11": 2010, "55": 2015, "101": 2025}
TARGET_BASE = 2025

# Coefficienti di raccordo ufficiali ISTAT per l'indice "00st" (vedi docstring).
SPLICE = {
    (1995, 2010): 1.373,
    (2010, 2015): 1.071,
    (2015, 2025): 1.214,
}

# Codici OBS_STATUS (codelist IT1:CL_FLAG) che indicano dati non definitivi.
NOT_FINAL_FLAGS = {"p", "pr", "0P", "P_ERROR", "PB", "PE", "PC", "PI", "e", "f"}

TIMEOUT = 180  # secondi per richiesta
ATTEMPTS = 3
BACKOFF = [20, 60]  # attesa prima del 2° e del 3° tentativo

MAX_MONTHLY_CHANGE = 0.05

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "foi.json")

CHECK_MONTHS = ["2002-01", "2015-01", "2021-01"]


class UpdateError(Exception):
    pass


def http_get(url, accept, extra_headers=None):
    headers = {"Accept": accept, "User-Agent": "potere-acquisto/1.0"}
    headers.update(extra_headers or {})
    req = urllib.request.Request(url, headers=headers)
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                if r.status != 200:
                    raise UpdateError(f"HTTP {r.status}")
                return r.read().decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError, OSError, UpdateError) as e:
            last = e
            print(f"  tentativo {attempt}/{ATTEMPTS} fallito: {e}", file=sys.stderr)
            if attempt < ATTEMPTS:
                time.sleep(BACKOFF[attempt - 1])
    raise UpdateError(f"API ISTAT non raggiungibile dopo {ATTEMPTS} tentativi: {last}")


def check_metadata():
    """Verifica che il dataflow esista ancora e contenga la chiave attesa."""
    url = f"{API}/availableconstraint/{DATAFLOW}/all/all/all"
    meta = json.loads(http_get(url, "application/vnd.sdmx.structure+json;version=1.0"))
    try:
        kv = meta["data"]["contentConstraints"][0]["cubeRegions"][0]["keyValues"]
    except (KeyError, IndexError) as e:
        raise UpdateError(f"metadati inattesi per {DATAFLOW}: {e}")
    values = {k["id"]: set(k.get("values", [])) for k in kv}
    for dim, code in [("FREQ", "M"), ("REF_AREA", "IT"), ("MEASURE", "4"), ("ECOICOP_2", "00ST")]:
        if code not in values.get(dim, set()):
            raise UpdateError(f"il dataflow {DATAFLOW} non contiene {dim}={code}")
    unknown = values.get("DATA_TYPE", set()) - set(BASES)
    if unknown:
        raise UpdateError(
            f"nuovi DATA_TYPE nel dataflow ({sorted(unknown)}): probabile cambio di base, "
            "aggiornare BASES e SPLICE con i nuovi coefficienti ISTAT"
        )


def to_target_base(value, base):
    """Porta un indice dalla sua base alla base TARGET_BASE con i coefficienti ISTAT."""
    chain = sorted(BASES.values())
    i = chain.index(base)
    for a, b in zip(chain[i:], chain[i + 1:]):
        value /= SPLICE[(a, b)]
    return value


def next_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}"


def fetch_series():
    url = f"{API}/data/IT1,{DATAFLOW},1.0/{KEY}"
    text = http_get(url, "application/vnd.sdmx.data+csv;version=1.0.0")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise UpdateError("risposta dati vuota")

    by_month = {}  # mese -> (base, valore originale)
    skipped = []
    for r in rows:
        if r.get("ECOICOP_2") != "00ST" or r.get("REF_AREA") != "IT" or r.get("MEASURE") != "4":
            continue
        dt = r.get("DATA_TYPE")
        if dt not in BASES:
            raise UpdateError(f"DATA_TYPE sconosciuto nei dati: {dt}")
        month = r["TIME_PERIOD"]
        if len(month) != 7 or month[4] != "-":
            raise UpdateError(f"periodo inatteso: {month}")
        if (r.get("OBS_STATUS") or "").strip() in NOT_FINAL_FLAGS:
            skipped.append(month)
            continue
        try:
            val = float(r["OBS_VALUE"])
        except (TypeError, ValueError):
            raise UpdateError(f"valore non numerico per {month}: {r.get('OBS_VALUE')!r}")
        base = BASES[dt]
        # Se lo stesso mese è presente in più basi, vale la più recente.
        if month not in by_month or base > by_month[month][0]:
            by_month[month] = (base, val)

    if skipped:
        print(f"  scartati dati non definitivi: {', '.join(sorted(skipped))}")
    series = {m: round(to_target_base(v, b), 4) for m, (b, v) in sorted(by_month.items())}
    return series


def validate(series, previous):
    if not series:
        raise UpdateError("serie vuota")
    months = list(series)
    m = months[0]
    for actual in months:
        if actual != m:
            raise UpdateError(f"mese mancante: {m}")
        m = next_month(m)
    prev_val = None
    for month, v in series.items():
        if not v > 0:
            raise UpdateError(f"valore non positivo in {month}: {v}")
        if prev_val is not None and abs(v / prev_val - 1) > MAX_MONTHLY_CHANGE:
            raise UpdateError(
                f"variazione mensile anomala in {month}: {100 * (v / prev_val - 1):+.2f}%"
            )
        prev_val = v
    if previous and previous.get("last_month") and months[-1] < previous["last_month"]:
        raise UpdateError(
            f"ultimo mese {months[-1]} anteriore a quello già salvato {previous['last_month']}"
        )


def main():
    previous = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            previous = json.load(f)

    print(f"Metadati {DATAFLOW}...")
    check_metadata()
    print(f"Dati {KEY}...")
    series = fetch_series()
    validate(series, previous)

    months = list(series)
    first, last = months[0], months[-1]
    out = {
        "source": "ISTAT - Indice dei prezzi al consumo per le famiglie di operai e impiegati (FOI), "
                  f"API SDMX {API}, dataflow IT1:{DATAFLOW}, chiave {KEY}",
        "index": "FOI senza tabacchi - indice generale, Italia, mensile",
        "base_note": "Serie concatenata in base 2025=100. I dati in base 1995 (1996-2010), "
                     "2010 (2011-2015) e 2015 (2016-2025) sono riportati in base 2025 con i "
                     "coefficienti di raccordo ufficiali ISTAT per l'indice senza tabacchi: "
                     "1,373 (1995->2010), 1,071 (2010->2015), 1,214 (2015->2025). "
                     "Solo dati definitivi.",
        "first_month": first,
        "last_month": last,
        "last_checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "series": series,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.replace(tmp, OUT)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    changed = previous is None or previous.get("series") != series
    print(f"Scritto {os.path.relpath(OUT, ROOT)} ({'serie aggiornata' if changed else 'serie invariata'})")
    print(f"Primo mese: {first}")
    print(f"Ultimo mese: {last}")
    print(f"Osservazioni: {len(series)}")
    for m in CHECK_MONTHS:
        if m in series:
            print(f"Coefficiente I({last})/I({m}): {series[last] / series[m]:.4f}")
        else:
            print(f"Coefficiente I({last})/I({m}): mese non disponibile")


if __name__ == "__main__":
    try:
        main()
    except UpdateError as e:
        print(f"ERRORE: {e}. data/foi.json NON modificato.", file=sys.stderr)
        sys.exit(1)
