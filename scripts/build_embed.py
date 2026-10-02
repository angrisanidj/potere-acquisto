#!/usr/bin/env python3
"""Estrae da index.html il blocco da incorporare e lo scrive in embed.html.

Il blocco e' il div radice <div id="fg-potere-acquisto-2026"> con stile e script,
fino al </div> che lo chiude (contando i div annidati e saltando il contenuto di
<style>, <script> e dei commenti): e' quello da incollare in una scheda HTML di
Ghost (o in qualsiasi altra pagina). Cio' che sta fuori dal div radice in
index.html, come la barra di condivisione, resta solo nella pagina autonoma.
embed.html non si modifica a mano: dopo ogni modifica a index.html si rilancia
questo script, e tests/embed.test.mjs controlla che i due file coincidano.

Uso: python scripts/build_embed.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "index.html")
OUT = os.path.join(ROOT, "embed.html")
START = '<div id="fg-potere-acquisto-2026">'
TOKEN = re.compile(r"<!--.*?-->|<(script|style)\b[^>]*>.*?</\1>|<div\b[^>]*>|</div\s*>", re.S | re.I)


class EmbedError(Exception):
    pass


def extract(html):
    """Blocco dal div radice al </div> che lo chiude, con un a capo finale."""
    i = html.find(START)
    if i == -1:
        raise EmbedError(f"{START} non trovato in index.html")
    if html.find(START, i + 1) != -1:
        raise EmbedError(f"{START} compare piu' di una volta in index.html")
    depth, end = 0, None
    for m in TOKEN.finditer(html, i):
        t = m.group(0)
        if t.startswith("<!--") or m.group(1):
            continue  # commento, <style> o <script>: il contenuto non conta
        depth += -1 if t.startswith("</") else 1
        if depth == 0:
            end = m.end()
            break
    if end is None:
        raise EmbedError("</div> di chiusura del div radice non trovato")
    block = html[i:end]
    # controlli minimi: un solo stile e un solo script, entrambi chiusi, niente
    # parti della pagina intera
    for tag in ("style", "script"):
        if block.count(f"<{tag}>") != 1 or block.count(f"</{tag}>") != 1:
            raise EmbedError(f"il blocco deve contenere esattamente un <{tag}>")
    for tag in ("<html", "<head>", "<body", "</body>"):
        if tag in block:
            raise EmbedError(f"il blocco contiene {tag}")
    return block + "\n"


def main():
    with open(SRC, encoding="utf-8") as f:
        block = extract(f.read())
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(block)
    os.replace(tmp, OUT)
    print(f"embed.html: {len(block.encode('utf-8'))} byte, {block.count(chr(10))} righe")


if __name__ == "__main__":
    try:
        main()
    except EmbedError as e:
        print(f"ERRORE: {e}. embed.html NON modificato.", file=sys.stderr)
        sys.exit(1)
