# Changelog

Le versioni del gestionale New Style Hair. Il formato è
`MAGGIORE.MINORE.CORREZIONE` ([SemVer](https://semver.org/lang/it/)): una
correzione alza l'ultimo numero, una funzionalità nuova quello di mezzo, un
cambiamento incompatibile il primo.

Le voci le scrive `scripts/release.py prepare` dai commit di ogni rilascio;
vedi «CI e flusso di rilascio» in `CLAUDE.md`.

## [1.3.0] — 2026-10-08

### Novità

- sell products when checking out an appointment

## [1.2.5] — 2026-10-08

### Correzioni

- worker emails from noreply, admin address masked at boot

## [1.2.4] — 2026-10-08

Solo manutenzione: documentazione, test, configurazione.

## [1.2.3] — 2026-10-08

### Correzioni

- lists show every record, not just the first page

## [1.2.2] — 2026-10-06

### Correzioni

- calendar: an extra working day only changes its own collaborator's column

## [1.2.1] — 2026-10-06

### Correzioni

- calendar: extra working days start the grid early; portal never books past 19:00

## [1.2.0] — 2026-10-06

### Novità

- auth: rate limits per email address, phone shown and correctable on the WhatsApp code screen

## [1.1.0] — 2026-09-29

### Novità

- calendar: half-hour labels, grid 8–19, after-closing band 19–20 for the salon

## [1.0.0] — 2026-09-29

Prima versione numerata: il gestionale com'è in produzione a questa data.

### Novità

- Calendario per collaboratore (giorno, settimana, telefono) con stati,
  colori per servizio, servizio accanto all'orario, permessi e assenze
  disegnati, spostamento e ridimensionamento degli appuntamenti.
- «Incassa» dall'appuntamento (contanti o carta) e Cassa con incassi,
  spese, buoni regalo, prodotti e magazzino.
- Portale clienti: prenotazione con uno o più servizi, con account o senza
  (nome, cognome e codice WhatsApp), lista d'attesa, area personale.
- Registrazione con verifica di email e numero; collegamento automatico alle
  schede già esistenti per email o per numero e nome.
- Notifiche su WhatsApp dal numero del salone (conferme, promemoria,
  codici) e per email; chat WhatsApp nel gestionale con foto e vocali,
  avvisi all'arrivo di un messaggio.
- Clienti, collaboratori con ordine e orari, servizi, impostazioni, team e
  accessi, messaggi ai clienti.
