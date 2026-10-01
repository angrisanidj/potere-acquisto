# Potere d'acquisto dello stipendio

Calcolatore web della perdita di potere d'acquisto di uno stipendio tra un mese
di partenza scelto dall'utente e l'ultimo mese disponibile, basato sull'indice
ISTAT **FOI senza tabacchi** (prezzi al consumo per le famiglie di operai e
impiegati, indice generale al netto dei tabacchi) e, a scelta, sugli indici ISTAT
delle **retribuzioni contrattuali** per dipendente.

Pagina pubblica: https://angrisanidj.github.io/potere-acquisto/

Elaborazione: Daniele Angrisani ([@putino](https://x.com/putino)).

## Come funziona

- Perdita di potere d'acquisto a stipendio fermo: `1 − I(partenza) / I(arrivo)`.
- Stipendio necessario all'arrivo per avere lo stesso potere d'acquisto:
  `stipendio di partenza × I(arrivo) / I(partenza)`.
- Opzione **"Considera gli aumenti del contratto"** (attiva di default): lo
  stipendio cresce come l'indice delle retribuzioni contrattuali del comparto
  scelto, `R(arrivo) / R(partenza)`. Il selettore del comparto ha ricerca e
  struttura ad albero; il predefinito è il totale economia. L'opzione si
  disattiva, con una spiegazione, per partenze prima del 2005 o prima
  dell'inizio della serie del comparto.
- Risultato principale: se si inserisce lo stipendio attuale, la sua variazione
  reale; altrimenti, con l'opzione contratto attiva, la perdita considerando gli
  aumenti del contratto; altrimenti la perdita a stipendio fermo. Gli altri
  valori compaiono sotto.
- Con l'opzione contratto attiva tutti i confronti si fermano all'ultimo mese
  comune alle due serie, indicato in pagina.
- Grafico del valore reale dello stipendio mese per mese, in euro del mese di
  partenza, con la linea dello stipendio rivalutato col contratto.
- Export PNG a doppia risoluzione, disegnato su canvas senza librerie.
- Per i mesi dal 1996 al 2001 l'importo si inserisce in lire ed è convertito a
  1.936,27 lire per euro.
- Gli importi si scrivono all'italiana: punto per le migliaia, virgola per i
  decimali (`1.500`, `1.500,50`, `2.500.000`). Le forme ambigue come `1.50` o
  `1,500` vengono rifiutate con un messaggio.

## Dati

### Prezzi: `data/foi.json`

Serie mensile nazionale dal gennaio 1996, concatenata in base 2025=100. La genera
`scripts/update_foi.py` interrogando l'API SDMX dell'ISTAT
(`https://esploradati.istat.it/SDMXWS/rest`, dataflow
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
il file com'è. Quando l'ISTAT introdurrà una nuova base, lo script si fermerà
segnalando un `DATA_TYPE` sconosciuto: vanno aggiunti in `BASES` e `SPLICE` il
nuovo codice e il relativo coefficiente di raccordo.

### Retribuzioni: `data/retribuzioni.json`

Indici mensili delle retribuzioni contrattuali per dipendente (esclusi i
dirigenti), base dicembre 2021=100, per 113 raggruppamenti contrattuali: totale
economia, settore privato, pubblica amministrazione, settori e comparti. L'API
non arriva al singolo CCNL. Li genera `scripts/update_retribuzioni.py` (dataflow
`IT1:155_318_DF_DCSC_RETRCONTR1C_4`, chiave `M.IT.WAGE_E_2021.N.10.`).

- La serie in base 2021 è già ricostruita e raccordata da ISTAT dal gennaio 2005:
  non servono coefficienti. Prima del 2005 l'API non ha dati.
- Validazioni come per il FOI, con soglie di variazione mensile adatte ai rinnovi
  contrattuali: ±10% per il totale economia, ±50% per i comparti. Lo script
  fallisce anche se l'ultimo mese è più vecchio di 4 mesi (un cambio di base crea
  un nuovo dataflow).
- `temporary_peaks` elenca i mesi con un aumento oltre il 3% che rientra di oltre
  il 3% il mese dopo (oggi dicembre 2023, anticipo una tantum nella PA): la pagina
  usa al loro posto il mese precedente e lo segnala.

## Aggiornamento automatico

Il workflow `.github/workflows/update-foi.yml` gira il 20 di ogni mese (e a mano
da *Actions → Aggiorna indice FOI → Run workflow*). I due script sono passi
indipendenti: se uno fallisce lascia intatto il proprio file, l'aggiornamento
dell'altro viene comunque committato e il job fallisce nell'ultimo passo. Il
campo `last_checked` cambia a ogni esecuzione riuscita, così c'è sempre un commit
mensile e GitHub non disattiva il workflow per inattività.

Il log riporta un avviso (`::warning::`, senza far fallire il job) quando l'ultimo
mese delle retribuzioni salta oltre il 5% sul totale economia o sulla PA, e
quando compare un picco temporaneo nuovo.

## Incorporare la pagina in un altro sito

Copiare tutto il blocco `<div id="fg-potere-acquisto-2026"> … </div>` da
`index.html`: contiene stile e script, con tutto il CSS sotto quell'ID e il
JavaScript in una IIFE. I dati vengono letti dall'URL assoluto di GitHub Pages,
che risponde con `Access-Control-Allow-Origin: *`, quindi il calcolatore
funziona anche su altri domini. Se i prezzi non si caricano compare un messaggio
d'errore; se mancano solo le retribuzioni, l'opzione contratto si disattiva con
un avviso. Non ci sono copie di riserva dei dati nel codice.

## Sviluppo locale

```bash
python scripts/update_foi.py              # aggiorna data/foi.json
python scripts/update_retribuzioni.py     # aggiorna data/retribuzioni.json
python -m http.server 8000                # poi apri http://localhost:8000/
node --test tests/parser.test.mjs         # test del parser degli importi
```

In locale (`localhost` o `127.0.0.1`) la pagina legge i file in `data/` con un
percorso relativo invece che dall'URL di GitHub Pages.

## Nota metodologica

L'indice dei prezzi misura un paniere medio: l'inflazione vissuta da ciascuna
famiglia può essere diversa. Conviene usare lo stipendio netto, perché il lordo
risente anche delle variazioni di tasse e contributi.

L'indice delle retribuzioni contrattuali misura gli aumenti previsti dai
contratti (minimi tabellari e voci contrattuali), non la crescita effettiva della
busta paga, che include anche anzianità, superminimi e promozioni. Riguarda le
retribuzioni lorde: a parità di regole fiscali, applicare al netto la crescita
del lordo tende a sovrastimarla, per effetto della progressività dell'IRPEF.
