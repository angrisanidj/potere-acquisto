# Potere d'acquisto dello stipendio

Calcolatore web della perdita di potere d'acquisto di uno stipendio tra un mese
di partenza scelto dall'utente e l'ultimo mese disponibile, basato sull'indice
ISTAT **FOI senza tabacchi** (prezzi al consumo per le famiglie di operai e
impiegati, indice generale al netto dei tabacchi).

Pagina pubblica: https://angrisanidj.github.io/potere-acquisto/

## Come funziona

- Perdita di potere d'acquisto: `1 − I(partenza) / I(ultimo mese)`.
- Stipendio necessario all'ultimo mese per avere lo stesso potere d'acquisto:
  `stipendio di partenza × I(ultimo mese) / I(partenza)`.
- Se si inserisce anche lo stipendio attuale: variazione reale percentuale e
  differenza mensile in euro rispetto allo stipendio rivalutato.
- Grafico del valore reale dello stipendio di partenza mese per mese, espresso
  in euro del mese di partenza.
- Per i mesi dal 1996 al 2001 l'importo si inserisce in lire ed è convertito a
  1.936,27 lire per euro.
- Gli importi si scrivono all'italiana: punto per le migliaia, virgola per i
  decimali (`1.500`, `1.500,50`, `2.500.000`). Le forme ambigue come `1.50` o
  `1,500` vengono rifiutate con un messaggio.

## Dati

`data/foi.json` contiene la serie mensile nazionale dal gennaio 1996, concatenata
in base 2025=100. Lo genera `scripts/update_foi.py` interrogando l'API SDMX
dell'ISTAT (`https://esploradati.istat.it/SDMXWS/rest`, dataflow
`IT1:169_748_DF_DCSP_FOI1B2025_1`, chiave `M.IT..4.00ST`).

Le basi 1995, 2010 e 2015 sono raccordate con i coefficienti ufficiali ISTAT per
l'indice senza tabacchi (file `DCSP_FOI_CR_Ecoicopv2.xlsx`):

| Raccordo          | Coefficiente |
|-------------------|-------------:|
| base 1995 → 2010  | 1,373 |
| base 2010 → 2015  | 1,071 |
| base 2015 → 2025  | 1,214 |

Si usano solo dati definitivi. Prima di scrivere il file lo script controlla che
non manchino mesi, che non ci siano valori ≤ 0, che le variazioni mensili siano
entro ±5% e che l'ultimo mese non sia anteriore a quello già salvato. Se un
controllo fallisce o l'API non risponde (3 tentativi), esce con errore e lascia
il file com'è.

Quando l'ISTAT introdurrà una nuova base, lo script si fermerà segnalando un
`DATA_TYPE` sconosciuto: vanno aggiunti in `BASES` e `SPLICE` il nuovo codice e
il relativo coefficiente di raccordo.

## Aggiornamento automatico

Il workflow `.github/workflows/update-foi.yml` gira il 20 di ogni mese (e a mano
da *Actions → Aggiorna indice FOI → Run workflow*), esegue lo script e committa
`data/foi.json`. Il campo `last_checked` cambia a ogni esecuzione riuscita, così
c'è sempre un commit mensile e GitHub non disattiva il workflow per inattività.
Se lo script fallisce, il job fallisce e non committa nulla.

## Incorporare la pagina in un altro sito

Copiare tutto il blocco `<div id="fg-potere-acquisto-2026"> … </div>` da
`index.html`: contiene stile e script, con tutto il CSS sotto quell'ID e il
JavaScript in una IIFE. I dati vengono letti dall'URL assoluto di GitHub Pages,
che risponde con `Access-Control-Allow-Origin: *`, quindi il calcolatore
funziona anche su altri domini. Se i dati non si caricano compare un messaggio
d'errore: non c'è una copia di riserva nel codice.

## Sviluppo locale

```bash
python scripts/update_foi.py              # aggiorna data/foi.json
python -m http.server 8000                # poi apri http://localhost:8000/
node --test tests/parser.test.mjs         # test del parser degli importi
```

In locale (`localhost` o `127.0.0.1`) la pagina legge `data/foi.json` con un
percorso relativo invece che dall'URL di GitHub Pages.

## Nota metodologica

L'indice misura i prezzi di un paniere medio: l'inflazione vissuta da ciascuna
famiglia può essere diversa. Conviene usare lo stipendio netto, perché il lordo
risente anche delle variazioni di tasse e contributi.
