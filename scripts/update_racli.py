#!/usr/bin/env python3
"""Scarica dall'API SDMX ISTAT le retribuzioni orarie RACLI dei dipendenti a
tempo pieno del settore privato extra-agricolo (per divisione ATECO e per
regione) e i coefficienti per portarle all'ultimo mese disponibile con l'indice
delle retribuzioni contrattuali per ATECO. Scrive data/racli.json.

Solo libreria standard; client HTTP, tentativi e limite di 40 s fra le
richieste vengono da update_foi.py.

Fonti (verificate interrogando i metadati, ottobre 2026)
--------------------------------------------------------
RACLI - registro annuale su retribuzioni, ore e costo del lavoro
  DSD IT1:DCSC_RACLI, dimensioni FREQ.REF_AREA.DATA_TYPE.SEX.AGE.EDU_LEV_HIGHEST.
  COUNTRY_BIRTH.CITIZENSHIP.TYPE_OF_CONTRACT.FULL_PART_TIME.CONTARCTUAL_OCCUPATION.
  EMPLOYEE_TENURE.PAID_DAYS.ECON_ACTIVITY_NACE_2007.EMPLOYESS_CLASS
  - 533_957_DF_DCSC_RACLI_22 "Regime orario - 2 digit": divisione ATECO x regime
    orario, solo Italia. Chiave A.IT..9.TOTAL.99.WORLD.WORLD.9.1.99.TOTAL.TOTAL..TOTAL
    (FULL_PART_TIME=1 tempo pieno).
  - 533_957_DF_DCSC_RACLI_13 "Regime orario - dati provinciali": territorio x regime
    orario, tutti i settori. Chiave A...9.TOTAL.99.WORLD.WORLD.9.1.99.TOTAL.TOTAL.0010.TOTAL
  - DATA_TYPE: HOUWAG_ENTEMP_{AV,MED,FIRD,NIND}_MI = retribuzione lorda oraria per
    ora retribuita (media, mediana, primo decile, nono decile).
  - Definizioni (nota metodologica RACLI): retribuzione lorda = imponibile
    previdenziale per cassa, straordinari inclusi; ore retribuite = ore lavorabili
    da orario contrattuale - ore non retribuite + straordinari (ferie e festivita'
    incluse).
Indice delle retribuzioni contrattuali per ATECO
  - 155_358_DF_DCSC_RETRATECO1_7, chiave M.IT.WAGE_E_2021.N.10. (per dipendente,
    base dicembre 2021, esclusi i dirigenti). Stessa codelist IT1:CL_ATECO_2007 v1.0
    di RACLI: a codice uguale corrisponde la stessa attivita'.

Regole
------
- Anno RACLI: l'ultimo per cui il totale ha media, mediana e decili. Quando ISTAT
  pubblica un anno nuovo lo script ci passa da solo e lo segnala con ::warning::.
- Valori di una divisione oscurati per segreto statistico (oggi la 07): si usa il
  valore RACLI della sezione, dichiarato nel campo racli_from.
- Indice: stessa divisione se la serie esiste per tutti i mesi dell'anno RACLI e
  per l'ultimo mese; altrimenti il livello superiore (oggi 59 -> J, 96 -> S),
  dichiarato nel campo index_code.
- Totale nazionale e regioni: RACLI copre il privato extra-agricolo, ma l'indice non
  ha un codice per il privato senza PA con dati (0037 e' nella codelist ma vuoto):
  si usa 0015, industria e servizi di mercato (B-N).
- Coefficiente = indice dell'ultimo mese / media dell'indice nell'anno RACLI. I mesi
  di picco temporaneo (aumento oltre il 3% che rientra di oltre il 3% il mese dopo,
  come dicembre 2023) sono sostituiti dal mese precedente, come nella pagina.
"""

import csv
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

from update_foi import API, UpdateError, http_get

RACLI_DIV = "533_957_DF_DCSC_RACLI_22"
RACLI_TERR = "533_957_DF_DCSC_RACLI_13"
INDEX = "155_358_DF_DCSC_RETRATECO1_7"
KEY_DIV = "A.IT..9.TOTAL.99.WORLD.WORLD.9.1.99.TOTAL.TOTAL..TOTAL"
KEY_TERR = "A...9.TOTAL.99.WORLD.WORLD.9.1.99.TOTAL.TOTAL.0010.TOTAL"
KEY_INDEX = "M.IT.WAGE_E_2021.N.10."
MEASURES = {
    "HOUWAG_ENTEMP_AV_MI": "media",
    "HOUWAG_ENTEMP_MED_MI": "mediana",
    "HOUWAG_ENTEMP_FIRD_MI": "d1",
    "HOUWAG_ENTEMP_NIND_MI": "d9",
}
TOTAL = "0010"
TOTAL_INDEX = "0015"
YEARS_BACK = 4          # anni RACLI richiesti a ritroso per trovare l'ultimo completo
MIN_DIVISIONS = 70
N_REGIONS = 21
FACTOR_RANGE = (0.9, 1.6)
PEAK_UP, PEAK_DOWN = 0.03, -0.03

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "racli.json")

CSV_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"
STRUCT = "application/vnd.sdmx.structure+json;version=1.0"


def warn(msg):
    print(f"::warning::{msg}")


def fetch_codelists():
    """Etichette italiane e gerarchia di ATECO e territori, dalla DSD di RACLI."""
    data = json.loads(http_get(f"{API}/datastructure/IT1/DCSC_RACLI/1.0?references=children",
                               STRUCT, {"Accept-Language": "it"}))["data"]
    out = {}
    for cl in data.get("codelists", []):
        if cl["id"] in ("CL_ATECO_2007", "CL_ITTER107"):
            out[cl["id"]] = {
                c["id"]: {"name": (c.get("names") or {}).get("it") or c.get("name") or c["id"],
                          "parent": c.get("parent")}
                for c in cl["codes"]
            }
    if set(out) != {"CL_ATECO_2007", "CL_ITTER107"}:
        raise UpdateError("codelist ATECO o territori assenti nella struttura di RACLI")
    return out["CL_ATECO_2007"], out["CL_ITTER107"]


def fetch_csv(dataflow, key, params):
    text = http_get(f"{API}/data/IT1,{dataflow},1.0/{key}?{params}", CSV_ACCEPT)
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise UpdateError(f"risposta vuota per {dataflow}")
    return rows


def racli_table(rows, dim):
    """{anno: {codice: {misura: valore}}}; i valori oscurati restano assenti."""
    out = {}
    for r in rows:
        if r.get("FULL_PART_TIME") != "1" or r.get("DATA_TYPE") not in MEASURES:
            continue
        if not r.get("OBS_VALUE"):
            continue  # flag "c": dato oscurato per segreto statistico
        try:
            v = float(r["OBS_VALUE"])
        except ValueError:
            raise UpdateError(f"valore non numerico in {dim} {r.get(dim)}")
        out.setdefault(r["TIME_PERIOD"], {}).setdefault(r[dim], {})[MEASURES[r["DATA_TYPE"]]] = v
    return out


def complete(v):
    return v is not None and set(v) == set(MEASURES.values())


def check_values(code, v):
    if not all(x > 0 for x in v.values()):
        raise UpdateError(f"{code}: valori non positivi {v}")
    if not v["d1"] <= v["mediana"] <= v["d9"]:
        raise UpdateError(f"{code}: decili e mediana non ordinati {v}")
    if not v["d1"] <= v["media"] <= v["d9"]:
        raise UpdateError(f"{code}: media fuori dall'intervallo dei decili {v}")


def prev_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y - (mo == 1):04d}-{(mo - 2) % 12 + 1:02d}"


def factor(series, year, last):
    """Indice dell'ultimo mese / media dell'anno, sostituendo i picchi temporanei."""
    months = sorted(series)
    peaks = {q for p, q, r in zip(months, months[1:], months[2:])
             if series[q] / series[p] - 1 > PEAK_UP and series[r] / series[q] - 1 < PEAK_DOWN}

    def eff(m):
        return series[prev_month(m)] if m in peaks and prev_month(m) in series else series[m]

    avg = sum(eff(f"{year}-{i:02d}") for i in range(1, 13)) / 12
    return eff(last) / avg


def main():
    previous = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            previous = json.load(f)

    print("Codelist ATECO e territori...")
    ateco, terr = fetch_codelists()
    this_year = datetime.now(timezone.utc).year
    print(f"Dati {RACLI_DIV}...")
    div_rows = fetch_csv(RACLI_DIV, KEY_DIV, f"startPeriod={this_year - YEARS_BACK}")
    by_year = racli_table(div_rows, "ECON_ACTIVITY_NACE_2007")
    years = sorted(y for y, t in by_year.items() if complete(t.get(TOTAL)))
    if not years:
        raise UpdateError("nessun anno RACLI con il totale completo")
    year = years[-1]
    if previous and previous.get("year") and year < previous["year"]:
        raise UpdateError(f"anno RACLI {year} anteriore a quello salvato {previous['year']}")
    div = by_year[year]
    # codici presenti nella risposta per l'anno scelto, anche con valori oscurati
    seen = {r["ECON_ACTIVITY_NACE_2007"] for r in div_rows
            if r.get("TIME_PERIOD") == year and r.get("FULL_PART_TIME") == "1"}

    print(f"Dati {RACLI_TERR} ({year})...")
    terr_rows = fetch_csv(RACLI_TERR, KEY_TERR, f"startPeriod={year}&endPeriod={year}")
    reg = racli_table(terr_rows, "REF_AREA").get(year, {})

    print(f"Dati {INDEX}...")
    idx_rows = fetch_csv(INDEX, KEY_INDEX, f"startPeriod={year}-01")
    index = {}
    for r in idx_rows:
        if r.get("OBS_VALUE"):
            index.setdefault(r["ECON_ACTIVITY_NACE_2007"], {})[r["TIME_PERIOD"]] = float(r["OBS_VALUE"])
    last = max(m for s in index.values() for m in s)
    if previous and previous.get("index_last_month") and last < previous["index_last_month"]:
        raise UpdateError(f"ultimo mese dell'indice {last} anteriore a quello salvato")

    def index_ok(code):
        s = index.get(code, {})
        return last in s and all(f"{year}-{i:02d}" in s for i in range(1, 13))

    def section_of(code):
        p = ateco.get(code, {}).get("parent")
        while p and not (len(p) == 1 and p.isalpha()):
            p = ateco.get(p, {}).get("parent")
        return p

    divisions = []
    for code in sorted(c for c in ateco if len(c) == 2 and c.isdigit()):
        own = div.get(code)
        sec = section_of(code)
        if not complete(own):
            if code not in seen:
                continue  # divisione fuori dal campo di RACLI (es. agricoltura, PA)
            if not complete(div.get(sec)):
                warn(f"RACLI {year}: divisione {code} senza dati e senza dati di sezione {sec}")
                continue
            values, racli_from = div[sec], sec
        else:
            values, racli_from = own, code
        idx_code = code
        while idx_code and not index_ok(idx_code):
            idx_code = ateco.get(idx_code, {}).get("parent")
        if not idx_code:
            raise UpdateError(f"nessuna serie dell'indice per la divisione {code} o i livelli superiori")
        check_values(code, values)
        f = factor(index[idx_code], year, last)
        if not FACTOR_RANGE[0] <= f <= FACTOR_RANGE[1]:
            raise UpdateError(f"coefficiente anomalo per {code} ({idx_code}): {f:.4f}")
        divisions.append({
            "code": code, "name": ateco[code]["name"],
            "section": sec, "section_name": ateco.get(sec, {}).get("name"),
            "values": values, "racli_from": racli_from,
            "index_code": idx_code, "factor": round(f, 5),
        })
    if len(divisions) < MIN_DIVISIONS:
        raise UpdateError(f"solo {len(divisions)} divisioni con dati (minimo {MIN_DIVISIONS})")

    if not index_ok(TOTAL_INDEX):
        raise UpdateError(f"serie {TOTAL_INDEX} dell'indice incompleta")
    tot_f = factor(index[TOTAL_INDEX], year, last)
    check_values(TOTAL, div[TOTAL])

    regions = []
    for code in sorted(c for c in reg if len(c) == 4 and c.startswith("IT")):
        if complete(reg[code]):
            check_values(code, reg[code])
            regions.append({"code": code, "name": terr.get(code, {}).get("name", code), "values": reg[code]})
    if len(regions) != N_REGIONS:
        raise UpdateError(f"{len(regions)} regioni complete invece di {N_REGIONS}")

    out = {
        "source": "ISTAT - registro RACLI (retribuzioni, ore e costo del lavoro), dataflow "
                  f"IT1:{RACLI_DIV} e IT1:{RACLI_TERR}; indice delle retribuzioni contrattuali "
                  f"per ATECO IT1:{INDEX}. API SDMX {API}",
        "index": "Retribuzione lorda oraria per ora retribuita, posizioni dipendenti a tempo "
                 "pieno del settore privato extra-agricolo: media, mediana, primo e nono decile",
        "base_note": f"Valori RACLI {year} da moltiplicare per factor (indice contrattuale di "
                     f"{last} / media {year}) per la stima all'ultimo mese. Totale e regioni con "
                     f"l'indice {TOTAL_INDEX} (industria e servizi di mercato B-N).",
        "year": year,
        "index_last_month": last,
        "last_checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": {"code": TOTAL, "values": div[TOTAL], "index_code": TOTAL_INDEX, "factor": round(tot_f, 5)},
        "regions_index_code": TOTAL_INDEX,
        "regions_factor": round(tot_f, 5),
        "divisions": divisions,
        "regions": regions,
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

    if previous and previous.get("year") and previous["year"] != year:
        warn(f"Anno RACLI cambiato da {previous['year']} a {year}: controlla il primo aggiornamento "
             "(divisioni, regioni e coefficienti).")
    changed = previous is None or {k: previous.get(k) for k in ("divisions", "regions", "total")} != \
        {k: out[k] for k in ("divisions", "regions", "total")}
    t = div[TOTAL]
    print(f"Scritto {os.path.relpath(OUT, ROOT)} ({'dati aggiornati' if changed else 'dati invariati'})")
    print(f"Anno RACLI: {year} · indice fino a {last}")
    print(f"Divisioni: {len(divisions)} · regioni: {len(regions)}")
    print(f"Totale tempo pieno {year}: mediana {t['mediana']} · d1 {t['d1']} · d9 {t['d9']} · media {t['media']} €/h")
    print(f"Coefficiente {TOTAL_INDEX} {last}/{year}: {tot_f:.4f}")
    for d in divisions:
        notes = []
        if d["racli_from"] != d["code"]:
            notes.append(f"valori RACLI della sezione {d['racli_from']}")
        if d["index_code"] != d["code"]:
            notes.append(f"indice {d['index_code']}")
        if notes:
            print(f"  {d['code']} {d['name'][:50]}: {', '.join(notes)}")


if __name__ == "__main__":
    try:
        main()
    except UpdateError as e:
        print(f"ERRORE: {e}. data/racli.json NON modificato.", file=sys.stderr)
        sys.exit(1)
