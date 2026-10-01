# Potere d'acquisto dello stipendio — note per Claude Code

Calcolatore web della perdita di potere d'acquisto di uno stipendio netto e del
confronto della retribuzione con il settore. Lavoro per Daniele Angrisani
(@putino), destinato anche all'incorporamento su altri siti (Fanpage.it,
FocusAmerica). Lingua di lavoro: italiano.

- Pagina pubblica: https://angrisanidj.github.io/potere-acquisto/
- Repository: https://github.com/angrisanidj/potere-acquisto (branch `main`, GitHub Pages da `main`, root)
- Copia locale: `C:\Progetti\potere-acquisto` (Windows, Python 3.13 con `py`, Node 24, `gh` autenticato,
  `gh auth setup-git` già fatto)

Si lavora per fasi: l'utente chiede di fermarsi alla fine di ognuna per verificare.
Commit e push solo quando l'utente li chiede.

## Struttura

| File | Cosa contiene |
|---|---|
| `index.html` | Tutta la pagina: un solo `<div id="fg-potere-acquisto-2026">` con `<style>` e `<script>` (IIFE) dentro |
| `tests/parser.test.mjs` | Test del parser degli importi in formato italiano (`node --test tests/parser.test.mjs`); estrae il blocco fra `// --- parser-start ---` e `// --- parser-end ---` di `index.html` |
| `scripts/update_foi.py` | FOI senza tabacchi → `data/foi.json`; contiene `http_get` (tentativi, limite ISTAT) usato dagli altri script |
| `scripts/update_retribuzioni.py` | Retribuzioni contrattuali per comparto → `data/retribuzioni.json` |
| `scripts/update_indice_ateco.py` | Coefficienti dell'indice contrattuale per sezione → `data/indice_ateco.json` |
| `scripts/check_inps.py` | Controllo mensile dell'albero degli Osservatori INPS (solo `::warning::`) |
| `scripts/inps_collect.py` | Raccolta a mano della tavola INPS → `data/inps.json` + risposte grezze in `data/inps_raw/<anno>/` |
| `scripts/update_racli.py`, `scripts/update_ses.py`, `data/racli.json`, `data/ses.json` | **In dismissione**: non più nel workflow; la pagina li usa ancora finché il blocco retribuzione non passa all'INPS |
| `.github/workflows/update-foi.yml` | Workflow mensile (cron il 20 alle 06:00 UTC + `workflow_dispatch`) |
| `.github/workflows/collect-inps.yml` | Workflow manuale "Raccolta INPS" |
| `README.md` | Documentazione pubblica (va aggiornata quando il blocco passa all'INPS) |

## Fonti e decisioni

**Prezzi — FOI senza tabacchi (ISTAT).** Dataflow `IT1:169_748_DF_DCSP_FOI1B2025_1`, chiave
`M.IT..4.00ST`, serie dal 1996-01 concatenata in base 2025=100 con i coefficienti ufficiali per
l'indice senza tabacchi (file `DCSP_FOI_CR_Ecoicopv2.xlsx`): 1,373 (1995→2010), 1,071 (2010→2015),
1,214 (2015→2025). Raccordo verificato dall'utente su Rivaluta. Solo dati definitivi; validazioni:
nessun mese mancante, valori > 0, variazione mensile entro ±5%, ultimo mese non anteriore al salvato.
Prima del 2002 l'importo è in lire (1.936,27 lire per euro).

**Contratto — retribuzioni contrattuali per comparto (ISTAT).** `IT1:155_318_DF_DCSC_RETRCONTR1C_4`,
chiave `M.IT.WAGE_E_2021.N.10.` (per dipendente, base dicembre 2021, esclusi i dirigenti), 113
raggruppamenti contrattuali (non singoli CCNL: in pagina si dice "comparto"), dati dal 2005, già
raccordati da ISTAT. Soglie di variazione mensile: ±10% totale economia (Z3620), ±50% comparti; errore se
l'ultimo mese ha più di 4 mesi. Picchi temporanei (salita oltre +3% che rientra di oltre il 3% il mese
dopo, es. dicembre 2023 nella PA): sostituiti dal mese precedente, `::warning::` se ne compare uno nuovo o
se l'ultimo mese salta oltre il 5% su totale economia o PA. Comparti della PA: nessun confronto
retributivo.

**Indice per sezione (ISTAT).** `IT1:155_358_DF_DCSC_RETRATECO1_7`, chiave `M.IT.WAGE_E_2021.N.10.`:
coefficiente = indice dell'ultimo mese / media dell'anno dei dati INPS, per sezione ATECO; per Italia
e regioni `0015` (industria e servizi di mercato B–N), perché l'indice non ha il solo settore privato
(`0037` esiste nella codelist ma è vuoto). La sezione T non ha serie: si usa `0015` e lo si dichiara.

**Confronto retributivo — INPS, tavola 526 (2024).** Osservatorio sui lavoratori dipendenti del settore
privato non agricolo, "Lavoratori dipendenti per classi di importo della retribuzione annua e
cittadinanza". Misura: imponibile previdenziale annuo dei lavoratori con periodo retribuito "Anno intero"
e "Presenza tempo parziale nell'anno" = No; 13 classi da "Fino a 5000" a "80000 ed oltre" (classe
aperta). Dati per Italia, 18 sezioni ATECO (B–T, senza A e O) e 20 regioni (escluso "Estero"), per
qualifica e per tutte le qualifiche: 151 combinazioni con dati, 57 non disponibili (rifiutate per
anonimizzazione anche al secondo tentativo, oppure sezione T non ritentata per decisione dell'utente
dopo un errore SAS del server). Totali nazionali verificati con l'export manuale: operai 3.244.096,
impiegati 3.169.824, quadri da 15.000 € 475.121, dirigenti 122.796. Condizioni d'uso: il portale non
indica licenze → art. 52, comma 2, del CAD (dati pubblicati senza licenza = dati di tipo aperto). La
nota metodologica INPS conferma solo che sono inclusi i dipendenti pubblici a tempo determinato (non
parla di scuola o supplenti: niente note sull'istruzione).

**RACLI (ISTAT, retribuzioni orarie) ed Eurostat SES (professioni)**: in dismissione, da togliere dalla
pagina e dal repository con il prossimo passo.

## Regole fisse

- **API ISTAT**: limite di 5 richieste al minuto per IP, oltre scatta un blocco di 1–2 giorni (è successo il
  2026-10-01; si è risolto cambiando IP con il riavvio del router). Almeno **40 s** fra due richieste,
  anche fra script diversi (orario dell'ultima richiesta in un file temporaneo, vedi `http_get`).
- **API INPS** (`https://servizi2.inps.it/servizi/osservatoristatistici/api/`, POST JSON, nessun login):
  almeno **12 s** fra due richieste; ogni risposta grezza salvata e mai richiesta di nuovo.
  - Corpo **identico a quello del browser**: righe e colonne con `id` = **nome della gerarchia**
    (`"CLASSE DI RETRIBUZIONE ANNUA"`, `"Periodo retribuito datore"`), non l'id del campo (altrimenti errore
    Base-64); filtri `{"id": campo, "label": Name della gerarchia, "values": [...]}`; filtro anno con label
    **`"Anno-"`** (con il trattino); `"language": ""`; `nome_osservatorio`; `totalRow`/`totalColumn`/
    `subtotalRow`/`subtotalColumn` a `true`. Vedi `body_for` in `scripts/inps_collect.py`.
  - **Una qualifica per richiesta.** Tavola rifiutata (`messageType: "Anonimizzazione"`): **un solo**
    nuovo tentativo con soglia (quadri: da 15.000 → da 20.000; dirigenti: nessuna → da 20.000; le altre:
    esclusa la fascia più bassa della distribuzione nazionale corrispondente), poi "non disponibile".
  - **Mai valori ricavati per differenza** fra tavole diverse.
  - **Stop alla prima risposta inattesa** (né dati né rifiuto per anonimizzazione), senza scrivere il JSON.
- **Testi della pagina**: mai "oggi", sempre il mese ("ad agosto 2026", "a gennaio 2021"). Nessun importo
  reale senza il mese della moneta ("1.500 € di agosto 2026 valgono 1.226 € di gennaio 2021").
  Etichetta testuale PERDITA/GUADAGNO con simbolo, anche nel PNG. Numeri con `toLocaleString('it-IT')`
  ma con il punto delle migliaia forzato (il CLDR italiano non raggruppa i numeri di 4 cifre: vedi `fmt`).
- **Incorporamento**: tutto il CSS sotto `#fg-potere-acquisto-2026` (nessun selettore globale), JS in una
  IIFE, font di sistema, nessuna libreria o risorsa esterna, palette #003F87 / #0070C0 / #00A6D6 /
  #E8F4FD / testo #1A1A2E / secondario #666680 / bordi #D0D8E8, radice con `margin:28px auto !important`,
  breakpoint a 600px. Dati letti dagli URL assoluti di GitHub Pages (relativi su localhost/127.0.0.1);
  se il FOI non si carica, errore con pulsante "Riprova" e nessun dato di riserva.
- **Prima di ogni commit della pagina**: fermarsi e mandare gli screenshot a **320 px e 1280 px** (più il PNG
  e gli stati particolari quando toccati). Le immagini molto alte non arrivano al cellulare: a 320 px
  mandare la pagina divisa in sezioni.
- Ogni script di aggiornamento: tentativi con attesa, scrittura atomica, nessuna sovrascrittura se un
  controllo fallisce; `last_checked` cambia a ogni esecuzione riuscita (commit mensile garantito).

## Workflow

- **Mensile** (`update-foi.yml`, ubuntu-24.04 fisso, timeout 60 min, `PYTHONUNBUFFERED=1`): FOI,
  retribuzioni contrattuali, indice per sezione come passi indipendenti (`continue-on-error`), controllo
  INPS (solo avvisi), commit "Aggiorna dati (FOI: …, retribuzioni: …, indice per sezione: …)" con
  `git pull --rebase`, ultimo passo con `::error::` per lo script fallito. Ultimo run manuale riuscito:
  2026-10-01, controllo INPS raggiungibile dai server GitHub.
- **Manuale** "Raccolta INPS" (`collect-inps.yml`, timeout 4 h): si lancia quando il controllo mensile
  segnala una tavola INPS di un anno nuovo; `scripts/inps_collect.py --offline` ricostruisce
  `data/inps.json` dalle sole risposte salvate. `data/inps_raw/2024/_non_ritentare.json` elenca le
  richieste da non ripetere.

## Prova in locale

```bash
py -m http.server 8765 --bind 127.0.0.1     # poi http://127.0.0.1:8765/
node --test tests/parser.test.mjs
```
Screenshot: Edge headless con `--remote-debugging-port`, viewport 320/1280 e
`Page.captureScreenshot` con `captureBeyondViewport` (lo script di supporto stava nella cartella
temporanea della sessione, non nel repository).

## Stato attuale (2026-10-01)

Online: calcolatore sul netto in stile "Griglia" (proposta 1b di Claude Design: passi 01 Quando, 02 Quanto,
03 Contratto; numero grande; tabella di riepilogo; riquadri; note su tre colonne), opzione contratto per
comparto, grafico SVG, export PNG; blocco "Come si colloca la tua retribuzione" ancora basato su RACLI
(paga oraria) con valore di riferimento per professione (Eurostat SES). Dati INPS e indice per sezione già
nel repository e aggiornati, non ancora usati dalla pagina.

## Prossimo passo

Passare il blocco "Come si colloca la tua retribuzione" all'INPS:
- niente ore settimanali (il confronto è con i lavoratori a tempo pieno per tutto l'anno: nota in pagina);
- input: RAL (più premi e straordinari facoltativi), sezione ATECO tra le 18, regione facoltativa,
  qualifica facoltativa con "Non lo so" (= tutte le qualifiche);
- percentile stimato per interpolazione nelle classi, arrotondato; RAL riportata ai valori dell'anno INPS
  con il coefficiente della sezione (Italia e regioni: `0015`);
- barra con decili e quartili; per le combinazioni con soglia, dire che il percentile riguarda solo i
  lavoratori delle classi pubblicate; quantili nella classe aperta come "oltre 80.000 €";
- combinazioni non disponibili: distribuzione nazionale della qualifica, dichiarata;
- dirigenti: niente barra né mediana, solo la quota oltre 80.000 € (Italia 93,2%);
- togliere RACLI e professione dalla pagina e dal repository (script, JSON, note, README);
- dati 2024 aggiornati con l'indice di sezione e dichiarati come stima;
- comparto della PA: confronto non disponibile, come ora.

## In sospeso

- Calcolo del netto dalla RAL (anno in corso), con una procedura annuale documentata in
  `AGGIORNAMENTO_FISCALE.md` (da creare).
- Risposta dell'INPS alla mail dell'utente (sull'uso dell'API e dei dati).
- Passaggio futuro del runner da ubuntu-24.04 a ubuntu-26.04, con un avvio di prova.
- Correggere `formatIT` nella skill `il-giornalista`: `toLocaleString('it-IT')` non mette il punto nei numeri
  di 4 cifre (1835 invece di 1.835).
