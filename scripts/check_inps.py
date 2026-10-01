#!/usr/bin/env python3
"""Controllo mensile leggero: una sola richiesta all'albero di navigazione degli
Osservatori INPS per vedere se e' comparsa la tavola "per classi di importo"
di un anno piu' recente di quello in data/inps.json.

Non scarica dati e non modifica file. Emette ::warning:: quando c'e' un anno
nuovo (la raccolta si lancia a mano con il workflow "Raccolta INPS") o quando
il controllo non riesce; in nessun caso fa fallire il job.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inps_collect import TABLE_TITLE, Stop, find_table  # noqa: E402

import urllib.request  # noqa: E402
import gzip  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://servizi2.inps.it/servizi/osservatoristatistici/api/getAlberoNavigazione/"


def main():
    with open(os.path.join(ROOT, "data", "inps.json"), encoding="utf-8") as f:
        have = json.load(f)["year"]
    req = urllib.request.Request(URL, data=json.dumps({"language": "it", "IdAreaTematica": 0}).encode(),
                                 headers={"Content-Type": "application/json", "Accept-Encoding": "gzip",
                                          "User-Agent": "potere-acquisto/1.0 (https://github.com/angrisanidj/potere-acquisto)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        year, table_id, label = find_table(json.loads(raw.decode("utf-8-sig")))
    except (Stop, OSError, ValueError) as e:
        print(f"::warning::Controllo INPS non riuscito ({e}): verificare a mano l'albero degli Osservatori.")
        return
    if year > have:
        print(f"::warning::INPS ha pubblicato la tavola \"{TABLE_TITLE}\" per il {year} (id {table_id}): "
              f"lanciare a mano il workflow \"Raccolta INPS\". Dati attuali: {have}.")
    else:
        print(f"INPS: ultima tavola per classi di importo {year} (id {table_id}), gia' in data/inps.json.")


if __name__ == "__main__":
    main()
