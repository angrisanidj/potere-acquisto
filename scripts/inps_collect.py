#!/usr/bin/env python3
"""Raccolta (a mano) delle distribuzioni INPS per classe di retribuzione annua e
costruzione di data/inps.json.

Fonte: INPS, Osservatorio sui lavoratori dipendenti del settore privato non
agricolo, tavola "Lavoratori dipendenti per classi di importo della retribuzione
annua e cittadinanza" (per il 2024: id 526). Retribuzione = imponibile
previdenziale nell'anno; lavoratori con periodo retribuito "Anno intero" e
"Presenza tempo parziale nell'anno" = No.

Uso:
    python scripts/inps_collect.py            # scarica le richieste mancanti
    python scripts/inps_collect.py --offline  # solo risposte gia' salvate

Condizioni d'uso: il portale degli Osservatori non indica una licenza; si
applica l'art. 52, comma 2, del CAD (dati pubblicati senza licenza = dati di
tipo aperto).

API interna del portale (POST JSON, nessun login), documentata dalle richieste
del browser:
  /api/getAlberoNavigazione/      {"language":"it","IdAreaTematica":0}
  /api/getStrutturaOsservatorio/  {"id_osservatorio":"526","language":"it"}
  /api/getDatiOsservatorio/       body come quello del portale: righe e colonne
      indicate con il Name della gerarchia ("CLASSE DI RETRIBUZIONE ANNUA",
      "Periodo retribuito datore"), filtri {"id": campo, "label": Name della
      gerarchia, "values": [...]}, filtro anno con label "Anno-".

Regole:
- almeno MIN_GAP secondi fra due richieste; ogni risposta grezza e' salvata in
  data/inps_raw/<anno>/<nome>.json e non viene mai richiesta di nuovo;
- tavola rifiutata per anonimizzazione: un solo nuovo tentativo
  (quadri: da 15.000 -> da 20.000 euro; dirigenti: nessuna soglia -> da 20.000;
  le altre: esclusa la fascia piu' bassa della distribuzione nazionale
  corrispondente); se ancora rifiutata, "non disponibile";
- nessun valore ricavato per differenza fra tavole;
- alla prima risposta che non e' ne' dati ne' un rifiuto per anonimizzazione
  lo script si ferma senza scrivere data/inps.json.
"""
import argparse
import gzip
import json
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

BASE = "https://servizi2.inps.it/servizi/osservatoristatistici/api"
TABLE_TITLE = "Lavoratori dipendenti per classi di importo della retribuzione annua e cittadinanza"
MIN_GAP = 12
TIMEOUT = 120

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "inps.json")
RAW_ROOT = os.path.join(ROOT, "data", "inps_raw")
STAMP = os.path.join(tempfile.gettempdir(), "potere-acquisto-inps-ultima-richiesta")

CLASSES = [
    ("Fino a 5000", 0, 5000), ("5000-9999", 5000, 10000), ("10000-14999", 10000, 15000),
    ("15000-19999", 15000, 20000), ("20000-24999", 20000, 25000), ("25000-29999", 25000, 30000),
    ("30000-34999", 30000, 35000), ("35000-39999", 35000, 40000), ("40000-44999", 40000, 45000),
    ("45000-49999", 45000, 50000), ("50000-59999", 50000, 60000), ("60000-79999", 60000, 80000),
    ("80000 ed oltre", 80000, None),
]
CLASS_NAMES = [c[0] for c in CLASSES]
QUALS = ["Operaio", "Impiegato", "Quadro", "Dirigente", "Apprendista"]
REGION_QUALS = ["Operaio", "Impiegato", "Quadro", "Apprendista", None]  # None = tutte le qualifiche

# Sezioni ATECO 2007 come le scrive l'INPS -> lettera
SECTIONS = {
    "Estrazione di minerali da cave e miniere": "B",
    "Attivita' manifatturiere": "C",
    "Fornitura di energia elettrica, gas, vapore e aria condizionata": "D",
    "Fornitura di acqua, reti fognarie, attivita' di gestione dei rifiuti e risanamento": "E",
    "Costruzioni": "F",
    "Commercio all'ingrosso e al dettaglio, riparazione di autoveicoli e motocicli": "G",
    "Trasporto e magazzinaggio": "H",
    "Attivita' dei servizi di alloggio e di ristorazione": "I",
    "Servizi di informazione e comunicazione": "J",
    "Attivita' finanziarie e assicurative": "K",
    "Attivita' immobiliari": "L",
    "Attivita' professionali, scientifiche e tecniche": "M",
    "Noleggio, agenzie di viaggio, servizi di supporto alle imprese": "N",
    "Istruzione": "P",
    "Sanita' e assistenza sociale": "Q",
    "Attivita' artistiche, sportive, di intrattenimento e divertimento": "R",
    "Altre attivita' di servizi": "S",
    "Attivita' di famiglie e convivenze come datori di lavoro per personale domestico, produzione "
    "di beni e servizi indifferenziati per uso proprio da parte di famiglie e convivenze": "T",
}


class Stop(Exception):
    pass


class Missing(Exception):
    """Risposta non salvata e modalita' --offline."""


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ------------------------------------------------------------------ client
class Client:
    def __init__(self, raw_dir, offline):
        self.raw_dir, self.offline = raw_dir, offline
        os.makedirs(raw_dir, exist_ok=True)
        # richieste da non ripetere (decisione presa a mano, con il motivo)
        skip = os.path.join(raw_dir, "_non_ritentare.json")
        self.skip = set(json.load(open(skip, encoding="utf-8"))["richieste"]) if os.path.exists(skip) else set()

    def call(self, endpoint, body, name):
        path = os.path.join(self.raw_dir, name + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)["response"], True
        if self.offline or name in self.skip:
            raise Missing(name)
        try:
            last = float(open(STAMP).read())
        except (OSError, ValueError):
            last = 0.0
        if last + MIN_GAP > time.time():
            time.sleep(last + MIN_GAP - time.time())
        open(STAMP, "w").write(str(time.time()))
        data = (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
        req = urllib.request.Request(f"{BASE}/{endpoint}/", data=data, headers={
            "Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
            "Accept-Language": "it,it-IT;q=0.9,en;q=0.8", "Accept-Encoding": "gzip",
            "User-Agent": "potere-acquisto/1.0 (https://github.com/angrisanidj/potere-acquisto)"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                status = r.status
        except Exception as e:  # rete o HTTP: risposta inattesa
            raise Stop(f"{name}: richiesta fallita ({e})")
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        try:
            resp = json.loads(raw.decode("utf-8-sig"))
        except ValueError:
            raise Stop(f"{name}: risposta non JSON")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"endpoint": endpoint, "body": body, "status": status,
                       "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "response": resp}, f, ensure_ascii=False)
        return resp, False


# ------------------------------------------------------------------ tavola
def find_table(tree):
    """id e nome della tavola piu' recente "per classi di importo" con un solo anno.

    Nell'albero il nodo della tavola ha descrizione TABLE_TITLE e gli osservatori in
    elencoOsservatoriArea, con nome "Anno 2024 (...)" o "Anni 2019-2023 (...)".
    """
    found = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("descrizione") == TABLE_TITLE:
                for c in o.get("elencoOsservatoriArea") or []:
                    nome = str(c.get("nome", ""))
                    if nome.startswith("Anno ") and nome[5:9].isdigit():
                        found.append((nome[5:9], str(c["id_osservatorio"]), nome))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(tree)
    if not found:
        raise Stop("tavola per classi di importo non trovata nell'albero")
    return max(found)


def body_for(meta, qual=None, section=None, region=None, classes=None):
    filters = []
    if classes:
        filters.append({"id": "cl_retr", "label": "CLASSE DI RETRIBUZIONE ANNUA", "values": classes})
    if section:
        filters.append({"id": "ATECO07_1", "label": "Attivita economica ATECO 2007", "values": [section]})
    if region:
        filters.append({"id": "regione", "label": "Regione", "values": [region]})
    filters += [
        {"id": "anno", "label": "Anno-", "values": [meta["year"]]},
        {"id": "cl_ggretr", "label": "Periodo retribuito datore", "values": ["Anno intero"]},
        {"id": "ppa", "label": "PRESENZA TEMPO PARZIALE", "values": ["No"]},
    ]
    if qual:
        filters.append({"id": "macro_qualifica", "label": "Qualifica", "values": [qual]})
    body = {
        "id_osservatorio": meta["id"], "nome_osservatorio": meta["name"], "language": "",
        "totalRow": True, "totalColumn": True, "subtotalRow": True, "subtotalColumn": True,
        "selections": {
            "rows": [{"id": "CLASSE DI RETRIBUZIONE ANNUA", "label": "CLASSE DI RETRIBUZIONE ANNUA",
                      "order": 1, "aggregate": True, "expand": "", "hide": False}],
            "cols": [{"id": "Periodo retribuito datore", "label": "Periodo retribuito datore",
                      "aggregate": True, "order": 1, "expand": "", "hide": False}],
            "measures": [{"id": "_FREQ_SUM", "label": "_FREQ_SUM", "order": 0, "statistic": "SUM"}],
            "filters": filters,
        },
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def parse(name, resp):
    """('ok', {classe: n}, totale) | ('rifiutata', None, None); altrimenti Stop."""
    if isinstance(resp, dict) and resp.get("messageType") == "Anonimizzazione":
        return "rifiutata", None, None
    if not isinstance(resp, dict) or "values" not in resp:
        raise Stop(f"{name}: risposta inattesa {str(resp)[:300]}")
    out, total = {}, None
    for row in resp["values"]:
        cols = {c["value"]: c["measures"][0]["value"] for b in row.get("columns", []) for c in b["values"]}
        if "Anno intero" not in cols:
            raise Stop(f"{name}: riga senza colonna 'Anno intero'")
        v = int(cols["Anno intero"].replace(".", ""))
        name_row = row.get("value")
        if name_row in CLASS_NAMES:
            out[name_row] = v
        elif str(name_row).lower().startswith("total"):
            total = v
        else:
            raise Stop(f"{name}: riga inattesa {name_row}")
    if total is None or total != sum(out.values()):
        raise Stop(f"{name}: totale assente o diverso dalla somma delle classi")
    return "ok", out, total


def from_class(c):
    return CLASS_NAMES[CLASS_NAMES.index(c):]


def attempts(qual, national):
    if qual == "Quadro":
        return [("da 15.000", from_class("15000-19999")), ("da 20.000", from_class("20000-24999"))]
    if qual == "Dirigente":
        return [("nessuna", None), ("da 20.000", from_class("20000-24999"))]
    present = [c for c in CLASS_NAMES if c in national[qual or "Totale"]["counts"]]
    return [("nessuna", None), (f"esclusa {present[0]}", from_class(present[1]))]


def collect(client, meta, name, national, qual, **where):
    rec = {"tentativi": []}
    for k, (label, classes) in enumerate(attempts(qual, national)):
        nm = f"{name}_{k}"
        try:
            resp, cached = client.call("getDatiOsservatorio", body_for(meta, qual, classes=classes, **where), nm)
        except Missing:
            rec["tentativi"].append({"soglia": label, "esito": "non raccolta" if nm not in client.skip else "non ritentata"})
            break
        st, counts, total = parse(nm, resp)
        rec["tentativi"].append({"soglia": label, "esito": st})
        log(f"{'(salvata) ' if cached else ''}{nm:28} soglia {label:22} -> {st}{'' if total is None else ' ' + str(total)}")
        if st == "ok":
            return {"soglia": label, "total": total, "counts": counts, "tentativi": rec["tentativi"]}
    return {"non_disponibile": True, "tentativi": rec["tentativi"]}


def national_name(qual):
    # nomi gia' usati nella prima raccolta del 2024
    return {"Quadro": "naz_Quadro_da15000", None: "naz_Totale"}.get(qual, f"naz_{qual}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="usa solo le risposte gia' salvate")
    args = ap.parse_args()

    # l'albero si scarica a ogni esecuzione (file datato), cosi' si vede l'anno nuovo;
    # in --offline si usa l'ultimo salvato
    boot = Client(os.path.join(RAW_ROOT, "_albero"), args.offline)
    if args.offline:
        saved = sorted(f[:-5] for f in os.listdir(boot.raw_dir) if f.startswith("albero_") and f.endswith(".json"))
        if not saved:
            raise Stop("nessun albero salvato per la modalita' --offline")
        tree_name = saved[-1]
    else:
        tree_name = "albero_" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tree, _ = boot.call("getAlberoNavigazione", {"language": "it", "IdAreaTematica": 0}, tree_name)
    year, table_id, table_label = find_table(tree)
    client = Client(os.path.join(RAW_ROOT, year), args.offline)
    struct, _ = client.call("getStrutturaOsservatorio", {"id_osservatorio": table_id, "language": "it"},
                            f"struttura_{table_id}")
    fields = {f["id"]: f for f in struct["definition"]["fields"]}
    meta = {"id": table_id, "name": struct["nome_osservatorio"], "year": year}
    sections = fields["ATECO07_1"]["distinctValues"]
    unknown = [s for s in sections if s not in SECTIONS]
    if unknown:
        raise Stop(f"sezioni ATECO non riconosciute: {unknown}")
    regions = [r for r in fields["regione"]["distinctValues"] if r != "Estero"]
    if [c for c in fields["cl_retr"]["distinctValues"] if c not in CLASS_NAMES]:
        raise Stop("classi di importo cambiate")
    log(f"tavola {table_id} ({table_label}), anno {year}")

    # distribuzioni nazionali (servono anche per le soglie delle altre tavole)
    national = {}
    for q in QUALS + [None]:
        classes = from_class("15000-19999") if q == "Quadro" else None
        nm = national_name(q)
        resp, cached = client.call("getDatiOsservatorio", body_for(meta, q, classes=classes), nm)
        st, counts, total = parse(nm, resp)
        if st != "ok":
            raise Stop(f"distribuzione nazionale rifiutata: {q or 'Totale'}")
        national[q or "Totale"] = {"soglia": "da 15.000" if classes else "nessuna", "total": total, "counts": counts}
        log(f"{'(salvata) ' if cached else ''}{nm:28} -> {total}")

    sez = {}
    for si, s in enumerate(sections):
        letter = SECTIONS[s]
        entry = {"name": s, "quals": {}}
        for q in QUALS:
            entry["quals"][q] = collect(client, meta, f"sez{si:02d}_{q}", national, q, section=s)
        entry["tutte"] = collect(client, meta, f"sezall{si:02d}", national, None, section=s)
        sez[letter] = entry

    reg = {}
    for ri, r in enumerate(regions):
        entry = {"quals": {}}
        for q in REGION_QUALS:
            res = collect(client, meta, f"reg{ri:02d}_{q or 'Totale'}", national, q, region=r)
            if q:
                entry["quals"][q] = res
            else:
                entry["tutte"] = res
        reg[r] = entry

    out = {
        "source": f"INPS, Osservatorio sui lavoratori dipendenti del settore privato non agricolo, "
                  f"tavola {table_id} \"{TABLE_TITLE}\" ({table_label})",
        "index": "Lavoratori con periodo retribuito 'Anno intero' e senza tempo parziale nell'anno, per "
                 "classe di importo della retribuzione annua (imponibile previdenziale)",
        "base_note": "Conteggi pubblicati dall'INPS, senza valori ricavati per differenza. 'soglia' indica le "
                     "classi incluse quando la tavola completa era rifiutata per anonimizzazione: i conteggi "
                     "riguardano solo le classi pubblicate.",
        "licence_note": "Nessuna licenza indicata dal portale: art. 52, comma 2, del CAD (dati di tipo aperto).",
        "year": year,
        "table_id": table_id,
        "published": str(struct.get("DatePub", "")),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classes": [{"label": c, "lo": lo, "hi": hi} for c, lo, hi in CLASSES],
        "italia": national,
        "sezioni": sez,
        "regioni": reg,
    }
    text = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, OUT)

    n_ok = sum(1 for e in sez.values() for r in list(e["quals"].values()) + [e["tutte"]] if not r.get("non_disponibile"))
    n_ok += sum(1 for e in reg.values() for r in list(e["quals"].values()) + [e["tutte"]] if not r.get("non_disponibile"))
    n_na = sum(1 for e in sez.values() for r in list(e["quals"].values()) + [e["tutte"]] if r.get("non_disponibile"))
    n_na += sum(1 for e in reg.values() for r in list(e["quals"].values()) + [e["tutte"]] if r.get("non_disponibile"))
    log(f"Scritto data/inps.json: anno {year}, {n_ok} combinazioni con dati, {n_na} non disponibili")


if __name__ == "__main__":
    try:
        main()
    except Stop as e:
        log(f"STOP: {e}. data/inps.json NON modificato.")
        sys.exit(1)
