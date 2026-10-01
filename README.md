# Potere d'acquisto dello stipendio

Calcolatore web della perdita di potere d'acquisto di uno stipendio tra un mese
di partenza scelto dall'utente e l'ultimo mese disponibile, basato sull'indice
ISTAT **FOI senza tabacchi** (prezzi al consumo per le famiglie di operai e
impiegati, indice generale al netto dei tabacchi) e, a scelta, sugli indici ISTAT
delle **retribuzioni contrattuali** per dipendente. Un secondo blocco confronta
la retribuzione annua lorda con la distribuzione INPS dei dipendenti del settore
privato a tempo pieno.

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
- Blocco **"Come si colloca la tua retribuzione"**: RAL (più premi e
  straordinari facoltativi), sezione ATECO, regione e qualifica facoltative.
  Mostra il percentile stimato, lo scarto dalla mediana e una barra con decili
  e quartili, per la sezione (o l'Italia) e, se scelta, per la regione. Il
  settore si precompila dal comparto contrattuale quando questo ricade in una
  sola sezione. Per i comparti della pubblica amministrazione il confronto non
  è disponibile.
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

### Confronto retributivo: `data/inps.json`

INPS, Osservatorio sui lavoratori dipendenti del settore privato non agricolo,
tavola 526 "Lavoratori dipendenti per classi di importo della retribuzione annua
e cittadinanza" (anno 2024). Si contano i lavoratori con periodo retribuito
"Anno intero" e senza tempo parziale nell'anno, per 13 classi di imponibile
previdenziale annuo (fino a "80000 ed oltre", classe aperta): Italia, 18 sezioni
ATECO (B–T) e 20 regioni, per qualifica e per tutte le qualifiche.

- Quando l'INPS rifiuta una tavola per anonimizzazione si fa un solo nuovo
  tentativo con una soglia (campo `soglia`: `da 15.000`, `da 20.000` o
  `esclusa 5000-9999`); i conteggi riguardano solo le classi pubblicate. Se
  anche il secondo tentativo è rifiutato la combinazione è `non_disponibile` e
  la pagina usa la distribuzione nazionale della qualifica, dichiarandolo.
- Nessun valore è ricavato per differenza fra tavole diverse.
- Percentile e quantili si stimano per interpolazione lineare dentro le classi;
  nella classe aperta non si stima (quantili "oltre 80.000 €"). Per i dirigenti
  la pagina mostra solo la quota nella classe aperta.
- Lo genera a mano `scripts/inps_collect.py` (workflow manuale *Raccolta INPS*,
  `.github/workflows/collect-inps.yml`), che salva ogni risposta grezza in
  `data/inps_raw/<anno>/` e non la richiede di nuovo; con `--offline` ricostruisce
  il JSON dalle sole risposte salvate. Va lanciato quando il controllo mensile
  (`scripts/check_inps.py`) segnala la tavola di un anno nuovo.
- Il portale non indica licenze: si applica l'art. 52, comma 2, del Codice
  dell'amministrazione digitale (dati pubblicati senza licenza = dati di tipo
  aperto).

### Aggiornamento del confronto: `data/indice_ateco.json`

Coefficienti per portare i valori INPS all'ultimo mese disponibile: indice ISTAT
delle retribuzioni contrattuali per dipendente per sezione ATECO
(`IT1:155_358_DF_DCSC_RETRATECO1_7`) dell'ultimo mese diviso per la media
dell'anno dei dati INPS. Per l'Italia, le regioni e la sezione T (che l'indice
non ha) si usa `0015`, industria e servizi di mercato (B–N), perché l'indice
non ha il solo settore privato. È una stima: non comprende la crescita oltre i
minimi contrattuali. Lo genera `scripts/update_indice_ateco.py`.

## Aggiornamento automatico

Il workflow `.github/workflows/update-foi.yml` gira il 20 di ogni mese (e a mano
da *Actions → Aggiorna indice FOI → Run workflow*). FOI, retribuzioni
contrattuali e indice per sezione sono passi indipendenti: se uno fallisce lascia
intatto il proprio file, gli aggiornamenti degli altri vengono comunque
committati e il job fallisce nell'ultimo passo. Un ultimo controllo
(`scripts/check_inps.py`) segnala con un avviso una nuova tavola INPS. Le
richieste all'ISTAT sono distanziate di almeno 40 secondi (limite di 5 al minuto
per IP). Il
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
un avviso; se mancano i dati INPS o l'indice per sezione, il blocco del confronto
retributivo mostra un messaggio al posto dei campi. Non ci sono copie di riserva dei dati nel codice.

## Sviluppo locale

```bash
python scripts/update_foi.py              # aggiorna data/foi.json
python scripts/update_retribuzioni.py     # aggiorna data/retribuzioni.json
python scripts/update_indice_ateco.py     # aggiorna data/indice_ateco.json
python scripts/inps_collect.py --offline  # ricostruisce data/inps.json dalle risposte salvate
python -m http.server 8000                # poi apri http://localhost:8000/
node --test tests/parser.test.mjs tests/inps.test.mjs   # parser degli importi e calcoli INPS
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

Il confronto retributivo riguarda solo chi ha lavorato tutto l'anno a tempo
pieno: per chi lavora part time o solo una parte dell'anno non è omogeneo. La
retribuzione INPS è l'imponibile previdenziale (comprende tredicesima,
straordinari e premi, non il TFR).
