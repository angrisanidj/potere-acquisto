#!/usr/bin/env python3
"""Estrae da index.html il blocco da incorporare e lo scrive in embed.html.

Il blocco e' il div radice <div id="fg-potere-acquisto-2026"> con stile e script,
fino all'ultimo </div> prima di </body>: e' quello da incollare in una scheda
HTML di Ghost (o in qualsiasi altra pagina). embed.html non si modifica a mano:
dopo ogni modifica a index.html si rilancia questo script, e
tests/embed.test.mjs controlla che i due file coincidano.

Uso: python scripts/build_embed.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "index.html")
OUT = os.path.join(ROOT, "embed.html")
START = '<div id="fg-potere-acquisto-2026">'


class EmbedError(Exception):
    pass


def extract(html):
    """Blocco dal div radice all'ultimo </div> prima di </body>, con un a capo finale."""
    i = html.find(START)
    if i == -1:
        raise EmbedError(f"{START} non trovato in index.html")
    if html.find(START, i + 1) != -1:
        raise EmbedError(f"{START} compare piu' di una volta in index.html")
    body_end = html.rfind("</body>")
    if body_end < i:
        raise EmbedError("</body> mancante o prima del div radice")
    j = html.rfind("</div>", i, body_end)
    if j == -1:
        raise EmbedError("</div> di chiusura del div radice non trovato")
    block = html[i:j + len("</div>")]
    # controlli minimi: un solo stile e un solo script, entrambi chiusi, niente
    # parti della pagina intera
    for tag in ("style", "script"):
        if block.count(f"<{tag}>") != 1 or block.count(f"</{tag}>") != 1:
            raise EmbedError(f"il blocco deve contenere esattamente un <{tag}>")
    for tag in ("<html", "<head>", "<body", "</body>"):
        if tag in block:
            raise EmbedError(f"il blocco contiene {tag}")
    if html[j + len("</div>"):body_end].strip():
        raise EmbedError("contenuto fra la chiusura del div radice e </body>")
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
