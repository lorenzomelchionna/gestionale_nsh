# TODO — Configurazione notifiche (Email + WhatsApp)

## STATO: EMAIL E WHATSAPP FUNZIONANTI — WHATSAPP SUL FISSO DEL SALONE (aggiornato 2026-09-22)

| Canale | Stato | Provider | Via |
|--------|-------|----------|-----|
| **Email** | ✅ Funziona | Brevo | HTTP API (HTTPS) |
| **WhatsApp** | ✅ Funziona dal 2026-09-17 (numero ponte); passato al **fisso del salone** `+39 0825 1728148` il 2026-09-22 | Twilio | HTTP API — template Meta approvati |

Il passaggio al fisso è fatto: dettagli, cosa resta aperto (nome business,
conferma ricezione) nella voce «WhatsApp produzione sul fisso» qui sotto.

> ⚠️ **Questa intestazione è stata sbagliata due volte, in versi opposti.**
>
> - Fino al 17 settembre diceva «EMAIL + WHATSAPP FUNZIONANTI IN
>   PRODUZIONE». Per WhatsApp era vero solo per il messaggio di prova del 19
>   giugno: da allora ogni invio è fallito sulla Sandbox — `63015`,
>   destinatario non iscritto alla Sandbox; `21211`, numero non valido (i
>   clienti demo di luglio). Il codice non se ne accorgeva perché l'errore
>   arriva da Twilio *dopo* la richiesta: la richiesta va a buon fine, la
>   consegna fallisce, e il registro di Twilio non lo guardava nessuno.
> - Dal 17 al 22 settembre diceva «WHATSAPP NON CONSEGNA NIENTE — Sandbox»,
>   mentre il canale era già acceso e provato nelle due direzioni.
>
> Regola che ne esce: questa tabella è la prima cosa che si legge, quindi
> quando lo stato di un canale cambia si aggiorna **prima lei**, poi il
> resto.

La pipeline email (appuntamento confermato → Redis → Celery worker → invio →
consegnato) resta quella verificata il 19 giugno.

### Perché NON si usa più SMTP per le email
Railway throttla/blocca l'SMTP in uscita (timeout). Si è passati a **Brevo HTTP API**
(free tier 300/giorno). `email.py` prova Brevo se `BREVO_API_KEY` è set, altrimenti
fallback SMTP (solo dev locale). Mittente verificato: `newstylehair2019@gmail.com`.

### Bug risolti (questa sessione)
1. Servizio Celery worker mancante → creato `celery-worker`
2. `worker-start.sh` senza beat → aggiunto `--beat`
3. `Event loop is closed` nei task → engine NullPool per run (`create_task_session_factory`)
4. SMTP unreachable/timeout su Railway → Brevo HTTP API
5. PUT /settings/booking 500 (MissingGreenlet) → `db.refresh` prima di model_validate

### Variabili settate in produzione (backend + worker)
`BREVO_API_KEY`, `EMAILS_FROM_EMAIL=newstylehair2019@gmail.com`,
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
`TWILIO_WHATSAPP_FROM=whatsapp:+3908251728148` (fisso del salone dal
2026-09-22; prima il numero ponte `+16893448830` dal 2026-09-17, prima
ancora la Sandbox `+14155238886`), `TWILIO_TEMPLATE_CONFERMA`,
`TWILIO_TEMPLATE_PROMEMORIA`, `TWILIO_TEMPLATE_VERIFICA`, `SMTP_*`
(fallback). `whatsapp_enabled=true` in BookingConfig.

### Restano (NON bloccanti)
- [x] ~~**Conferme per appuntamenti già passati**~~ — **corretto e
  rilasciato il 2026-09-23**, prima che il salone caricasse lo storico.

  `create_appointment` lato gestionale accoda sempre una conferma, e in
  tutta la catena — endpoint, task Celery, `notify_booking_confirmation` —
  non c'era **nessun controllo sulla data**. Per l'uso normale non si
  vedeva: si confermano appuntamenti futuri. Si sarebbe visto al primo
  caricamento dello storico, dove ogni riga inserita manda alla cliente una
  conferma via email **e** WhatsApp per una data trascorsa.

  Non solo rumore: i template utility fuori dalla finestra di 24 ore si
  pagano, e una raffica di messaggi inattesi è il modo più rapido per far
  segnalare un numero WhatsApp — sul fisso, attivato il giorno prima e
  senza storico di invii a difenderlo, sarebbe stato il primo banco di
  prova della sua reputazione.

  La guardia sta in `notify_booking_confirmation` (`app/utils/notifications.py`)
  e **non nell'endpoint**, così copre anche il passaggio `pending →
  confirmed` e qualunque chiamante venga aggiunto dopo. I promemoria non
  erano interessati: interrogano una finestra futura, lo storico non li
  sveglia.

  Test scritto prima della correzione (`tests/test_conferma_appuntamenti_passati.py`):
  i due casi «passato» rossi per il motivo giusto — i messaggi partivano
  davvero — e il caso «futuro» già verde, a dire che la guardia non stava
  per spegnere il caso normale.

  Nella stessa PR, **i contatti facoltativi lato gestionale**: chiesto di
  poter registrare clienti senza email, o senza né email né telefono, solo
  da admin, e di completare i dati dopo.
  ~~«Si è scoperto che funzionava già da capo a fondo»~~ — **questa riga
  era falsa, per metà.** Creare una scheda senza contatti funzionava
  davvero. **Completarla dopo no**: l'endpoint c'era e il test lo provava,
  ma nell'interfaccia **non esisteva nessun pulsante** per modificare o
  eliminare un cliente — `updateClient` importato e mai chiamato fin dal
  commit iniziale, `deleteClient` mai scritto. L'ha scoperto Flavia lo
  stesso giorno, arrivando a un vicolo cieco: «Crea accesso portale» le
  diceva di aggiungere l'email «dalla modifica cliente», che non c'era.
  Corretto nella voce «Modifica ed elimina cliente» più sotto.

  La lezione è la stessa che questo file ha già scritto in cima per
  WhatsApp: **un test sull'API dice che il codice è giusto, non che la
  persona ci arriva.** Qui era stato verificato l'endpoint e letto il form,
  ma nessuno aveva cercato il pulsante che apre il form in modifica.

  [PR #121](https://github.com/lorenzomelchionna/gestionale_nsh/pull/121)
  → `develop`, [PR #122](https://github.com/lorenzomelchionna/gestionale_nsh/pull/122)
  → `main` (commit `be575e0`), CI verde su entrambe (8/8 su #122). 738 test.
  **Deploy confermato**: backend, frontend e worker tutti `SUCCESS` e
  `online`, riavviati alle 07:33 UTC. `/health` → 200,
  `www.newstylehair.it` → 200, worker `celery@... ready` con beat avviato,
  nessun errore vero nei log.

  *Nota per chi legge i log di Railway*: le righe di alembic all'avvio
  compaiono con severity `error` perché alembic scrive su stderr. Sono
  `INFO`, non errori.
- [x] ~~**Modifica ed elimina cliente**~~ — **corretto il 2026-09-23**,
  segnalato da Flavia con due foto: una scheda senza contatti, e «Crea
  accesso portale» che le diceva di aggiungere l'email «dalla modifica
  cliente». Quel comando **non è mai esistito**: nella scheda cliente
  c'erano solo accesso portale e «Unisci duplicato», nell'elenco solo
  «Nuovo cliente». Il form sapeva già modificare (titolo «Modifica
  cliente» compreso) ma nessun pulsante lo apriva in modifica.

  Ora nella scheda cliente ci sono **Modifica** ed **Elimina**, con una
  conferma che dice cosa succede: la scheda sparisce da elenco e ricerca,
  appuntamenti e incassi restano nello storico, e se c'è un accesso al
  portale non si potrà più prenotare. Il form è passato in
  `components/admin/ClientFormSheet.tsx`, condiviso da elenco e scheda.

  Due difetti trovati sulla strada, entrambi corretti nello stesso giro:
  - **Svuotare un campo non lo cancellava.** Il form mandava `undefined`,
    che sparisce dal JSON; l'aggiornamento tocca solo i campi ricevuti,
    quindi l'email vecchia restava. Ora manda `null` — fissato lato server
    da `test_un_contatto_si_puo_anche_togliere`.
  - **Gli errori del server non si vedevano.** Un telefono troppo corto o
    un'email come `rosa@b` (valida per il browser, non per il server)
    davano 422 e niente a schermo. Ora il messaggio compare nel form, in
    italiano.

  E una terza cosa: **tutte** le azioni della scheda (modifica, elimina,
  unisci, accesso portale, password) sono solo admin sul server, ma i
  pulsanti comparivano anche ai collaboratori, che cliccando ricevevano un
  403. Ora il gruppo intero si vede solo da admin.

  Verificato nel browser, percorso completo: scheda creata senza contatti
  → Modifica → telefono ed email aggiunti e visibili → «Crea accesso
  portale» ora mostra l'indirizzo e si attiva → errori di telefono ed
  email mostrati → email svuotata davvero → Elimina → scheda sparita da
  elenco e ricerca. Da collaboratrice nessun pulsante, anagrafica ancora
  leggibile.

  Rilasciato insieme all'ordine dei collaboratori, stessa PR ([#123](https://github.com/lorenzomelchionna/gestionale_nsh/pull/123)
  → `develop`, [#124](https://github.com/lorenzomelchionna/gestionale_nsh/pull/124)
  → `main`, commit `143bc51`): **deploy confermato** il 2026-09-23 alle
  10:20 UTC, dettagli nella voce «Ordine dei collaboratori nel calendario».
- [x] ~~**Promemoria mai partiti per le prenotazioni ravvicinate**~~ —
  **corretto il 2026-09-23**, segnalato da Flavia: appuntamento per il giorno
  stesso, conferma arrivata (appuntamento #42, nei log del worker alle 11:45
  UTC), promemoria no.

  Il worker, ogni 15 minuti, cercava gli appuntamenti che iniziano fra **24
  ore esatte**, con una finestra larga 15 minuti. Due buchi:
  - **Chi prenota con meno di 24 ore di anticipo non riceveva mai il
    promemoria**: l'appuntamento nasce già dentro le 24 ore e non passa mai
    per la fetta «fra 24 ore». In un salone sono le prenotazioni più comuni.
  - **Un giro saltato era un promemoria perso per sempre**: la finestra era
    larga esattamente quanto l'intervallo fra due giri, e il worker salta un
    giro ogni volta che riparte — a ogni rilascio.

  Nessun test esercitava la finestra: quelli esistenti controllavano il
  valore di ritorno e lo spostamento dell'orario, ed è per questo che il
  difetto è arrivato in produzione.

  Ora il promemoria parte per **ogni appuntamento confermato che inizia
  entro le prossime N ore** e non l'ha ancora ricevuto (il flag
  `reminder_sent` impedisce i doppioni, e rende la cosa robusta ai giri
  saltati), **ma non nella prima ora dopo la conferma** — deciso con
  Lorenzo: il promemoria ci deve essere anche per le prenotazioni del
  giorno stesso, ma due messaggi a un quarto d'ora di distanza sono uno di
  troppo, e il secondo si paga. Per contare quell'ora serviva sapere quando
  la conferma è **partita**, non quando l'appuntamento è nato: le
  prenotazioni online restano «in attesa» e vengono confermate dopo. Nuova
  colonna `appointments.confirmation_sent_at` (migration `a1f3c8d27e64`),
  scritta solo se la conferma è arrivata su almeno un canale.

  Chi prenota per fra meno di un'ora non riceve promemoria: un'ora dopo la
  conferma l'appuntamento è già iniziato.

  Test in `tests/test_promemoria_finestra.py`, che chiamano il task vero.
  Il caso di Flavia e il giro saltato visti **rossi prima** della
  correzione (zero promemoria partiti); poi falsificati uno per uno la
  prima ora di silenzio, l'esclusione degli appuntamenti già iniziati, la
  registrazione della conferma e il suo «non partita» per gli appuntamenti
  passati.

  **Al primo giro dopo il rilascio** partirà il promemoria per ogni
  appuntamento confermato entro le 24 ore che non l'ha ancora avuto,
  compreso quello di Flavia se non è ancora passato: è il recupero voluto.

  [PR #127](https://github.com/lorenzomelchionna/gestionale_nsh/pull/127)
  → `develop`, [PR #128](https://github.com/lorenzomelchionna/gestionale_nsh/pull/128)
  → `main` (commit `d29e73b`), CI verde su entrambe (8/8 su #128). 760
  test. **Deploy confermato** il 2026-09-23 alle 12:25 UTC: backend,
  frontend e worker `SUCCESS`; nei log del backend `Running upgrade
  c4e7a2d91b05 -> a1f3c8d27e64, add confirmation_sent_at to appointments`;
  `/health` → 200, frontend → 200.

  **Provato dal vivo, sul caso che l'aveva fatto trovare.** Primo giro del
  worker dopo il rilascio, 12:30 UTC: `succeeded`, nessun «promemoria non
  inviato». Dai log da soli non si poteva dire di più — `nsh.whatsapp` e
  `nsh.email` scrivono solo i fallimenti — quindi la prova l'ha data
  Twilio, interrogato in sola lettura: dal fisso, alla cliente
  dell'appuntamento #42, conferma alle 13:45:08 e **promemoria alle
  14:30:00 ora di Roma**, entrambi `delivered`. Appuntamento per il giorno
  stesso: col codice di prima quel promemoria non sarebbe partito mai.
- [x] ~~**Più servizi in un appuntamento, dal portale**~~ — **fatto il
  2026-09-23.** Dal gestionale si poteva già: il modale somma le durate.
  Dal portale no, ma mancava meno di quanto sembrasse. La prenotazione
  lato server gestiva già più servizi (somma delle durate, tempi di posa in
  sequenza, collaboratore che deve farli tutti, ora di fine calcolata da
  lui). Erano **gli orari** a saperne uno solo: `/availability` e
  `/availability/calendar` accettavano un unico `service_id`, quindi
  avrebbero mostrato orari validi per il primo servizio che la prenotazione
  poi rifiutava.

  Ora i due endpoint accettano `service_ids` (ripetuto nella query) e
  calcolano sulla durata complessiva; `service_id` resta valido per le
  pagine già aperte. L'**ordine** dei servizi conta, perché i tempi di
  posa dipendono da quale viene prima: nel portale è l'ordine in cui la
  cliente li tocca, e **lo stesso elenco** va sia agli orari sia alla
  prenotazione, così i due non possono discordare. In elenco compaiono
  solo i collaboratori che fanno **tutti** i servizi scelti; se nessuno li
  fa tutti, il messaggio suggerisce di toglierne uno o di prenotare due
  appuntamenti. Un appuntamento ha un solo collaboratore: «colore con
  Flavia e piega con Raffaella» restano due appuntamenti.

  Due trappole evitate lungo la strada:
  - axios manda le liste come `service_ids[]=1`, che FastAPI legge come
    niente: impostato `paramsSerializer: { indexes: null }` sulle due
    chiamate, e controllato nella richiesta vera (`service_ids=1&service_ids=3`);
  - la barra «Continua» fissata in basso sarebbe finita **sotto** la barra
    delle schede del portale, che è fissa in fondo per chi ha fatto
    l'accesso: sta a `bottom-tabbar`, misurata sul telefono.

  Test in `tests/test_booking_multi_servizio.py`, rossi prima
  dell'intervento. Il test che conta è l'accordo: l'ultimo orario offerto
  per due servizi viene accettato dalla prenotazione. Falsificato: con la
  disponibilità calcolata sul solo primo servizio quell'orario viene
  **rifiutato con 409**. Falsificato anche il controllo «il collaboratore
  deve farli tutti».

  Verificato nel browser da cliente: taglio + colore → barra «2 servizi ·
  180 min · €90.00», solo Sofia fra i collaboratori (Marco fa il taglio e
  non il colore, Elena il contrario), calendario e orari concordi (11 e
  11), ultimo orario 16:00 = fine giornata 19:00 meno 3 ore, riepilogo e
  prenotazione salvata «Taglio donna + Colore base», 16:00–19:00, €90.

  [PR #135](https://github.com/lorenzomelchionna/gestionale_nsh/pull/135)
  → `develop`, [PR #136](https://github.com/lorenzomelchionna/gestionale_nsh/pull/136)
  → `main` (commit `1f3ec97`), CI verde su entrambe (8/8 su #136). 768
  test. **Deploy confermato** il 2026-09-23: backend, frontend e worker
  `SUCCESS` alle 18:31 UTC.

  Verificato dal vivo sugli endpoint pubblici di produzione, con un
  collaboratore e due servizi da 30 minuti che fa entrambi, il 25/09:
  - un servizio: 22 orari, l'ultimo alle 18:30;
  - due servizi: 21 orari, l'ultimo alle 18:00, cioè anticipato
    **esattamente della durata del secondo**;
  - formato vecchio `service_id`: 200, con gli stessi orari del nuovo;
  - «Puoi sceglierne più di uno» presente nel bundle servito.
- [ ] **Il seed crea la cliente demo senza verifiche** — trovato il
  2026-09-23. `seed.py` crea `giulia.marino@email.it` con
  `email_verified` e `phone_verified` a `false`, quindi le credenziali demo
  che il seed stesso stampa non aprono il portale: il login risponde 403.
  È nato con le due verifiche, e tocca solo lo sviluppo locale. Basta
  mettere entrambe a `true` nel seed, come fa `portal_account.crea` per
  gli accessi creati dal salone.
- [x] ~~**Registrazione impossibile dal vecchio indirizzo**~~ — **trovato e
  corretto il 2026-09-23.** Una delle clienti di prova provava a
  registrarsi di nuovo e non ci riusciva.

  **La causa non era nel codice di registrazione.** Nei log HTTP di
  produzione, da un telefono Android: quattro `OPTIONS
  /api/public/auth/register` → **400**, e poi nessun `POST`. È il
  controllo preventivo CORS che il browser fa prima di mandare la
  richiesta; se fallisce, la richiesta non parte proprio. Dallo stesso
  telefono fallivano allo stesso modo login ed elenco servizi, mentre dal
  PC del salone, stessa rete, andava tutto.

  Il frontend risponde a **due indirizzi**: `www.newstylehair.it` e quello
  generato da Railway, `happy-benevolence-production.up.railway.app`. Il
  backend accetta come origine solo il primo. Riprodotto: il preflight dal
  vecchio indirizzo risponde `400 Disallowed CORS origin`, da `www` 200.
  La pagina sul vecchio indirizzo è identica e funzionante a vista, finché
  non si prova a mandare qualcosa. Le clienti di prova si erano
  registrate a luglio e agosto, prima del dominio: quel vecchio indirizzo
  ce l'avevano nei preferiti o come icona sul telefono.

  **Corretto in nginx**: il vecchio indirizzo, e solo quello per nome,
  risponde **301** su `https://www.newstylehair.it`, conservando percorso e
  parametri. Non un redirect generico «tutto ciò che non è www»: il
  controllo di salute di Railway interroga `/` con un altro host e vuole
  200. Si sarebbe potuto aggiungere il vecchio indirizzo alle origini CORS,
  ma avrebbe lasciato due siti con due insiemi di login salvati; il
  redirect ne lascia uno.

  Provato con `nginx:alpine` e la configurazione vera: vecchio host → 301
  con percorso conservato, `www` → 200, host del controllo di salute → 200.
  E falsificato il dettaglio che non si vede: senza `default_server` sul
  blocco principale, nginx prende il redirect come predefinito e `www`
  rimanda a se stesso all'infinito. Provato: `www` e controllo di salute
  entrambi 301.

  [PR #133](https://github.com/lorenzomelchionna/gestionale_nsh/pull/133)
  → `develop`, [PR #134](https://github.com/lorenzomelchionna/gestionale_nsh/pull/134)
  → `main` (commit `fd80b59`), CI verde su entrambe (8/8 su #134).
  **Deploy confermato** il 2026-09-23: backend `SUCCESS` alle 14:06 UTC,
  frontend alle 14:08. Il passaggio delicato era il controllo di salute
  sulla nginx nuova, e nei log del frontend c'è `GET / 200
  "RailwayHealthCheck/1.0"`. Il worker stava ancora ricostruendosi, ma
  quello precedente restava attivo; questa modifica non lo riguarda.

  Verificato dal vivo subito dopo:
  - `happy-benevolence-production.up.railway.app/login?registrati` → **301**
    su `https://www.newstylehair.it/login?registrati`;
  - `https://www.newstylehair.it` → 200;
  - preflight di `POST /api/public/auth/register` con origine `www` → 200.

  ~~«Intanto, per quella cliente: aprire `https://www.newstylehair.it`
  invece del vecchio link»~~ — **non serve più**: anche il vecchio link, i
  preferiti e l'icona sul telefono portano adesso all'indirizzo giusto.
  Chi aveva effettuato l'accesso sul vecchio indirizzo dovrà rientrare una
  volta, perché i login salvati appartengono all'indirizzo su cui sono
  stati fatti.
- [x] ~~**La Chat sembrava svuotata**~~ — **chiarito e corretto il
  2026-09-23.** Lorenzo: «quando sono stati eliminati i messaggi della
  chat? non è che ogni release cancella i messaggi?». La pagina Chat era
  vuota.

  **Non era stato cancellato niente.** Verificato nel database, in sola
  lettura: 2 conversazioni e 5 messaggi, tutti intatti, entrambe con
  `is_archived = True`. La conversazione nata alle 07:59 era sopravvissuta
  a quattro rilasci. Nel codice non esiste nessun percorso che cancelli
  conversazioni o messaggi. L'unica cancellazione della giornata era
  stata quella fatta a mano la notte prima, su richiesta, durante la
  pulizia dei clienti.

  **La causa era l'archiviazione.** Nell'intestazione di ogni
  conversazione c'è un'icona «Archivia»: un clic, nessuna conferma, e la
  conversazione sparisce. La pagina però chiedeva solo le non archiviate e
  **non aveva nessun modo di mostrare le altre**, quindi una conversazione
  archiviata tornava visibile solo se la cliente riscriveva. Con due
  conversazioni archiviate la Chat risultava vuota, e sembrava un database
  svuotato.

  Ora c'è un selettore **«In corso / Archiviate»**, e dentro una
  conversazione archiviata **«Riporta in lista»**. Il server lo sapeva già
  fare (`PATCH …/archive?archived=false`), mancava solo l'interfaccia.

  Trovato durante la prova: riaperta subito dopo averla archiviata, la
  conversazione mostrava ancora il pulsante sbagliato. Lo `staleTime`
  globale di 30 secondi teneva buona la copia in cache, e l'archiviazione
  aggiornava le liste ma non la singola conversazione. Ora aggiorna anche
  quella.

  Verificato nel browser: archivia → «In corso» vuota (lo stato visto da
  Flavia) → «Archiviate» la mostra → «Riporta in lista» → di nuovo in «In
  corso» → riarchiviata e riaperta subito, pulsante giusto. Su telefono a
  375 px nessuno scorrimento orizzontale.

  [PR #131](https://github.com/lorenzomelchionna/gestionale_nsh/pull/131)
  → `develop`, [PR #132](https://github.com/lorenzomelchionna/gestionale_nsh/pull/132)
  → `main` (commit `2e72f77`), CI verde su entrambe (8/8 su #132).
  **Deploy confermato** il 2026-09-23: backend e frontend `SUCCESS` alle
  13:03–13:04 UTC, worker alle 13:05. `/health` → 200,
  `www.newstylehair.it` → 200, e «Archiviate» e «Riporta in lista»
  presenti nel bundle JavaScript servito in produzione.

  Le due conversazioni vere **ora si recuperano**: Chat → «Archiviate» →
  apri la conversazione → «Riporta in lista».
- [ ] **Il calendario chiede un'impostazione che ai collaboratori è
  negata** — trovato il 2026-09-23 mentre si provava la scheda cliente da
  collaboratrice. `CalendarPage` carica sempre `GET
  /api/admin/settings/booking`, che è solo admin: a un collaboratore
  risponde 403, e il calendario lavora senza la configurazione del
  salone (giorni di chiusura compresi). Da decidere se esporre ai
  collaboratori la parte di configurazione che serve al calendario, o non
  chiederla quando non si è admin.
- [ ] **`min_cancel_hours` (24) supera `min_advance_hours` (2) in
  produzione** — trovato il 2026-09-22 durante la prova di prenotazione sul
  numero fisso: prenotazione riuscita, cancellazione rifiutata. Non un bug
  di codice — il vincolo di 24h di preavviso per cancellare è applicato
  correttamente — ma una prenotazione fatta con meno di 24h di anticipo
  (permesso fino a 2h) risulta **incancellabile dal portale fin dal momento
  in cui nasce**. Entrambi i valori sono già selezionabili da Impostazioni
  → Prenotazione online (verificato: il salvataggio funziona ed è
  immediato) — resta solo da **decidere il valore giusto** e cambiarlo lì,
  non serve altro codice.
  - [x] ~~**Il secondo problema trovato insieme: fallimento silenzioso**~~
    — **corretto lo stesso giorno.** Qualunque fosse il valore, se la
    cancellazione (o accettare/rifiutare un orario alternativo, o uscire
    dalla lista d'attesa) veniva rifiutata dal server, il frontend non lo
    mostrava: nessun messaggio, bottone che sembrava rotto. Le quattro
    mutation in `BookingAccountPage.tsx` non avevano gestione d'errore.
    Aggiunto un messaggio inline (il testo del salone,
    `HTTPException.detail`, non un genericone) sotto il bottone di ognuna,
    verificato dal vivo nel browser: prenotato un appuntamento a 3h da
    adesso, cancellazione rifiutata con «Cancellazione non consentita con
    meno di 24h di preavviso» mostrato sotto il bottone — prima spariva nel
    nulla. Verificato anche il percorso senza errori (abbassato
    temporaneamente `min_cancel_hours`): cancellazione riuscita, nessun
    messaggio residuo.

    [PR #117](https://github.com/lorenzomelchionna/gestionale_nsh/pull/117)
    → `develop`, [PR #118](https://github.com/lorenzomelchionna/gestionale_nsh/pull/118)
    → `main` (commit `b1227c1`), CI verde su entrambe. **Deploy confermato**:
    backend, frontend e worker tutti `SUCCESS` sul commit del merge,
    riavviati alle 16:09 UTC. `/health` → 200, `www.newstylehair.it` → 200,
    worker `celery@... ready`, nessun errore vero nei log.
- [x] ~~**WhatsApp produzione sul fisso**~~ — fatto il 2026-09-22. Il
  canale è passato dal numero ponte al **fisso del salone**
  `+39 0825 1728148`, sullo stesso WABA. Restano due dettagli non
  bloccanti — vedi «Il fisso è live» in fondo a questa voce.

  **Numero deciso (2026-08-25)**: il **fisso del vecchio gestionale**. Un
  numero sta su WhatsApp in un posto solo — app Business *oppure* API, mai
  entrambi — quindi va liberato dall'account attuale. Due conseguenze: le
  chat esistenti **si perdono** (esportarle prima), e da quel momento non si
  chatta più a mano dall'app. Il rimpiazzo però c'è già ed è costruito: il
  webhook salva ogni messaggio in entrata e la pagina Chat del gestionale li
  mostra e permette di rispondere. La verifica per un fisso avviene per
  **chiamata vocale**, non per SMS.

  **Verifica azienda Meta: dichiarata completata il 2026-09-17, da
  confermare** con la riga «Stato della verifica dell'azienda» in
  Impostazioni → Informazioni business, che deve dire *Verificato*.

  ~~«completata il 2026-09-02»~~ — **questa riga era falsa.** Il 17
  settembre, collegando l'account WhatsApp, il portfolio risultava *Non
  verificato* e senza nessuna pratica in corso o respinta. I dati
  dell'azienda erano incompleti: ragione sociale «New Style Hair» invece di
  quella della visura, indirizzo «Italia», nessun telefono. Con dati così il
  confronto con la visura non può tornare. Corretti il 17 settembre e
  verifica rifatta da capo.

  **Come sono organizzati gli account Meta**, perché qui ci si è confusi più
  volte:

  ```
  Profilo Facebook personale di Vincenzo Romolo      ← il login
   └─ Portfolio business (ID 217225312415884)        ← qui si fa la verifica
       ├─ Pagina Facebook "New Style Hair"
       └─ Account WhatsApp "New Style Hair"          ← ID 2221302968437076
  ```

  La verifica riguarda il **portfolio**, non la Pagina. Cercare di
  «verificare» la Pagina porta a Meta Verified, cioè alla spunta blu a
  pagamento, che **non serve**. I dati del portfolio devono essere quelli
  della visura, copiati lettera per lettera: ragione sociale, sede legale,
  telefono (il **fisso**, non il numero Twilio), sito.

  **Secondo amministratore**: Flavia Romolo (`flaviaromolo400@gmail.com`)
  invitata il 2026-09-18 con accesso completo su tutto. **Risulta ancora
  «Non attivo/a»**, cioè l'invito non è stato accettato: finché resta così
  Pagina, account WhatsApp e verifica dipendono ancora da un solo profilo
  personale, e l'obiettivo non è raggiunto.

  La mail arrivata a Flavia **è l'invito, non la conferma che sia stato
  accettato**: riceverla non sposta lo stato. Lo stato cambia solo dopo che
  lei apre il link, entra col **proprio profilo Facebook** e conferma. La
  prova che conta non è la colonna nell'elenco ma questa: Flavia apre
  `business.facebook.com` col suo Facebook e vede il portfolio New Style
  Hair nel selettore in alto. Se non lo vede, l'invito è ancora aperto —
  va rimandato, controllando lo spam di quella casella.

  Nell'elenco compare anche `@vincenzoromolo_`, che è l'account Instagram
  della stessa persona: non conta come seconda testa.

  **Account Twilio a pagamento: fatto il 2026-09-09.** Blocco che nessuno
  aveva previsto: l'account era **trial**, e la registrazione di un Mittente
  WhatsApp richiede un account upgradato — il credito di prova residuo non
  basta, perché il vincolo non è «avere credito» ma «non essere trial». Fatto
  l'upgrade con carta e versamento iniziale.

  Da controllare quando si arriva a regime: **attivare la ricarica
  automatica** con soglia. Il credito che finisce di sabato mattina significa
  promemoria che non partono, e nessuno se ne accorge finché una cliente non
  si presenta il giorno sbagliato — è un guasto silenzioso, il tipo peggiore.

  Costo atteso, per non trovarselo in faccia: **€20–40 al mese** a regime
  (~500–1.000 messaggi). Le conversazioni **iniziate dalla cliente sono
  gratuite**, e lo sono anche i template utility mandati entro 24 ore da un
  suo messaggio: quindi tutta la chat quotidiana non costa niente, e quella
  stima è un tetto, non il valore atteso. Si paga solo quando è il salone a
  scrivere per primo a freddo.

  ### Ordine dei passi che restano

  L'ordine conta, e non è quello che sembra ovvio.

  1. **Esportare le chat** dal fisso (app → Impostazioni → Chat → Esporta).
     Da fare comunque e per primo: lo storico **non passa all'API in nessun
     caso**, nemmeno migrando. L'API non ha proprio il concetto di quelle
     conversazioni.
  2. **Aprire la registrazione del Sender su Twilio** (Console → Messaging →
     Senders → WhatsApp senders → New sender) e arrivare al punto in cui si
     inserisce il numero — **senza aver cancellato niente**.

     Qui si guarda cosa risponde: se offre una **migrazione** app → API la si
     usa e non si cancella nulla; se rifiuta il numero perché già su
     WhatsApp, allora si cancella l'account dall'app e si riprende.

     **Il motivo di quest'ordine**: provare non costa niente (al massimo un
     errore), mentre cancellare è irreversibile e apre subito la finestra in
     cui il numero è muto. Fra due strade, si rimanda quella che non torna
     indietro. Una versione precedente di questa nota diceva di cancellare
     per prima cosa: era un consiglio che regalava giorni di numero spento
     senza motivo.
  3. **Display name e profilo**, che si compilano nella stessa schermata del
     Sender — non sono un passaggio separato, come invece diceva la nota
     vecchia. Nome: `New Style Hair`, che è la parte distintiva della
     ragione sociale verificata **e** il dominio **e** l'insegna: tre
     riscontri che dicono la stessa cosa. Niente termini generici, niente
     emoji, niente città nel nome. Nel profilo va l'indirizzo di **visita**
     (Corso Italia, 32), non quello legale con `snc`.
  4. **Verifica del numero per chiamata vocale** — serve qualcuno in salone
     che risponda e trascriva il codice.
  5. **Far approvare i template** (1–2 giorni l'uno).
  6. **Railway**: `TWILIO_WHATSAPP_FROM` e i due `TWILIO_TEMPLATE_*` su
     backend **e** worker, poi `whatsapp_enabled=true` da Impostazioni.

  ### Come è andata davvero, e il piano che ne è uscito (2026-09-09)

  Twilio **rifiuta il fisso**: è ancora su WhatsApp Business, quindi va
  liberato — la migrazione automatica non c'è. Ma il fisso **non si può
  liberare adesso**: il salone lavora ancora col vecchio gestionale e quella
  è la chat con cui risponde alle clienti.

  Il problema non è il fisso in sé, è che **l'approvazione dei template
  richiede 1–2 giorni**. Facendo tutto il giorno del passaggio, WhatsApp
  resterebbe spento proprio mentre il salone cambia sistema.

  **Piano scelto: numero ponte.** I template si approvano sul WhatsApp
  Business Account, non sul singolo numero, e un WABA può avere più numeri.
  Quindi:

  - **Adesso** — comprato un numero Twilio (USA, attivo subito; uno italiano
    richiede un bundle documentale che fa aspettare giorni, e questo numero
    è temporaneo). Lo si registra come Sender → nasce il WABA → si
    sottopongono i template e si aspetta con calma.
  - **Il giorno del passaggio** — si cancella WhatsApp dal fisso, lo si
    aggiunge come secondo Sender **sullo stesso WABA**, verifica per
    chiamata vocale, si cambia `TWILIO_WHATSAPP_FROM`. I template sono già
    approvati, quindi funziona subito.

  Il giorno del go-live diventa un'ora di lavoro invece di giorni di attesa,
  e permette di provare il percorso vero — template reali, non Sandbox —
  settimane prima invece di scoprire un intoppo il giorno stesso.

  **Da verificare appena il primo Sender è attivo**: che i template approvati
  restino validi passando al secondo numero dello stesso WABA. È quello che
  risulta, ma non è stato provato sul campo — e regge tutto il piano. Si
  controlla a costo quasi zero sottoponendo **un** template e guardando.

  **Stato al 2026-09-17**: numero ponte **+1 689 344-8830**. Collegato a
  Meta dalla registrazione Sender di Twilio con il login di Vincenzo Romolo:
  l'account WhatsApp «New Style Hair» è nato sotto il portfolio giusto, e la
  schermata di Twilio («collega l'account WhatsApp Business al tuo numero»)
  conferma che il WABA è un oggetto distinto a cui i numeri si agganciano.
  Durante il collegamento vanno **tolte** le due spunte facoltative:
  analisi automatica delle conversazioni da parte di Meta e insight
  aziendali. Non servono a mandare messaggi, e sono chat con dati personali
  delle clienti.

  **Aggiornamento 2026-09-17, letto dalle API di Twilio**, non dalle
  schermate:

  | | |
  |---|---|
  | Sender `+1 689 344-8830` | **ONLINE**, nome «New Style Hair» |
  | `promemoria_appuntamento` `HXa61b5a829758c40d48c5c3b575f7b074` | ✅ **approvato**, Utility, `it` |
  | `conferma_appuntamento` `HX848a66f189ce68f7646a7327c556ca97` | ⏳ **in attesa**, Utility, `it` |

  Entrambi i testi controllati via API: variabili nell'ordine che il codice
  manda (`{{1}}` nome, `{{2}}` data, `{{3}}` ora, `{{4}}` collaboratore). I
  SID sono identificativi, non credenziali: senza il token non servono a
  niente.

  *(Stato di metà giornata, superato poco sotto: acceso lo stesso 17.)*
  **Non ancora su Railway, di proposito**: `TWILIO_WHATSAPP_FROM` è ancora la
  Sandbox, e un template del WABA «New Style Hair» mandato dal numero della
  Sandbox verrebbe rifiutato. SID e numero vanno cambiati **insieme**, su
  backend e worker.

  - [x] ~~**Webhook del Sender**~~ — fatto 2026-09-17 via API:
    `https://gestionalensh-production.up.railway.app/api/public/whatsapp/webhook`,
    POST. Prima era vuoto, quindi la risposta di una cliente non arrivava da
    nessuna parte. Controllata **prima** la firma in produzione, perché se
    l'URL ricostruito dal backend non combaciasse ogni risposta verrebbe
    scartata in silenzio: senza firma 403, firma sbagliata 403, firma giusta
    200. La prova usava un corpo vuoto, che il gestore ignora, quindi non ha
    scritto niente a database.
    **Il giorno del passaggio lo stesso webhook va impostato anche sul
    Sender del fisso**: è un'impostazione del singolo Sender, non del WABA.
  - [x] ~~**Profilo del Sender**~~ — fatto 2026-09-17: descrizione, indirizzo
    di visita, categoria «Beauty, Spa and Salon», sito. Nome lasciato com'era
    (cambiarlo fa ripartire la revisione di Meta). Twilio vuole la categoria
    per esteso: il codice Meta `BEAUTY` viene rifiutato con errore `63100`.
    **Email lasciata vuota di proposito**: era stata proposta
    `noreply@newstylehair.it`, ma in un profilo pubblico un indirizzo da cui
    si spedisce e basta è un errore, perché chi ci scrive non riceve
    risposta. Da decidere quale indirizzo mostrare.
  - [x] ~~**Prova vera**~~ — fatta 2026-09-17, dal numero ponte al telefono
    di Lorenzo, passando per il codice vero (`send_reminder_message` con un
    appuntamento finto e le credenziali di produzione passate per
    ambiente, **senza** toccare la configurazione di Railway):
    - template **consegnato** (`delivered`), testo e variabili giusti;
    - in cima alla chat compare **«New Style Hair»**;
    - la risposta di Lorenzo è arrivata a Twilio e Twilio l'ha inoltrata al
      webhook: **200**, firma valida.
    Da confermare a vista: che la risposta compaia nella pagina Chat.
  - [x] ~~**Entrambi i template approvati**~~ — `conferma_appuntamento`
    approvato il 2026-09-17 alle 13:02 UTC.
    **Nota per chi legge il debugger di Twilio**: gli avvisi `63046` non
    sono errori, sono le notifiche di cambio stato dei template («The
    template was APPROVED»). Hanno livello *warning* e sembrano problemi, ma
    non lo sono.

  **ACCESO il 2026-09-17 sul numero ponte.** Impostate su Railway, backend
  **e** worker:

  ```
  TWILIO_WHATSAPP_FROM=whatsapp:+16893448830
  TWILIO_TEMPLATE_CONFERMA=HX848a66f189ce68f7646a7327c556ca97
  TWILIO_TEMPLATE_PROMEMORIA=HXa61b5a829758c40d48c5c3b575f7b074
  ```

  Provato in produzione nelle due direzioni: messaggio dal gestionale al
  telefono e risposta dal telefono alla pagina Chat.

  **Perché prima non partiva niente**: il gestionale spediva ancora dalla
  Sandbox, e ogni invio moriva con `63015` — «il destinatario non si è
  iscritto alla Sandbox». La ricezione invece funzionava già, perché non
  dipende dal numero mittente. Sintomo istruttivo: **metà canale funzionante
  sembra un canale rotto in modo misterioso**, e per capirlo è servito
  leggere il registro di Twilio, non i log dell'applicazione.

  **Il numero è ancora quello ponte, americano.** Va bene per provare, ma a
  regime le clienti vedrebbero un prefisso +1: chi lo blocca o lo segnala
  abbassa la reputazione dell'account WhatsApp, e le conversazioni si
  dividerebbero su due numeri. Il passaggio al fisso resta da fare il giorno
  del go-live, seguendo i passi qui sopra.

  ### Il fisso è live (2026-09-22)

  Il numero (`0825 1728148`, il vecchio gestionale) era ancora agganciato
  all'app WhatsApp Business su un telefono in salone — primo tentativo di
  registrazione respinto da Twilio: «numero già registrato in un account
  WhatsApp». Liberato da lì (app → Impostazioni → Account → Elimina il mio
  account) e registrato come secondo Sender sullo stesso WABA «New Style
  Hair» (ID `2221302968437076`), seguendo l'ordine scritto sopra: nessuna
  migrazione offerta da Twilio, quindi cancellazione dall'app e nuova
  registrazione, non fusione. Verifica per **chiamata vocale**, come
  previsto al punto 4 del piano.

  **Il nome business è sbagliato**: la schermata di collegamento a Meta ha
  ereditato «Vincenzo Romolo» (il profilo personale del login), non «New
  Style Hair». Il campo è bloccato dopo la registrazione — Twilio lo dice
  esplicito: «To update the business display name for this phone number
  please submit a support ticket». Ticket aperto il 2026-09-22, in attesa
  di risposta Twilio e poi review Meta (giorni, non ore). **Non blocca
  l'invio**: è cosmetico, il nome sbagliato compare solo in cima alla chat.

  **Conferma sul campo dell'assunzione del 2026-09-17** («i template
  restano validi passando al secondo numero dello stesso WABA», scritta ma
  mai provata): mandato un messaggio vero col template
  `TWILIO_TEMPLATE_VERIFICA` dal nuovo Sender, prima ancora di toccare
  Railway — consegnato, testo e variabile giusti, senza nessuna nuova
  sottomissione a Meta. Tutto il piano del numero ponte poggiava su questo,
  ed era corretto.

  Sender **online**, quality rating «Unavailable» — normale per un numero
  senza volume di messaggi ancora, si popola con l'uso.

  **Railway aggiornato** (backend e worker): `TWILIO_WHATSAPP_FROM` da
  `whatsapp:+16893448830` a `whatsapp:+3908251728148`. Deploy confermato
  `SUCCESS` su entrambi i servizi. Prova vera dopo lo switch: messaggio
  reale al telefono di Lorenzo, consegnato dal numero nuovo.

  **Webhook non ereditato dal WABA** — è un'impostazione per singolo
  Sender, esattamente come annotato sopra per il numero ponte, e sul nuovo
  Sender risultava vuoto (controllato via API, `GET
  /v2/Channels/Senders/{sid}`, campo `webhook.callback_url` stringa
  vuota). Impostato via API allo stesso URL del numero ponte:
  `https://gestionalensh-production.up.railway.app/api/public/whatsapp/webhook`,
  POST.

  **Resta aperto**:
  - [ ] Ticket Twilio per correggere il nome business («New Style Hair»)
  - [x] ~~Confermare **a vista** che una risposta vera della cliente sul
    fisso compaia nella pagina Chat~~ — **confermato il 2026-09-23, dai
    fatti e non da una prova.** Nel database (letto in sola lettura) una
    conversazione ha messaggi in arrivo alle 07:59 e alle 09:37 e le
    risposte del salone alle 09:24 e alle 09:39, partite **dalla pagina
    Chat**: qualcuno ha visto lì il messaggio della cliente e ha risposto.
    Twilio conferma quelle risposte come `read`. Resta la nota storica:
    Metà strada era fatta il 2026-09-22:
    mandato un messaggio vero dal telefono di Lorenzo al fisso, e nei log
    HTTP di Railway risulta `POST /api/public/whatsapp/webhook 200` —
    quindi Twilio inoltra e la firma è valida (senza firma o con firma
    sbagliata sarebbe 403). Resta da guardare la pagina Chat del
    gestionale: il `200` dice che la richiesta è stata accettata, non che
    il messaggio sia visibile a chi deve rispondere. Stessa voce rimasta
    aperta per il numero ponte il 17 settembre, per lo stesso motivo.
  - [ ] Decidere quando cancellare/disattivare il numero ponte
    `+1 689 344-8830` — resta come secondo Sender dello stesso WABA finché
    non si toglie

  **Deploy confermato**: [PR #119](https://github.com/lorenzomelchionna/gestionale_nsh/pull/119)
  (verifica telefono, questa voce) → `develop`,
  [PR #120](https://github.com/lorenzomelchionna/gestionale_nsh/pull/120)
  → `main` (merge commit `00402f2`), CI verde su entrambe (8/8 check su
  #120). Backend, frontend e worker tutti `SUCCESS` sul commit del merge.
  Log di startup del backend confermano la migrazione applicata,
  `Running upgrade b6e21c8f0a53 -> f8a2e916c4d3, add phone verification to
  client_accounts`, e il bootstrap completato senza errori; worker
  `celery@... ready.`, nessun errore vero (solo l'avviso normale su
  superuser). `/health` → 200, `www.newstylehair.it` → 200. Il numero fisso
  come `TWILIO_WHATSAPP_FROM` era già attivo da prima di questo rilascio
  (switchato a mano su Railway, non fa parte del codice deployato).

- [x] ~~**Fuso orario degli appuntamenti**~~ — **corretto il 2026-09-17**, in
  due rilasci. Sotto resta il referto, perché il ragionamento serve a chi un
  domani toccherà `availability.py`.

  **Rilascio 1 — i messaggi.** `app/utils/tempo.py` è ora l'unico confine fra
  ora di orologio e istante: `istante(giorno, ora)` e `ora_salone(dt)`, con
  `Europe/Rome` da `ZoneInfo` e non dal `TZ` del processo. Email e WhatsApp
  convertono prima di formattare. Tre test esistenti si aspettavano l'ora UTC
  — erano loro a fissare il difetto — e ora verificano l'ora del salone.
  `tzdata` dichiarato in `requirements.txt` invece che ereditato da `kombu`:
  su immagine slim `zoneinfo` senza database dei fusi solleva all'avvio, e
  nessuno collegherebbe quel guasto all'impacchettamento di Celery.

  **Rilascio 2 — gli slot.** Tre conversioni, arrivate **insieme**: gli
  appuntamenti entrano nella griglia dei minuti con `minuti_salone()` e non
  con `.hour`, gli slot nascono da `istante()`, e la finestra del giorno è
  quella del salone. In `booking.py` un `start_time` senza fuso è letto come
  ora del salone, e la data di riferimento è quella del salone.

  **La trappola, per chi tornerà qui:** correggere la sola riga degli slot
  lasciando gli appuntamenti sulla vecchia scala apre **doppie
  prenotazioni** — l'appuntamento occuperebbe un minuto che nessuno slot
  guarda. `TestNonSiCorreggeAMeta` in `tests/test_slot_ora_salone.py` esiste
  per quello, ed è stato verificato facendo davvero la correzione parziale:
  tre test diventano rossi.

  **Verifica**: 682 test passano; il difetto originale rimesso ne fa cadere
  nove. Provato nel browser sul database di sviluppo, percorso intero: il
  portale offre 09:00–18:00 per una giornata 09:00–19:00 con servizio da
  un'ora, il database salva `07:00Z`, la conferma scrive «alle 09:00». Prima
  quei tre punti dicevano tre cose diverse.

  Le date nei test nuovi sono **calcolate**, non scritte: una data fissa
  scivola nel passato e da lì `get_available_slots` risponde `[]` per il
  preavviso minimo, cioè il test fallirebbe per un motivo che non c'entra.

  **Resta aperto, minore**: i confini di giornata — sono nella voce
  «Difetti minori ancora aperti» subito sotto il referto.

<details>
<summary>Referto originale (2026-09-17)</summary>

- [x] **Fuso orario degli appuntamenti: CONFERMATO, in produzione adesso** —
  emerso il 2026-09-17 preparando la prova WhatsApp. Verificato con un
  controllo a più agenti: quattro lettori, uno per percorso, e due
  refutatori indipendenti per ogni conclusione. Quattro affermazioni su
  quattro confermate, sette verifiche su otto **riprodotte eseguendo il
  codice vero**.

  **Correzione all'ipotesi iniziale.** La prima versione di questa nota
  diceva che lo stesso appuntamento veniva salvato in due modi a seconda di
  chi lo creava. Non è così: il database contiene sempre l'istante che la
  cliente ha cliccato e che lo staff vede in calendario, e i due frontend
  sono corretti. L'errore sta in tre punti del **backend** che trattano
  l'ora del salone come fosse UTC:
  - `services/availability.py:227` — slot costruiti con
    `combine(data, ora, tzinfo=UTC)`;
  - `services/availability.py:183` — occupazione degli appuntamenti letta in
    ore UTC;
  - `utils/email.py` e `utils/whatsapp.py` — `strftime` su `start_time`
    senza `astimezone`.

  **Effetti** (esempio: 18/09/2026, salone aperto 09–19, estate):
  - **P1, portale**: le clienti vedono gli slot **dalle 11:00 alle 20:00**.
    Si può prenotare alle 20:00 a salone chiuso, le 09:00–10:30 non
    compaiono mai, un permesso 14–16 resta prenotabile alle 14:00. D'inverno
    lo scarto è di 1 ora.
  - **P2, messaggi**: **tutte** le email e i WhatsApp scrivono un orario 2
    ore prima di quello in calendario (1 ora d'inverno). Un appuntamento
    dello staff alle 09:00 arriva come «alle 07:00».
  - **P3, preavvisi e promemoria**: corretti rispetto alle schermate, ma
    sfasati rispetto al testo dei messaggi. Spariscono correggendo P1 e P2.

  Controllo sovrapposizioni fra appuntamenti: coerente, perché confronta UTC
  con UTC. Lo sfasamento riguarda solo il confronto con orari di lavoro,
  giorni extra e permessi.

  **Correzione scelta in linea di principio (opzione A): istanti reali
  ovunque, con la conversione nel backend.** Un modulo con
  `ZoneInfo("Europe/Rome")`, usato per:
  - slot **e** occupazione in `availability.py`, **nello stesso rilascio**.
    Correggere solo la riga 227 introduce doppie prenotazioni: lo slot delle
    09:00 diventerebbe `07:00Z` e un appuntamento dello staff a `07:00Z`
    continuerebbe a occupare il minuto 420, fuori griglia;
  - `astimezone` nei messaggi;
  - `booking.py` (valori senza fuso letti come ora di Roma, `date.today()`
    sostituito con la data di Roma);
  - confini di giornata in dashboard e filtri;
  - seed, bootstrap e test, con test sui giorni del cambio d'ora (29/03 e
    25/10/2026);
  - `tzdata` dichiarato in `requirements.txt`, che oggi arriva solo come
    dipendenza di `kombu`.

  Il frontend non va toccato. Scartate l'opzione B (ora del salone come UTC
  ovunque: toccherebbe tutto il frontend e lascerebbe in `timestamptz`
  valori che non sono istanti) e l'opzione C (colonna senza fuso: più costi
  che vantaggi).

  **Dati esistenti**: le righe create dallo staff sono già giuste. Per
  quelle online vale lo schermo (quello che la cliente ha cliccato), quindi
  **nessuna migrazione**. Il criterio per distinguerle è
  `appointments.origin`.

  **Prima di correggere**, in sola lettura sulla produzione:
  1. controllare `CollaboratorSchedule`: se qualcuno ha già «compensato» gli
     orari a mano, la correzione sposterebbe il portale nel verso opposto;
  2. elencare le **prenotazioni online future**. Quelle clienti hanno
     ricevuto un orario sbagliato e vanno avvisate:
     ```sql
     SELECT id, start_time AT TIME ZONE 'Europe/Rome' AS ora_schermo,
            start_time AT TIME ZONE 'UTC'         AS ora_messaggio, status
     FROM appointments WHERE origin = 'online' AND start_time > now()
     ORDER BY start_time;
     ```
     Vanno segnalate a mano anche quelle che, in ora di Roma, cadono fuori
     orario o dentro un permesso.

  **Da chiudere prima di attivare WhatsApp in produzione.**

  **Segnalati da un solo lettore**: spostati fuori da questo blocco, nella
  voce «Difetti minori ancora aperti» qui sotto. Stavano qui dentro chiusi,
  dove non li vedeva nessuno.

</details>

- [x] ~~**Difetti minori raccolti il 2026-09-22**~~ — **corretti lo stesso
  giorno, in produzione dalle 11:43 UTC.** Ognuno era letto dal codice, non
  riprodotto; per ognuno si è scritto prima il test che lo fa cadere,
  verificato che cadesse davvero (anche con un finto-fix, per essere sicuri
  che il test misuri il difetto e non qualcos'altro), e solo dopo applicata
  la correzione — 695 test passano, 13 nuovi.
  [PR #113](https://github.com/lorenzomelchionna/gestionale_nsh/pull/113) →
  `develop`, [PR #114](https://github.com/lorenzomelchionna/gestionale_nsh/pull/114)
  → `main` (commit `85962e8`), entrambe con CI verde.

  **Deploy confermato**, non solo mergiato: backend, frontend e worker tutti
  `SUCCESS` sul commit del merge, avviati alle 11:42:43 UTC senza
  migration nuove (nessun modello toccato). `/health` → 200,
  `www.newstylehair.it` → 200, worker `celery@... ready` con beat e Redis
  connessi, nessun errore vero nei log (solo il consueto avviso cosmetico
  "root user" e le righe INFO di Alembic etichettate `error` da Railway).
  - [x] ~~**Confini di giornata col giorno del processo nella dashboard**~~
    (`api/admin/dashboard.py`). «Oggi/settimana/mese/anno» ora usano
    `oggi_salone()`; anche le spese, che confrontavano `Expense.date` (un
    giorno senza fuso) con `.date()` di un istante UTC — stesso difetto una
    seconda volta nella stessa funzione. Test in
    `tests/test_dashboard_ora_salone.py`, con l'orologio bloccato
    (`tempo.adesso()` sostituito) su un istante fisso di prima mattina a
    Roma: deterministico, non dipende da quando gira la suite.
    ~~**Restano aperti, stesso difetto, non ancora toccati**~~ — **verificati
    e corretti il 2026-09-22**, la sera stessa in cui erano stati segnalati
    come sospetti. Tre meccanismi diversi, stessa famiglia:

    - **Filtri data di agenda e incassi** (`CalendarPage.tsx:187`,
      `AppointmentsPage.tsx:67`, `CashPage.tsx:45` → `date_from`/`date_to`
      in `api/admin/appointments.py` e `api/admin/payments.py`). Il
      frontend era già giusto — manda mezzanotte a Roma senza fuso, come
      deve. Il difetto era nel backend: un `datetime` senza fuso confrontato
      con una colonna `timestamptz` viene interpretato dal driver secondo il
      fuso **del processo Python**, non quello di sessione del database né
      UTC per definizione — misurato forzando `TZ=UTC` e `TZ=Europe/Rome`
      sullo stesso codice e vedendo il confine spostarsi. Su Railway il
      processo non ha `TZ`, quindi gira in UTC: un filtro per "22 giugno"
      diventava una finestra UTC. Nuova funzione `istante_da_ingresso()` in
      `tempo.py`, usata ai due endpoint. Test in
      `tests/test_query_filters_ora_salone.py`, con l'attenzione che la
      *stessa cosa* capita al test se non fissa `TZ=UTC` sul proprio
      processo: sul Mac di chi sviluppa (Europe/Rome) il difetto sarebbe
      rimasto nascosto per puro caso.
    - **Scadenza dei buoni regalo** (`models/gift_card.py:139`,
      `api/admin/gift_cards.py:186`). `date.today()` è la data del
      *processo* (stesso meccanismo di sopra, UTC su Railway): una vendita
      fra mezzanotte e l'alba a Roma faceva scadere la card un giorno più
      tardi del promesso, e un buono in scadenza restava spendibile un paio
      d'ore oltre la mezzanotte vera. Sostituito con `oggi_salone()` in
      entrambi i punti. Test in `tests/test_gift_cards.py`
      (`TestScadenzaUsaIlGiornoDelSalone`).
    - **`revenue-chart` e `yearly-chart`** in `dashboard.py`. Confermato:
      `func.date()`/`extract()` su una colonna `timestamptz` tagliano
      usando il `TimeZone` di **sessione** del database — UTC su Railway,
      verificato con una query diretta — non il fuso del salone. Un
      incasso di notte finiva raggruppato nel giorno (o, a Capodanno, anche
      nell'anno) sbagliato. Anche l'anno di default di `yearly-chart` usava
      `now.year` (UTC). Nuova funzione `colonna_ora_salone()` in `tempo.py`
      (`AT TIME ZONE 'Europe/Rome'` prima del taglio). Test in
      `tests/test_dashboard_ora_salone.py`, il secondo apposta a Capodanno:
      è l'unico giorno in cui la differenza fra i due fusi sposta anche
      l'anno, non solo il giorno.

    Ognuno dei tre falsificato prima di essere considerato chiuso: fix
    applicata, test verificato che passa; fix rimossa a mano, stesso test
    verificato che torna a fallire; fix riapplicata. 7 nuovi test, nessuno
    dei vecchi toccato nel comportamento (uno solo, `test_scade_a_un_anno`,
    aggiornato per confrontare contro `oggi_salone()` invece di
    `date.today()` — altrimenti sarebbe diventato lui stesso intermittente
    nella stessa finestra oraria).

    [PR #115](https://github.com/lorenzomelchionna/gestionale_nsh/pull/115)
    → `develop`, [PR #116](https://github.com/lorenzomelchionna/gestionale_nsh/pull/116)
    → `main` (commit `388a276`), CI verde su entrambe. **Deploy confermato**:
    backend, frontend e worker tutti `SUCCESS` sul commit del merge,
    riavviati alle 12:18 UTC. `/health` → 200, `www.newstylehair.it` → 200,
    worker `celery@... ready`, nessun errore vero nei log.
  - [x] ~~**Proposta alternativa accettata: la fine restava quella
    vecchia**~~ (`api/public/booking.py`). La durata si legge ora *prima*
    di spostare `start_time`. Test in `tests/test_accept_alternative.py`,
    compreso il caso limite che dava durata negativa.
  - [x] ~~**Promemoria segnato come inviato anche se non era partito**~~
    (`tasks/reminders.py`, `utils/notifications.py`).
    `notify_appointment_reminder` ora ritorna se il promemoria è da
    considerarsi gestito — consegnato su almeno un canale, o nessun canale
    disponibile per quel cliente — e il task spunta il flag solo in quel
    caso. Con entrambi i canali rotti l'appuntamento ricompare nella
    finestra al giro successivo invece di perdere il tentativo per sempre.
    Test in `tests/test_reminders.py`.
  - [x] ~~**Appuntamento spostato, promemoria perso**~~
    (`api/admin/appointments.py`). Cambiare `start_time` ora rimette
    `reminder_sent`/`whatsapp_reminder_sent` a falso; una modifica che non
    tocca l'orario (note, servizi) li lascia intatti. Test in
    `tests/test_reminders.py`.
  - [x] ~~**Una scheda eliminata poteva ancora prenotare**~~ — il più
    grave dei cinque: non un dato sbagliato, un controllo accessi mancante.
    «Elimina cliente» spegneva solo `Client.is_active`; login e token del
    portale guardano `ClientAccount.is_active`, che restava intatto, e ogni
    endpoint di `booking.py` ritrovava la scheda per `account_id` senza
    controllare se fosse attiva — non solo la prenotazione: anche
    cancellare, accettare un orario alternativo, iscriversi o uscire dalla
    lista d'attesa. Erano **otto** punti nello stesso file con lo stesso
    difetto, non uno: chiusi tutti insieme con un unico helper
    (`_cliente_del_portale`), non uno alla volta, per lo stesso motivo per
    cui altrove in questo file le correzioni parziali sono vietate — un
    punto lasciato aperto sarebbe stata la stessa falla con un altro nome.
    Test in `tests/test_auth_boundaries.py`, dentro `TestDeactivatedAccounts`
    che già copriva l'altro interruttore.

- [x] ~~**Codice pronto per i template Meta**~~ — fatto 2026-08-25, prima
  dell'approvazione, perché è la parte che non dipende da Meta.

  **Correzione a una nota che era sbagliata in questo file**: diceva
  «aggiornare `TWILIO_WHATSAPP_FROM` (1 variabile, zero codice)». Non era
  vero. `send_whatsapp()` mandava `Body`, cioè testo libero, e fuori dalla
  finestra di 24 ore da un messaggio della cliente WhatsApp lo **rifiuta**
  (errore 63016): vuole `ContentSid` di un template approvato più
  `ContentVariables`. In Sandbox non si vedeva perché il `join` apre una
  sessione — la Sandbox è più permissiva del posto in cui il codice deve
  girare, ed è il motivo per cui un problema del genere si scopre al
  rilascio.

  Ora `_invia()` è la parte comune e sopra ci stanno due strade:
  `send_whatsapp()` per il testo libero e `send_whatsapp_template()` per i
  template. I messaggi che parte il salone — **conferma e promemoria** —
  passano dai template; la pagina Chat resta a testo libero, ed è corretto:
  quelle risposte stanno dentro la finestra per costruzione, visto che
  esistono perché la cliente ha scritto per prima.

  **Erano quattro, sono due dal 2026-09-09**: auguri di compleanno e reset
  password sono passati a solo email, e le due funzioni WhatsApp sono state
  cancellate invece che lasciate lì inutilizzate. Le ragioni stanno accanto
  alle funzioni in `notifications.py`, in breve: l'augurio per Meta è
  «marketing» e costerebbe molto più di un promemoria a fronte del minor
  valore pratico, e il reset contiene un link — che Meta vuole come pulsante,
  non come variabile di testo — e nasce comunque da una richiesta fatta via
  email. Due test in `test_whatsapp_templates.py` tengono ferma la scelta:
  senza, «rimettiamo anche WhatsApp» sembrerebbe un miglioramento ovvio e la
  bolletta lo scoprirebbe un mese dopo.

  **Senza SID configurato si continua col testo libero**, con una riga di log
  che dice perché. Non è un ripiego per la produzione — lì senza template il
  messaggio non parte comunque — ma è ciò che tiene in piedi la Sandbox nel
  tempo in cui Meta approva, quindi si può provare tutto il percorso adesso.

  **Conseguenza da sapere prima del go-live**: una volta attivi i template, i
  campi `whatsapp_booking_message` e `whatsapp_reminder_message` in
  Impostazioni **non cambiano più** quello che la cliente riceve — comanda il
  testo approvato da Meta. Restano a governare solo il ripiego. Se il salone
  vuole cambiare un messaggio, va cambiato il template e rifatta approvare.

  13 test nuovi, 658 in tutto. Verificati rompendoli: rimesso il promemoria a
  `Body` cadono due test, scambiati i SID di conferma e promemoria ne cadono
  due — ed è l'errore da copia-incolla più probabile fra queste due funzioni,
  che manderebbe «confermata» il giorno prima e «ti ricordiamo» alla
  prenotazione.

  Il messaggio libero dalla pagina Messaggi resta scoperto **per forza**: un
  testo scritto a mano non può essere pre-approvato, quindi arriva solo a chi
  ha scritto nelle ultime 24 ore. Non è un difetto da correggere, è come
  funziona WhatsApp; sta scritto nel docstring perché non venga «sistemato»
  per sbaglio.
- [x] ~~**Reset password cliente dal pannello admin**~~ — fatto 2026-08-11.
  `POST /api/admin/clients/{client_id}/reset-password`, `require_admin`
  (stessa famiglia del merge: dà accesso all'account di un'altra persona,
  non è consultazione). Pulsante «Password portale» sulla scheda cliente,
  visibile solo se la cliente ha un account online.
  Due cose emerse leggendo il flusso, che non erano nell'idea iniziale:
  - il reset azzera `reset_token`, altrimenti un link chiesto per email e
    mai usato resterebbe valido e sovrascriverebbe la password appena
    dettata al telefono;
  - su un account con email non verificata la rotta **rifiuta**: il login
    blocca comunque quegli account, quindi cambiare la password non farebbe
    entrare nessuno e l'operatore non capirebbe perché. La strada per quel
    caso è rimandare il codice. Verificare l'indirizzo da qui non è
    un'opzione: è la prova che l'indirizzo è suo, e da quella prova dipende
    l'aggancio alla scheda del salone.
  Minimo password 10 e non 12 come lo staff: è il minimo del portale, e uno
  più alto solo qui durerebbe fino al primo cambio password della cliente.
  Nel registro l'evento è `reset_password_eseguito` con `via=admin`, per
  distinguerlo da quello self-service che scrive lo stesso nome.
- [x] ~~**Accesso al portale creato dal salone**~~ — fatto 2026-08-25.
  `POST /api/admin/clients/{client_id}/portal-account`, `require_admin`.
  Pulsante «Crea accesso portale» sulla scheda cliente, dove prima c'era il
  vuoto: i due pulsanti si alternano, perché sono lo stesso posto in due
  momenti — prima si crea l'accesso, dopo si rigenera la password.
  Chiude il caso più comune di tutti: una cliente iscritta al banco non
  aveva `account_id`, quindi nessun modo di entrare, e in un salone al banco
  ci finisce quasi tutta l'anagrafica.

  **La richiesta era una password di default tipo `0000`, e non si è fatta
  così.** Un valore uguale per tutte non è una password: chi conosce
  l'indirizzo email di una cliente — che in un salone di quartiere è la cosa
  meno segreta che ci sia — entrerebbe nel suo account e ne leggerebbe lo
  storico. È la stessa famiglia di `admin123`, chiusa nell'audit di agosto,
  moltiplicata per ogni cliente invece che su un solo account demo. Al suo
  posto una password **casuale per account**, mostrata una volta sola a chi
  la crea. Stesso alfabeto dei codici gift card e per la stessa ragione:
  niente `0`/`O` né `1`/`I`/`L`, perché viene dettata al telefono.
  `test_due_clienti_non_ricevono_la_stessa` è la regressione contro il
  ritorno dell'idea.

  **`email_verified=True` alla creazione, ed è la decisione che pesa.**
  Senza, il login rifiuta l'account e la password consegnata non apre
  niente. La verifica per email serve a dimostrare che l'indirizzo è di chi
  lo ha digitato, e qui a digitarlo è il salone con la cliente davanti — la
  stessa fiducia su cui poggiano già gli accessi dello staff, che di
  verifica non ne hanno affatto. Il prezzo, scritto in chiaro perché è
  reale: un indirizzo sbagliato di battitura diventa un account funzionante
  intestato a un estraneo, che con «password dimenticata» potrebbe
  entrarci. Per questo la schermata chiede di rileggere l'indirizzo **prima**
  di creare, non dopo.

  Tre rifiuti, tutti prima di scrivere una riga: cliente che ha già un
  account, cliente senza email, e indirizzo già usato — dallo staff o da un
  altro account cliente. L'ultimo non è formalità: `ClientAccount.email` è
  unique, quindi senza controllo arriverebbe un 500 dal database invece di
  una frase leggibile (verificato togliendolo: esce l'`IntegrityError`).
  Su un account non verificato lasciato a metà da una registrazione la
  rotta **rifiuta invece di sovrascrivere**, al contrario di `register`: lì
  è giusto perché un account non verificato non prova niente, qui no perché
  a quell'account può essere già appesa una scheda cliente, e assorbirla in
  silenzio sposterebbe dati fra due persone che nessuno ha confrontato.

  La password in chiaro esce **solo** nella risposta del `POST` che l'ha
  generata, con uno schema suo (`PortalAccountCreated`) e non dentro
  `ClientOut`: un campo password su un modello di lettura prima o poi
  comparirebbe in una risposta di elenco. Nei log non entra — verificato con
  un test che cerca proprio quella stringa in tutti i record emessi.
  Nel registro l'evento è `registrazione` con `tipo=creato_da_admin`, stesso
  nome di quella dal portale: chi cerca «quando è nato questo account» ha
  una riga sola da cercare.

  23 test nuovi, 645 in tutto. Le quattro protezioni che contano sono state
  verificate **rompendole**: tolto `email_verified` cadono i due test di
  login, resa fissa la password ne cadono due di generazione, tolta ognuna
  delle due guardie sulle collisioni cade la sua. Provato anche nel browser
  sul database di sviluppo: accesso creato per una cliente demo, password
  `3CHQ-…` usata per entrare davvero sia dal portale sia dalla schermata
  unica (200 e token emesso), e il caso «scheda senza email» che mostra il
  messaggio col pulsante disabilitato.

  **Resta fuori, di proposito**: il cambio password obbligatorio al primo
  accesso. Servirebbe una colonna `must_change_password` più una migration
  e un passaggio in più nel login, ed è una funzione a sé — oggi la cliente
  la password può cambiarla dal portale, ma nessuno la obbliga.
- [x] ~~`SEED_DEMO` da disattivare~~ — verificato 2026-08-01: `SEED_DEMO=false`
  sul backend, non impostata sul worker. Anche se tornasse `true` non
  succederebbe nulla: `seed_demo()` esce subito se esiste almeno un servizio,
  e in produzione ce ne sono 19 reali coi prezzi del salone.
- [x] ~~(Opz.) Dominio + branding `noreply@newstylehair.it`~~ — fatto 2026-08-11.
  Dominio comprato su Aruba, autenticato su Brevo con 4 record DNS (TXT
  verifica, due CNAME DKIM, TXT DMARC `p=none`). `EMAILS_FROM_EMAIL` cambiata
  su Railway, redeploy fatto. Verificato con un invio vero
  (`forgot-password` su un account reale): `reset_password_chiesto` nei log
  di produzione, nessun errore, email arrivata. Il vecchio mittente Gmail
  non è più usato per la posta transazionale.
- [x] ~~`notify_new_booking` è solo un `print()`~~ — fatto 2026-08-02. Erano tre
  bug in fila, non uno: l'endpoint non accodava niente, il task stampava e
  basta, e accodare prima del commit avrebbe fatto trovare al worker una
  prenotazione che ancora non esiste. Ora la richiesta parte via email a tutti
  gli admin attivi + al collaboratore prenotato (chiunque possa rispondere:
  confermare è un permesso `staff`, non solo admin). Niente WhatsApp allo
  staff: passerebbe dalla stessa Sandbox Twilio che parla solo con chi ha
  mandato `join`, quindi sarebbe un canale che perde i messaggi in silenzio.
  *Il motivo è superato dal 2026-09-17* (niente più Sandbox). Resta vero che
  servirebbe un template approvato apposta, perché è il salone a scrivere
  per primo. La scelta non è stata riaperta.

---

## Roadmap go-live clienti reali

### WhatsApp produzione — DECISIONE numero: PRESA il 2026-08-25

> ⚠️ Questa sezione registrava una scelta ancora aperta e **consigliava lo
> Scenario B**. La decisione è stata presa, ed è **A**. Resta scritta perché
> il ragionamento che ha fatto scartare B è la ragione per cui A oggi
> funziona.

Vincolo Meta/Twilio: un numero può stare su WhatsApp in UN solo posto — app
Business *oppure* API.

- **Scenario A — il fisso esistente passa all'API** ✅ **scelto.** Si perde
  l'app WhatsApp Business manuale su quel numero.
- ~~**Scenario B — numero nuovo dedicato**~~: SIM nuova per le notifiche, il
  numero attuale resta sull'app per le chat a mano.

**Perché B non serve più.** B era consigliato per non perdere la chat
manuale: era l'unico modo di rispondere a una cliente. Nel frattempo quella
capacità è stata costruita **dentro il gestionale** — il webhook salva ogni
messaggio in entrata e la pagina Chat permette di rispondere — quindi
passare all'API non toglie più niente, sposta soltanto dove si risponde.
Con B, invece, le clienti si sarebbero trovate due numeri del salone.

Il go-live vero e proprio dei dettagli operativi sta nella sezione in cima
al file, che è quella aggiornata.

**I passi operativi stanno in cima al file, in una lista sola.** Qui ce n'era
una seconda copia: teneva ancora «numero nuovo per lo Scenario B» dopo che B
era stato scartato, e diceva «1 variabile, zero codice» dopo che quella frase
si era rivelata sbagliata. Due liste della stessa cosa divergono sempre, e
quella che si legge non è mai quella aggiornata — quindi ne resta una.

### Altri step go-live
- [x] **Accessi dei collaboratori** — 2026-07-29: tutti e tre creati e collegati
  al rispettivo profilo in agenda. Nessun collaboratore resta senza account.

  | Collaboratore | Profilo agenda | Account |
  |---|---|---|
  | Flavia Romolo | id 4 | ✅ `flaviaromolo400@gmail.com` |
  | Raffaella Bozza | id 5 | ✅ `raff8541@gmail.com` |
  | Vincenzo Romolo | id 6 | ✅ `vincenzoromolo75@gmail.com` |

  Password temporanee generate e comunicate a voce, da cambiare al primo accesso
  da Team e accessi. Permessi verificati in produzione per tutti: calendario,
  clienti e chat sì; dashboard, incassi, spese, team e impostazioni no.
- [x] ~~Servizi assegnati a ciascun collaboratore~~ — verificato 2026-08-01 su
  produzione: **19 servizi su 19** hanno almeno un operatore, quindi nessuno
  può scegliere un servizio e trovare il passo "Con chi" vuoto.
  Flavia 16 (colore, taglio, trattamenti), Raffaella 8 (colore e styling),
  Vincenzo 7 (barbiere: barba, taglio uomo/bambino, taglio+barba).
- [x] Telefoni clienti in E.164 — 2026-07-29: normalizzati automaticamente in
  scrittura (`app/utils/phone.py`), si possono digitare in qualunque formato.
  Serviva perché la registrazione online e la chat WhatsApp cercano il cliente
  per telefono confrontando stringhe: `333 287 6794` e `+39 333 287 6794`
  creavano due schede separate. Per dati importati da fuori:
  `python scripts/normalise_client_phones.py` (dry-run, `--apply` per scrivere).
  Le **email** restano case-sensitive per scelta: normalizzarle tocca anche il
  login, quindi richiede una migrazione dati contestuale.
- [x] **Verifica email alla registrazione** — 2026-07-29: codice a 6 cifre
  inviato per email, valido 15 minuti, 5 tentativi. L'account non ha sessione
  finché il codice non è inserito, e il login (sia dal portale sia dalla
  schermata unica) rifiuta gli indirizzi non verificati. Un'iscrizione non
  verificata non blocca l'indirizzo: chi si registra dopo la sovrascrive, così
  nessuno può occupare l'email di un altro.
- [x] ~~**Verifica del numero di telefono**~~ — **implementata e verificata
  il 2026-09-22**, in produzione dietro `TWILIO_TEMPLATE_VERIFICA`. Prima
  nulla impediva di inserire il numero di qualcun altro, che si sarebbe
  ritrovato i messaggi WhatsApp del salone.
  ~~**Prerequisito**: WhatsApp fuori dalla Sandbox Twilio~~ — soddisfatto
  il 2026-09-17. Serviva un **template di categoria Authentication**: un
  codice di verifica è un messaggio che il salone manda per primo, quindi
  fuori dalla finestra di 24 ore, e Meta vuole i codici usa-e-getta in
  quella categoria — i due template approvati sono Utility e non vanno bene.
  Confrontato con l'alternativa SMS Twilio (~$0.09 a messaggio in Italia,
  contro ~$0.004–0.046 per un template Authentication — un ordine di
  grandezza in meno) prima di scegliere: WhatsApp vince, stesso canale già
  in uso e nessun flusso a parte da gestire, al prezzo di aspettare
  l'approvazione Meta.

  **Template creato e sottomesso il 2026-09-22**: `verifica_telefono`,
  `HXf10735654fffde097632a871533e8d87`, lingua `it`. Il corpo è preimpostato
  da WhatsApp — non personalizzabile, «custom authentication templates
  aren't allowed» — e Twilio ci mette dietro solo `code_expiration_minutes`
  (messo a **15**, lo stesso della verifica email:
  `email_verification.CODE_TTL_MINUTES`, per non promettere alla cliente un
  tempo diverso da quello vero) e un bottone «Copia codice». Stato in
  ~~`received`, in attesa di revisione Meta come gli altri due (1-2
  giorni)~~ — **approvato il 2026-09-22, meno di un'ora dopo la
  sottomissione**: molto più veloce degli altri due, che avevano preso
  fino a un giorno.

  **Prova vera fatta lo stesso giorno**, dal numero ponte al telefono di
  Lorenzo, con codice finto `482913`. Testo letto dalla risposta di Twilio,
  non stimato:

  > *482913 è il tuo codice di verifica. Per garantire la tua sicurezza, ti
  > consigliamo di non condividere questo codice.*

  più bottone «Copia codice». La riga sulla scadenza (15 minuti) non
  compare nel corpo — WhatsApp la mostra altrove, non nel testo.
  Consegnato e letto (`status: read` via API). **«New Style Hair» in cima
  alla chat**, confermato a vista sul telefono: è il nome del Sender, non
  il corpo del template — quello Meta lo vieta esplicitamente di
  personalizzare («custom authentication templates aren't allowed», niente
  URL, emoji o testo libero), per lo stesso motivo per cui un OTP non deve
  poter somigliare a un messaggio di phishing.

  ### Il collegamento vero, fatto lo stesso giorno

  **Decisioni prese prima di scrivere codice** (chieste esplicitamente,
  perché cambiavano la forma del lavoro): il passo è **obbligatorio**, come
  l'email oggi — nessun modo di saltarlo — e riguarda **solo le nuove
  registrazioni**. Chi si era già registrato prima che questo esistesse
  resta com'è, nessuna richiesta retroattiva.

  **Schema**: quattro colonne su `ClientAccount`
  (`phone_verified`, `phone_verification_code_hash`,
  `phone_verification_expires`, `phone_verification_attempts`), stesso
  disegno delle quattro già lì per l'email. Migrazione
  `f8a2e916c4d3`: grandfathering per righe esistenti
  (`UPDATE ... SET phone_verified = true`), stesso schema già usato per
  l'email in `d7a1c93f2b48` — verificato applicandola su un database con
  una riga pre-esistente, non solo letto dal file.

  **Perché sull'account e non sulla scheda cliente**, dove il numero vive
  davvero: rispecchia `email_verified`, un controllo di una sola tabella al
  login invece di un join, e i due nascono comunque insieme alla
  registrazione.

  **Il flusso cambia**: `verify-email` non dà più la sessione subito. Se il
  telefono è già verificato (grandfathered, o già fatto) la sessione parte
  come prima; altrimenti risponde `phone_verification_required` e manda il
  codice WhatsApp — la sessione arriva solo da `verify-phone`, il passo
  nuovo. Login (sia il portale sia la schermata unica staff+clienti)
  rifiuta anche il telefono non verificato, stesso schema del controllo
  sull'email che c'era già.

  **Chi salta il passo, di proposito, con la stessa nota già scritta per
  l'email** (`portal_account.py`): un accesso creato dal salone al banco,
  con la cliente davanti che detta il numero — stessa fiducia già concessa
  per l'indirizzo.

  **Verificato, non solo scritto**:
  - 726 test passano (20 nuovi: `tests/test_phone_verification.py` per
    esteso, più gli aggiustamenti a `test_email_verification.py` e
    `test_registration_takeover.py` che il nuovo secondo passo rompeva).
  - 4 punti della logica nuova falsificati uno per uno (tolti a mano,
    verificato che il test giusto torna rosso, rimessi): l'ordine
    email-poi-telefono, il salto per chi è già verificato, e il rifiuto al
    login su entrambe le rotte.
  - Migrazione provata per davvero: applicata da vuoto, il backfill
    controllato su una riga pre-esistente, e il downgrade.
  - **Prova end-to-end nel browser, con un WhatsApp vero**: registrazione
    compilata a mano, codice email letto dal database locale, codice
    telefono arrivato per davvero sul numero di Lorenzo — letto da lui,
    non simulato — e la sessione finale che apre il portale con la
    schermata di benvenuto.

  **`TWILIO_TEMPLATE_VERIFICA` — controllata su Railway prima di chiudere
  questa voce, e non c'era**: a differenza degli altri due template, questo
  non era mai stato impostato né su backend né su worker. Senza, il codice
  di verifica sarebbe partito come testo libero — che WhatsApp rifiuta fuori
  dalla finestra di 24 ore, cioè sempre, essendo il salone a scrivere per
  primo. Impostata ora su entrambi i servizi (stesso SID approvato,
  `skip_deploys` per non far ripartire il deploy prima che il codice ci sia
  davvero): arriverà con il rilascio di questa PR.

  ~~«Resta da fare quando è approvato: la variabile su Railway e il
  collegamento vero»~~ — **scritto quando esisteva solo il template, ed è
  stato superato lo stesso giorno.** Entrambe le cose sono fatte e
  descritte qui sopra: la variabile è su backend e worker, il collegamento
  è `app/services/phone_verification.py` con i due passi in
  `api/public/auth.py`. Lasciata la riga barrata invece di cancellarla
  perché la contraddizione fra due paragrafi vicini è l'errore che questo
  documento ha già fatto due volte in cima.
- [x] ~~**Pulizia dei profili cliente di prova**~~ — **fatta il
  2026-09-23**, e non come «pulizia»: svuotate del tutto anagrafica,
  account del portale e appuntamenti. Il come, e i quattro punti qui
  sotto che l'hanno guidata, restano scritti perché servono la prossima
  volta. Resoconto in fondo alla voce.

  Prima di toccare qualcosa:
  1. **Decidere il criterio** di «di prova» (nome, email, data di
     creazione, nessun appuntamento…) ed estrarre l'elenco in **sola
     lettura** dalla produzione. Nessuna cancellazione senza l'elenco
     approvato scheda per scheda.
  2. **«Elimina» dal gestionale non cancella**: mette solo
     `Client.is_active = False` (`api/admin/clients.py:123`). La scheda
     sparisce dagli elenchi ma resta a database.
  3. **Chiude il portale, ma non il login.** ~~«E non chiude il portale:
     vedi fra i difetti aperti»~~ — quel difetto è stato corretto, la voce
     è più su in questo file. Oggi `_cliente_del_portale`
     (`api/public/booking.py:47`) filtra su `Client.is_active`, quindi una
     scheda eliminata non prenota, non cancella e non entra in lista
     d'attesa. Resta però valido il **login**: `ClientAccount.is_active` è
     un interruttore separato, e chi accede si trova «Profilo cliente non
     trovato». Per un profilo di prova conviene disattivare anche
     l'account — non più per sicurezza, solo per non lasciare un accesso
     che porta a una schermata rotta.
  4. Una cancellazione vera è bloccata dagli appuntamenti
     (`ondelete="RESTRICT"`); pagamenti, chat, comunicazioni e buoni regalo
     restano ma perdono il cliente (`SET NULL`); la lista d'attesa se ne va
     con lui (`CASCADE`). Per i doppioni c'è già **Unione schede**, che va
     preferita alla cancellazione.

  **Com'è andata (2026-09-23).** L'estrazione del punto 1 ha trovato **sei**
  schede, e il criterio «di prova» **non si poteva applicare**: nomi veri,
  Gmail veri, cellulari italiani veri, tutte con account verificato. Niente
  che da fuori distinguesse una prova da una cliente — una aveva perfino un
  appuntamento *confermato*. Messo l'elenco davanti, la decisione è stata
  di svuotare tutto: il salone non ha ancora clienti veri a sistema, quindi
  l'anagrafica intera era il banco di prova.

  Cancellati: **4 appuntamenti** (più i 4 `appointment_services`, portati
  via in `CASCADE`), **6 clienti**, **6 account del portale**. Restano
  intatti **19 servizi**, **13 prodotti**, **3 collaboratori** — verificato
  confrontando i conteggi prima e dopo, non fidandosi dell'intenzione.
  `/health` 200 e frontend 200 dopo l'operazione, nessun errore nei log.

  Due precauzioni che vale la pena ripetere:
  - **Copia di sicurezza prima**, JSON di tutte le tabelle coinvolte. È ciò
    che ha reso reversibile una cosa che di suo non lo è. Contiene dati
    personali: sta fuori dal repository e va cancellata quando non serve.
  - **Una transazione sola.** A metà strada il database sarebbe rimasto in
    uno stato che nessuno ha scelto — appuntamenti orfani senza cliente.

  **La conversazione WhatsApp**, lasciata indietro al primo giro perché non
  era nella richiesta, è stata tolta subito dopo su conferma: 1
  conversazione e i suoi 5 messaggi (`CASCADE`). Vale la pena sapere che le
  conversazioni sono indicizzate per **numero di telefono**, non per
  cliente — svuotare l'anagrafica non le porta via, restano con `client_id`
  a `NULL`. Chi rifà questa pulizia deve cancellarle a parte.

  Stato finale del database: anagrafica, account, appuntamenti e chat a
  zero; servizi, prodotti e collaboratori intatti.
- [x] ~~Stessa gara di commit sul lato admin~~ — fatto 2026-08-02, trovata
  mentre si sistemava `notify_new_booking`. In `api/admin/appointments.py`
  `_trigger_booking_confirmation` partiva dopo `flush()` ma prima che `get_db`
  facesse commit: alla creazione di un appuntamento il worker poteva non
  trovare la riga e la conferma al cliente non partiva mai, senza una riga di
  log. Alla conferma di una richiesta il difetto era più sottile — la riga
  c'era, ma con lo stato ancora `pending`. Ora entrambe committano prima di
  accodare. Regressione in `tests/test_admin_confirmation_commit.py`, che legge
  da una connessione separata nell'istante in cui l'id viene passato.
- [x] Dati reali: collaboratori creati con orari lun–ven 08:00–19:00
- [x] Cambiare password admin demo (`admin123`) — 2026-07-28: email → `newstylehair2019@gmail.com`,
  password ruotata (generata e mostrata una volta in chat, da salvare in un password manager)
- [x] **Cambio password dal gestionale** — 2026-07-29: pagina "Team e accessi" con
  creazione login, reset password da admin e cambio password self-service.
- [x] `SECRET_KEY` robusta in prod — 2026-07-29: 64 caratteri esadecimali
  (256 bit), non è il default `changeme` di `config.py`, identica su backend e
  worker, assente dal servizio frontend. Contava perché firma i token di admin,
  collaboratori **e** clienti: chi la conosce entra come admin senza password, e
  il default è leggibile in questo repository pubblico. Verificata per hash,
  senza esporre il valore. Da ruotare solo se finisce in una chat, in un commit
  o se si perde un dispositivo con accesso a Railway — la rotazione disconnette
  tutti, refresh token compresi.
- [x] Disattivare `SEED_DEMO` + svuotare dati demo — 2026-07-29: clienti, appuntamenti,
  pagamenti, prodotti e spese demo cancellati; collaboratori e servizi demo rimossi.
- [x] **Limiti di spesa Railway** — verificato via `railway usage`: soft $5,
  hard $10. Sono due cose diverse: il soft **avvisa**, l'hard **spegne i
  servizi**. Un hard a $5 secco rischierebbe di mandare offline il salone senza
  preavviso, quindi il margine fra i due è voluto.

  Consumo reale: $2.00 nel periodo, stima $3.48 — di cui **memoria $1.91**, CPU
  $0.07, volumi $0.02, egress trascurabile. È la RAM a fare il costo.

  Nota: il consumo **è fatturato** (`currentBill` = `currentUsage`), non
  assorbito da un credito incluso. Ridurlo ridurrebbe davvero la spesa, ma le
  cifre in gioco sono di circa un euro al mese e non valgono la perdita di
  affidabilità (vedi il ragionamento su worker e Redis nella cronologia).

  Comandi utili: `railway usage`, `railway usage projects`,
  `railway usage limit status`.

### Allineamento da controllare (go-live)
- [x] `closed_weekdays` allineato — 2026-07-29: confermato chiuso **domenica e
  lunedì**. Orario dei 3 collaboratori aggiornato da lun–ven a **mar–sab
  08:00–19:00** (nessun appuntamento attivo di lunedì nel DB, nessuna
  prenotazione persa).

---

## Sicurezza — audit 2026-08-03

Sette revisioni indipendenti sul codice, ognuna passata da un revisore ostile
che ha riaperto i file citati per provare a demolire i finding. Verdetto:
sistema sostanzialmente sano — confine fra i tre pubblici solido, nessun
segreto nella storia di git, nessun XSS, CSRF o IDOR. Sotto restano solo le
cose ancora aperte; il resto è chiuso.

### Da fare — rotazione credenziali dopo doppia esposizione in chat (2026-08-12)

`list_variables` (MCP Railway) ha ristampato in chiaro nella conversazione,
due volte, tutte le variabili del servizio backend — non un furto, una
chiamata di troppo. Rotazione decisa solo dove la stringa da sola basta a
fare danno (raggiungibile da internet pubblico); le due dietro la rete
privata Railway restano facoltative.

- [x] ~~`SECRET_KEY`~~ — ruotata 2026-08-12, 64 caratteri esadecimali nuovi,
  redeploy verificato (`/health` ok). Effetto: tutte le sessioni JWT
  invalidate, staff e clienti devono rientrare — nessuna perdita dati.
- [ ] `BREVO_API_KEY` — rigenerare su dashboard Brevo, poi aggiornare la
  variabile su Railway (backend + worker). Raggiungibile da internet
  pubblico: la sola stringa basta a mandare email a nome del salone o a
  leggere contatti/statistiche.
- [ ] `SMTP_PASSWORD` (App Password Gmail `newstylehair2019@gmail.com`) —
  revocare e rigenerare da Account Google → Sicurezza → Password per le
  app, poi aggiornare su Railway. Stesso motivo: pubblico, e se l'account
  ha IMAP attivo l'app password può anche leggere la casella.
- [ ] `TWILIO_AUTH_TOKEN` — Twilio supporta rotazione con token secondario,
  zero downtime: farla dalla Console prima di sostituire la variabile.
- [ ] `POSTGRES_PASSWORD` — dietro rete privata Railway, non raggiungibile
  da internet: priorità bassa. Se si fa comunque, **cambiare solo la
  variabile non basta** — il Postgres già acceso non se ne accorge, la
  legge solo al primo avvio. Serve `ALTER ROLE ... PASSWORD` sul DB live
  via tunnel SSH (`railway connect --tunnel-only`, chiave registrata)
  *prima* di aggiornare la variabile, altrimenti backend e worker perdono
  la connessione a metà operazione.
- [x] ~~`REDIS_URL`~~ — ruotata 2026-08-12. `REDIS_PASSWORD` rigenerata sul
  servizio Redis, riavviato, nessun errore nei log del worker dopo il
  redeploy.
  **Guasto reale trovato facendolo**: `REDIS_URL` su backend e worker era
  scritta a mano (valore letterale con la password vecchia), non un
  riferimento a Redis — la rotazione l'avrebbe rotta in silenzio, backend
  e worker avrebbero continuato a provare la password di prima. Convertita
  in riferimento vero (`${{Redis.REDIS_URL}}`) su entrambi i servizi:
  ora una futura rotazione della password su Redis si propaga da sola,
  senza dover toccare backend/worker a mano come stavolta.
- [x] ~~Marcare le variabili sensibili come **sealed** su Railway~~ — fatto
  2026-08-12 per `SECRET_KEY` (backend) e `REDIS_PASSWORD` (Redis): non
  più rileggibili in chiaro da nessuno, `list_variables` compreso. Le
  altre (Brevo, SMTP, Twilio, Postgres) da sigillare quando vengono
  ruotate.

### Chiuso il 2026-08-04
- [x] ~~La prenotazione pubblica accettava `start_time`/`end_time` arbitrari~~ —
  ora lo slot deve comparire in `get_available_slots` e la durata la calcola il
  server dai servizi scelti. Chiude anche il caso che svuotava il calendario
  (una richiesta `pending` occupa lo slot, quindi bastava prenotare 00:00–23:59
  su tutti i collaboratori). Tetto di 3 richieste in attesa per cliente.
- [x] ~~HTML non escapato nelle email~~ — `/register` non è autenticato e
  spediva `first_name` grezzo dal mittente verificato del salone verso un
  indirizzo scelto da chi chiama. Ora `esc()` copre tutti i mittenti.
- [x] ~~`SECRET_KEY = "changeme"` e `ADMIN_PASSWORD = "admin123"`~~ — fuori da
  `APP_ENV=development` l'app non parte e il bootstrap non crea l'admin.
- [x] ~~`python-multipart` 0.0.20~~ → 0.0.31 (GHSA-5rvq-cxj2-64vf, parsing
  quadratico raggiungibile prima della verifica firma sul webhook Twilio).
- [x] ~~La registrazione agganciava l'anagrafica su un telefono mai
  verificato~~ — l'aggancio si è spostato in `verify-email` e ora avviene solo
  sull'**indirizzo dimostrato**, e solo su una scheda che non appartiene già a
  qualcun altro. Chi conosce il numero di una cliente non ne legge più lo
  storico, non la stacca dalla sua scheda e non le sovrascrive l'email.
  **Conseguenza voluta**: una cliente già seguita in salone di cui si conosce
  solo il telefono (email assente o diversa) genera ora una **seconda riga**,
  che il salone unisce a mano. Due schede da fondere battono una fusa per
  sbaglio. La verifica del numero via WhatsApp, quando arriverà, renderà di
  nuovo automatico anche quel caso — ma la guardia su `account_id` resta
  necessaria comunque, perché due persone possono condividere un numero.
  Nota: il confronto sull'email è esatto, maiuscole comprese (scelta già presa
  altrove nel progetto), quindi `Mario.Rossi@` e `mario.rossi@` restano righe
  distinte.

### Da fare — in ordine di resa
- [x] ~~**Spegnere i proxy TCP pubblici** di Postgres e Redis~~ — fatto
  2026-08-04. Ricontrollato oggi: nessuna variabile `RAILWAY_TCP_PROXY_*` su
  nessuno dei due servizi. Backend e worker parlano dagli host
  `*.railway.internal`, quindi non è caduto niente. Per la manutenzione serve
  un tunnel SSH (`railway connect postgres --tunnel-only`), e va **chiuso
  controllando la porta con `lsof`**, non il processo con `ps`: il wrapper
  muore e l'`ssh -N -L` figlio resta in ascolto per conto suo.
- [x] ~~**Rate limiting**~~ — fatto 2026-08-05, `slowapi` su otto rotte:
  register 5/ora, resend-code e forgot-password 3/ora, login (tutti e tre gli
  ingressi: admin, cliente, unificato) 10/min, verify-email e reset-password
  10/min. Nessun limite di default: l'agenda dal salone viene interrogata di
  continuo e un tetto lì bloccherebbe chi lavora.
  **La chiave del conteggio: `X-Envoy-External-Address`, altrimenti la
  *prima* voce di `X-Forwarded-For`.** La prima versione prendeva l'ultima
  voce, ragionando che fosse l'unica non scrivibile dal chiamante. Giusto in
  generale, falso su Railway: accoda l'IP di un suo nodo interno che **cambia
  a ogni richiesta** (`100.64.0.2`, `.3`, `.4` nei log). Ogni richiesta
  prendeva una chiave diversa, quindi un secchio nuovo, quindi **nessun
  limite**: provato in produzione, dodici login sbagliati di fila passavano
  tutti. Trovato solo perché il tetto è stato verificato sul servizio vero
  dopo il rilascio — in locale e nei test funzionava.
  La prima voce di `X-Forwarded-For` è falsificabile e va detto: chi la
  cambia a ogni richiesta si compra un secchio nuovo. Resta meglio
  dell'alternativa reale, che non era «un limite inviolabile» ma «nessun
  limite».
  **Se Redis non risponde si continua a contare in memoria**
  (`in_memory_fallback_enabled` + `swallow_errors`). Non è un dettaglio:
  provato dal vivo, senza quello con Redis spento **ogni login rispondeva
  500** — il salone chiuso fuori dal proprio gestionale perché è caduta una
  cache. Fino a ieri Redis giù voleva dire solo notifiche non spedite.
- [x] ~~**bcrypt fuori dall'event loop**~~ — fatto 2026-08-05.
  `hash_password`/`verify_password` sono ora `async` e girano in
  `run_in_threadpool`; `issue_code`/`check_code` sono diventate async di
  conseguenza — erano proprio quelle che si dimenticano.
  Le versioni sincrone restano come `hash_password_sync` /
  `verify_password_sync` per seed, bootstrap e la rotazione password, che
  girano fuori da un event loop.
  **I nomi brevi sono quelli async di proposito**: chi scrive un endpoint
  nuovo digita `hash_password` e prende quella giusta, e se dimentica
  l'`await` si ritrova una coroutine al posto dell'hash — errore rumoroso
  invece di un rallentamento silenzioso di tutta l'applicazione. È successo
  davvero durante il lavoro, ed è stato immediato accorgersene.
- [x] ~~**Unione schede duplicate**~~ — fatto 2026-08-05.
  `POST /api/admin/clients/{id}/merge` più `GET .../merge-preview`, admin, con
  `app/services/client_merge.py` a fare il lavoro.
  **Chi resta lo sceglie l'operatore, non un'euristica.** La destinazione sta
  nell'URL. «Vince la più vecchia» o «vince quella con più appuntamenti»
  sarebbero entrambe ragionevoli e ogni tanto sbagliate, e l'operazione non si
  annulla: il codice esegue invece di indovinare.
  L'ordine di spostamento non è alfabetico. `waitlist_entries` va per prima
  perché è l'unica in `CASCADE`: sparirebbe con la scheda. `appointments` è in
  `RESTRICT` e blocca la cancellazione finché punta lì. Le altre quattro sono
  `SET NULL`, cioè diventerebbero righe orfane — un incasso senza cliente.
  I campi vuoti della destinazione si riempiono, quelli pieni **non** si
  sovrascrivono; le note si concatenano invece di sceglierne una, perché sono
  testo libero del salone (allergie, preferenze) e scartarne metà perde sapere
  che non sta scritto altrove.
  Due account del portale **rifiutano** la fusione: vuol dire due persone con
  due password, e unirle ne chiuderebbe fuori una senza dirglielo. Il controllo
  sta prima di spostare qualunque riga — c'è un test che verifica proprio che
  un rifiuto non lasci le cose a metà.
  La scheda di partenza viene **disattivata, non cancellata**, come fa già
  `DELETE /api/admin/clients`, con una nota che dice dove è finita.
  Anteprima e esecuzione condividono la stessa funzione con un flag `applica`,
  non due copie delle regole: due copie divergono, e il giorno che divergessero
  l'anteprima mostrerebbe una cosa e la fusione ne farebbe un'altra. C'è un
  test che le confronta.
  Provato nel browser sul database di sviluppo: l'anteprima ha annunciato «6
  appuntamenti, 1 pagamento, 1 conversazione WhatsApp» e il pulsante di
  conferma resta disabilitato finché quell'anteprima non è arrivata.
- [x] ~~**Due `scalar_one_or_none()` ancora esposti in `availability.py`**~~ —
  fatto 2026-08-05. Erano gli ultimi due della famiglia chiusa il 2026-08-04
  sulle assenze.
  **Nessun vincolo unico in migration, ed è la decisione che conta**: più
  righe sulla stessa data non sono un errore da vietare, sono il **turno
  spezzato** — mattina, pausa pranzo, pomeriggio — che in un salone è la
  norma. Un vincolo unico avrebbe reso impossibile una cosa legittima per
  chiudere un bug che si chiude leggendo tutte le righe.
  Quindi si tengono come fasce separate, e **non si fondono**: unire 09–13 e
  15–19 in 09–19 aprirebbe alle prenotazioni due ore in cui non c'è nessuno.
  Un appuntamento deve stare dentro una fascia, non a cavallo di due: un
  colore da due ore non può cominciare alle 12 e finire dopo pranzo.
  Verificato al contrario: rimettendo le due vecchie query, cinque test
  falliscono.
- [x] ~~**Ordine dei controlli in `services/images.py`**~~ — fatto 2026-08-05,
  e meglio di come diceva questa riga. Spostare l'allowlist *fra* `open()` e
  `load()` avrebbe fermato la decodifica ma non il parsing dell'header, che è
  già codice C su byte scelti da chi carica. L'elenco è finito invece **dentro**
  `Image.open(formats=...)`: Pillow prova soltanto i tre plugin ammessi, quindi
  di un TIFF malevolo non viene letta nemmeno l'intestazione.
  Il tetto sui pixel (50 MP) si conta sull'header, prima di allocare. Il limite
  in byte non bastava: la compressione fa sì che 78 kB dichiarino 81 MP, e la
  tela va in RAM decompressa, non compressa.
  Il commento "Pillow refuses absurd pixel counts on its own" era sbagliato
  come sospettato — Pillow avvisa a 89 MP e solleva solo al doppio, ~178 MP =
  mezzo giga di RAM. Rimosso.
  `ALLOWED_FORMATS` è passata da `set` a tupla, perché è ciò che
  `Image.open(formats=)` accetta; c'è un test apposta, altrimenti un
  `TypeError` uscirebbe come «immagine danneggiata», cioè un errore nostro
  addebitato a chi carica il file.
  Verificato al contrario: rimettendo il vecchio ordine due test falliscono —
  uno spia `TiffImageFile._open` e lo vede chiamato, l'altro spia
  `PngImageFile.load` e vede i pixel allocati prima del rifiuto.
- [x] ~~**Open redirect** in `LoginPage.tsx`~~ — fatto 2026-08-05. Erano
  **due** i punti di uscita, non uno: login e registrazione. Ora il parametro
  passa da un filtro che accetta solo percorsi interni.
  `//` è la parte che si dimentica: per il browser `//host` è un URL assoluto
  con lo schema corrente, non un percorso — e così `/\host`, che alcuni
  browser normalizzano allo stesso modo. Un controllo che si fermasse a
  «inizia con /» li lascerebbe passare entrambi.
  L'unico che genera `next` è `RequireClient`, che passa un
  `location.pathname`: il flusso legittimo non cambia.
- [x] ~~**`visit_notes` fuori dal portale**~~ — fatto 2026-08-04, e proprio
  come diceva questa riga: **prima** di iniziare a usarla. Le due rotte
  pubbliche degli appuntamenti ora rispondono con `PortalAppointmentOut`,
  che elenca i campi permessi invece di toglierne due — così un campo nuovo
  sul modello non esce dal portale per distrazione. Fuori anche `notes`, che
  dal calendario la scrive il salone. Dentro resta `rejection_reason`: è la
  spiegazione di un rifiuto, scritta per chi l'ha subito.
- [x] ~~**Dependabot + `pip-audit` in CI**~~ — fatto 2026-08-05.
  `.github/workflows/audit.yml` trova, `.github/dependabot.yml` porta la
  correzione già scritta. La parte che conta è il `schedule` settimanale, non
  i trigger sulle PR: una falla viene pubblicata quando viene pubblicata, non
  quando qualcuno tocca il codice, ed è precisamente com'è andata col DoS di
  `python-multipart`.
  Non è un check obbligatorio di `main`, di proposito: una falla in una
  dipendenza transitiva non deve poter bloccare il rilascio di una correzione
  che non c'entra — sarebbe un cancello che il giorno che serve si scavalca.
  Ma fallisce davvero: rosso = c'è lavoro in coda.
  **Cosa ha trovato accendendolo: 30 vulnerabilità Python e 14 npm.** Chiuse
  subito le tre pulite — `pillow` 11.0.0 → 12.3.0 (diciassette avvisi, e i
  decoder più brutti erano già fuori portata grazie a `formats=` in
  `images.py`, ma non tutti), `python-jose` 3.3.0 → 3.5.0, `jinja2` 3.1.4 →
  3.1.6. Restano 30 → 10.
  Escluso `ecdsa` PYSEC-2026-1325, l'unico senza una versione corretta: arriva
  da `python-jose[cryptography]` ma i token sono HS256 simmetrici e
  `jwt.decode` fissa l'algoritmo, quindi nessuna curva ellittica viene mai
  toccata. La motivazione sta scritta in `backend/.pip-audit-ignore`, che è la
  regola di quel file.
- [x] ~~**Matrice permessi pronta per FastAPI 0.141**~~ — fatto 2026-08-05.
  `tutte_le_rotte()` scende nell'albero dei router e passa su **entrambe** le
  versioni, 120 test per parte. Due trappole, trovate provando e non leggendo:
  `_IncludedRouter` **non espone `.routes`** ma `original_router`, quindi una
  ricorsione che cercasse `.routes` gli passa accanto trovando zero rotte e
  credendo di aver finito (primo tentativo, stesso fallimento di prima); e il
  prefisso `/api/admin` non sta nei percorsi interni, che sono relativi, ma in
  `include_context.prefix` — va ricomposto a mano, altrimenti le rotte si
  trovano col nome sbagliato, che per questa matrice è come non trovarle.
  Aggiunti due test che prima mancavano, ed è la parte che conta:
  `test_l_inventario_non_e_vuoto` e `test_una_rotta_nota_e_davvero_sorvegliata`.
  Il motivo è che **il fallimento peggiore di questo file è verde, non rosso**:
  `test_no_unclassified_routes` cerca rotte *nuove*, e su un elenco vuoto non
  ne trova nessuna, quindi passa. Verificato rompendo apposta la ricorsione:
  gli altri diventano rossi, quello passa. Senza la guardia sulla guardia, un
  giorno la matrice avrebbe potuto smettere di guardare qualcosa senza che
  nessuno se ne accorgesse.
- [x] ~~**FastAPI 0.115.6 → 0.141.1 (e con lui starlette 0.41 → 1.4)**~~ —
  fatto 2026-08-05, dopo aver riscritto la matrice: 584 test passano.
  Con questo `pip-audit` resta con **una sola** voce, `ecdsa`, che è quella
  già esclusa con la motivazione scritta. Cioè l'audit Python è verde.
  Chiude anche PYSEC-2026-249 alla radice. Il tetto sul corpo del webhook
  resta comunque dov'è: è una difesa che non dipende da quale versione di
  starlette è installata, e quell'endpoint ha già visto passare due problemi
  della stessa famiglia.
  Sistemate due deprecation che l'aggiornamento ha reso rumorose:
  `HTTP_413_REQUEST_ENTITY_TOO_LARGE` → `HTTP_413_CONTENT_TOO_LARGE` (stesso
  valore) e `Query(regex=)` → `Query(pattern=)` in `dashboard.py`.
  Delle 7 di starlette, sei non ci riguardano: `FileResponse`, `StaticFiles` e
  `HTTPEndpoint` qui non si usano; quelle su multipart passano solo dall'upload
  delle foto prodotto, che è `require_admin` e legge al massimo 10 MB
  (`_read_capped`); quelle sull'header `Host` mordono chi costruisce URL da
  `request.url`, mentre qui il link di reset nasce da `settings.FRONTEND_URL`.
  **La settima sì**, ed è la riga sotto.
- [x] ~~**PYSEC-2026-249: corpo urlencoded senza limiti sul webhook Twilio**~~ —
  fatto 2026-08-05. Trovato leggendo le descrizioni dell'audit invece di
  fermarsi al conteggio: `request.form()` accetta `max_fields` e
  `max_part_size`, li applica al multipart e **li ignora in silenzio** su
  `application/x-www-form-urlencoded`.
  `/api/public/whatsapp/webhook` è senza autenticazione per forza — Twilio non
  può tenere le nostre credenziali — e deve chiamare `request.form()` **prima**
  di `is_valid_twilio_request`, che è a sua volta obbligatorio: la firma si
  calcola sui parametri, quindi per verificarla bisogna prima averli letti.
  Non ha nemmeno un `@limiter.limit`. **Stessa forma esatta del DoS di
  `python-multipart`** già annotato in `requirements.txt`: stesso endpoint,
  stessa ragione — il corpo va letto prima di poter decidere se buttarlo.
  La correzione: un tetto di 64 kB letto **a pezzi**, che si ferma mentre
  legge invece che dopo. `await request.body()` avrebbe già portato tutto in
  memoria prima di poterlo misurare, cioè avrebbe pagato esattamente il costo
  da evitare.
  I byte già limitati tornano al parser di starlette invece di essere
  interpretati a mano con `parse_qsl`. Provato, davano lo stesso risultato su
  accenti, emoji, `+` e `&` — ma la firma si calcola su quei valori, quindi
  qualunque differenza di decodifica in un caso limite non provato si sarebbe
  manifestata come **messaggi veri rifiutati**, che è il guasto peggiore
  possibile per questo endpoint. Così l'unica cosa che cambia è quanto si legge.
  Misurato prima e dopo, stessa macchina: 200.000 campi passavano da 0,42 s a
  0,001 s, e un corpo da 9,6 MB ora costa quanto uno da 64 kB — il tempo è
  diventato costante invece che lineare nella dimensione.
  413 e non 403, benché il 403 dica meno a chi sonda: se un domani un messaggio
  legittimo sforasse, un 403 manderebbe a cercare un problema di firma per ore.
  Verificato al contrario: togliendo il tetto due test falliscono, e uno dei
  due spia `Request.form` per controllare che non venga proprio interpellato —
  perché rifiutare *dopo* aver parsato darebbe lo stesso 413 senza servire a
  niente.
- [x] ~~**PR #65 di Dependabot: il gruppo «minori» contiene FastAPI**~~ —
  chiusa su GitHub, superata: `dependabot.yml` esclude ora `fastapi`,
  `starlette`, `sqlalchemy` e `pydantic*` dal gruppo «minori» (sotto la 1.0
  ogni rilascio è un minor per semver, la riga `ignore` sui major non li
  prendeva), e l'aggiornamento FastAPI 0.115.6 → 0.141.1 è stato fatto a
  parte (voce sopra). Verificato chiusa il 2026-08-12.
- [x] ~~**npm: `axios` e `lodash`**~~ — fatto 2026-08-05. `axios` 1.13.6 →
  1.19.0 chiude ventotto avvisi in un colpo (SSRF, prototype pollution,
  CRLF injection, un paio di ReDoS). `lodash` non era in `package.json`:
  arriva da `recharts`, quindi è stato forzato a 4.18.1 con un `overrides`,
  che è la strada per una dipendenza transitiva che nessuno può aggiornare
  direttamente.
  `npm audit --omit=dev --audit-level=high` adesso esce 0.
- [x] ~~**`react-router` 6 → 7**~~ — fatto 2026-08-05. Zero righe di codice
  toccate: qui si usano solo le API classiche a componenti (`BrowserRouter`,
  `Routes`, `Route`, `Navigate`, `Outlet`, `Link`, `NavLink`, e gli hook
  `useLocation`/`useNavigate`/`useParams`/`useSearchParams`), e la v7 le tiene.
  Quello che la v7 ha rivoluzionato sono i data router — `createBrowserRouter`,
  i `loader`, le `action` — che questo frontend non ha mai usato. React 18.3.1
  soddisfa già il peer `>=18`, quindi nessun aggiornamento a cascata.
  **Il fatto che ha deciso la scelta: non esiste una versione che chiuda
  tutto.** I due avvisi si accavallano —

      open redirect (`<Link>`, `useNavigate`)  6.0.0 – 7.17.0   corretto da 7.18.0
      CSRF in modalità RSC                     7.12.0 – 8.2.0   nessuna correzione

  — quindi qualunque versione che corregga il primo ricade dentro il secondo.
  Restare alla 6.30.4 avrebbe tenuto l'audit verde senza toccare niente, ed è
  proprio per questo che vale la pena scrivere perché è la scelta peggiore:
  la modalità RSC (React Server Components) **non esiste in questa
  applicazione** — è una SPA servita da Vite — quindi il CSRF è irraggiungibile
  per architettura, non per come è scritto un punto preciso. L'open redirect
  invece vive in `<Link>` e `useNavigate`, usati in dodici file: oggi è coperto
  dal filtro in `LoginPage.tsx`, ma è una proprietà del codice di oggi, non una
  garanzia sul tredicesimo file che passerà un valore preso dall'URL.
  L'esclusione motivata sta in `frontend/.npm-audit-ignore`, e per applicarla è
  servito `frontend/scripts/audit.mjs`: `npm audit` da solo non sa escludere un
  singolo avviso, ha solo `--audit-level`, che è una soglia di gravità — alzarla
  per far tacere una voce fa tacere tutte le altre della stessa gravità.
  Verificato nel browser, non solo con typecheck e build: navigazione
  client-side senza ricaricare la pagina, `<Navigate>` che protegge le rotte
  admin, e i payload dell'avviso (`//evil`, `/\evil`, `\\evil`,
  `https://evil`) tutti respinti dal filtro mentre i percorsi legittimi
  passano. Console pulita.
- [x] ~~**Un minimo di logging**~~ — fatto 2026-08-05. Due cose, non una.
  Il **registro degli accessi** (`nsh.accessi`): una riga per richiesta, con
  metodo, percorso, stato, durata, IP e soprattutto **attore** — `admin:3`,
  `client:41`, `anonimo`. È l'unico campo che risponde alla domanda che si fa
  dopo un furto di credenziali, che non è «qualcuno è entrato?» ma «ha aperto
  le schede di chi?». Senza, è un elenco di URL.
  Gli **eventi di sicurezza** (`nsh.sicurezza`): login riusciti e falliti,
  token rifiutati, permessi negati, 429, reset password. Nomi costanti in
  `app/audit.py`, così si cercano per nome invece che per frase.
  Il log distingue «password errata» da «account inesistente», che l'API di
  proposito non fa: cento tentativi su un indirizzo che esiste è qualcuno che
  forza un account preciso, cento indirizzi inesistenti è una lista comprata.
  La distinzione resta nei log e non esce dall'API — c'è un test per
  entrambe le metà.
  **Costo del middleware**: `RegistroAccessi` è ASGI e non `BaseHTTPMiddleware`,
  che sarebbe stato più corto. `BaseHTTPMiddleware` esegue l'app in un task
  separato e le `ContextVar` impostate là dentro non tornano indietro: l'attore
  sarebbe `anonimo` per sempre. Verificato al contrario — rimettendolo, tre
  test falliscono, e uno è una guardia esplicita contro proprio quella
  riscrittura.
  **Cosa non entra nei log**: password, token, codici. Non per disciplina di
  chi scrive la chiamata ma per filtro sul *nome* del campo, più una passata
  sul testo che toglie JWT e header `Bearer`. Email e telefoni mascherati: su
  un login fallito l'indirizzo digitato può essere di qualcuno che non c'entra,
  e un log di sicurezza è a sua volta un archivio di dati personali.
  Conseguenza da ricordare: `code` è fra le parole oscurate, quindi un campo
  chiamato `status_code` sparirebbe. Qui si chiama `stato`.
  **Corretto dopo il primo rilascio**, verificando i log veri invece di
  fidarsi del deploy riuscito: il livello stava in una chiave `livello`, e
  Railway interpreta solo `level` e `message` — tutto il resto lo indicizza
  soltanto. Risultato: ogni riga risultava `info` (è il default per stdout) e
  `@level:warn` non trovava niente, cioè i login falliti erano `WARNING` nel
  codice e indistinguibili dal traffico normale nel posto in cui quei log si
  leggono. Siccome l'unico motivo per cui un login fallito è `WARNING` è
  potersi filtrare, il campo sbagliato annullava la scelta.
  `WARNING` e `CRITICAL` sono mappati a mano su `warn` ed `error`: la
  documentazione dice che i livelli vengono «accostati al più vicino», ma
  quale sia il più vicino a `CRITICAL` è una supposizione, e sbagliarla
  toglierebbe dai filtri proprio le righe più gravi.
  Chiusi per strada anche i ~20 `print()` di notifiche e task, che finivano sì
  nello stdout di Railway ma senza livello — invisibili a un filtro «mostrami
  gli errori» — e il gestore globale delle eccezioni in `main.py`, che
  rispondeva 500 **senza scrivere niente**: con `SENTRY_DSN` non configurato,
  che è il caso oggi, un guasto in produzione spariva del tutto.
- [x] ~~`Field(min_length=10)` su `ClientRegister.password` e
  `PasswordReset.new_password`~~ — fatto 2026-08-05. Dieci e non dodici come
  per lo staff: chi lavora in salone ha accesso a tutta l'anagrafica e alla
  cassa, una cliente solo ai propri appuntamenti. Il minimo vale anche sul
  reset, altrimenti sarebbe la scappatoia — registrarsi con una password
  lunga e accorciarla subito dopo. Alzato anche il `minLength` del form da 6
  a 10, con messaggio in italiano: il 422 di Pydantic arriva in inglese e non
  dice quanti caratteri mancano.

### Deciso di NON fare
Non sono dimenticanze: sono scelte, con la ragione accanto.
- **Token nei cookie httpOnly** — l'app non usa nessun cookie, quindi il CSRF è
  strutturalmente impossibile e non esiste un solo sink XSS. Passare ai cookie
  regalerebbe una superficie CSRF che oggi non c'è.
- **CSP completa** — `default-src 'self'` rompe Radix e recharts (stili inline).
  Solo `frame-ancestors 'none'` e `nosniff`.
- **HSTS** — inutile finché il dominio è `*.up.railway.app`. Diventa sensato con
  `newstylair.it`.
- **Aggiornare Pillow per le 17 CVE** — le gravi non sono raggiungibili in
  questo codice (`paste` a coordinate fisse, `ImageCms` e `ImageFilter` mai
  importati) e l'endpoint è `require_admin`. Vale invece l'ordine dei controlli,
  che è in lista sopra ed è gratis.
- **Sostituire passlib** — zero advisory, e il pin `bcrypt==3.2.2` è proprio ciò
  che evita il crash noto di passlib con bcrypt ≥ 4.1. È manutenzione, non
  sicurezza.
- **Blacklist di token / `jti`** — la revoca esiste già: `is_active` è riletto
  dal DB a ogni richiesta. Manca solo che il *cambio password* sia anch'esso una
  revoca, e la versione economica è una colonna `token_version`.
- **Captcha** — il rate limiting risolve lo stesso problema senza infastidire
  venti clienti veri.
- **Toccare il CORS** — `localhost:5173` in allowlist è sciatto ma innocuo senza
  cookie. Verificato in produzione: `Origin` estranea → 400 senza header.
  Diventa la prima riga da cambiare *se* un giorno si passa ai cookie.

**Da sapere, costo zero**: per cacciare qualcuno la leva è **"disattiva
l'accesso"** (`PUT /api/admin/team/{id}` con `is_active=false`), non "cambio la
password" — quella non invalida nessuna sessione.

---

## Funzionalità richieste

Non bloccano il go-live: il gestionale funziona senza. Stanno qui separate
apposta, così le caselle aperte qui sotto non si confondono con quelle della
roadmap sopra.

### Richiesta — 2026-09-25: le immagini in chat, e da dove vengono i nomi

- [x] **Le immagini non si vedevano perché non venivano salvate.** Il
  webhook registrava un messaggio solo se aveva testo (`if from_phone and
  body`): una foto o un vocale senza didascalia sparivano per intero, senza
  lasciare traccia. Su Twilio ne risultavano 3 — due foto di prova di
  Lorenzo del 22/09 e **un vocale di una cliente del 25/09 alle 08:17**
  (numero …3565), che nessuno ha sentito.
  - `chat_messages.media` (migration `e3c9a1f47b82`): gli allegati dal
    webhook, solo URL `https://api.twilio.com/`.
  - I file restano su Twilio e **vogliono le credenziali dell'account**
    (senza: 401, provato): la pagina li chiede a `GET
    /api/admin/chat/messages/{id}/media/{indice}` (staff), che li scarica e
    li serve senza mai mostrare l'URL. Un tipo che il browser eseguirebbe
    (html, svg, …) si scarica invece di aprirsi.
  - Nella chat: foto, vocali (con «Scarica il vocale»: i `.ogg` di WhatsApp
    non si riproducono su Safari vecchi), video, altri file come download;
    nell'elenco «📷 Foto», «🎤 Messaggio vocale».
- [x] **I nomi.** Con una scheda cliente collegata si vede il nome della
  scheda; senza, quello che la persona si è data **sul suo profilo
  WhatsApp** (`ProfileName`, che Twilio manda con ogni messaggio). Due
  difetti corretti: quel nome si fissava al primo messaggio e non si
  aggiornava più; e la scheda si collegava **solo quando la conversazione
  nasceva** — chi scriveva prima di avere una scheda restava col nome
  WhatsApp per sempre. Ora si collega al primo messaggio utile, se c'è **una
  sola** scheda attiva con quel numero (con due — il fisso di casa — resta il
  nome WhatsApp, che almeno è di chi scrive). Nell'intestazione, se diverso
  da quello della scheda, «su WhatsApp «…»».
- [PR #139](https://github.com/lorenzomelchionna/gestionale_nsh/pull/139)
  → `develop`, [PR #140](https://github.com/lorenzomelchionna/gestionale_nsh/pull/140)
  → `main` (commit `d180d19`), CI verde (8/8 su #140). **Deploy
  confermato** il 2026-09-25 alle 08:41 UTC: backend, frontend e worker
  `SUCCESS`, `Running upgrade d7b2e5a91c30 -> e3c9a1f47b82, add media to
  chat_messages`, bootstrap completato. Dal vivo: `/health` 200, `www` 200;
  allegato senza token → 401; webhook non firmato con allegato → 403; le
  stringhe nuove («Scarica il vocale», «Allegato non disponibile», «su
  WhatsApp «») nel bundle servito.
- [x] ~~**Recuperare i 3 messaggi persi in produzione**~~ — fatto il
  2026-09-25 alle 08:48 UTC, col tunnel aperto da Lorenzo e il suo ok dopo
  il dry-run: `scripts/recupera_allegati_chat.py --apply` → «Recuperati 3
  messaggi»; rilanciato → «Niente da fare». Verificato in sola lettura:
  id 21 e 22 (foto, 22/09 20:37, conversazione di Lorenzo), id 23 (vocale,
  25/09 08:17, conversazione «Raffaele»), con la loro data; la finestra
  della conversazione 4 parte dalle 08:17 del vocale, non dal recupero.
  Alle 08:49 UTC `admin:1` ha aperto la chat e i tre allegati sono stati
  serviti dal vivo (`/media/0` → 200, il vocale in 419 ms) — la prima
  prova in produzione del passaggio dal backend. Aprirle le ha segnate
  lette, per questo `unread_count` risulta 0.
  **Resta da fare**: che Flavia ascolti il vocale di Raffaele e risponda —
  risposta libera possibile fino al 26/09 08:17.
  La password del superuser Postgres è comparsa di nuovo in chat (output
  del tunnel): stessa voce di rotazione già aperta in «Sicurezza».

### Richiesta — 2026-09-25: prenotare senza account

«Prenotare, sia da admin sia dal portale, con nome, cognome e telefono, senza
account; e chi poi si registra con lo stesso nome e numero dev'essere
collegato a quegli appuntamenti.» Tre decisioni prese con Lorenzo prima di
scrivere codice: dal portale **serve il codice WhatsApp** al numero;
alla registrazione si collega per **numero + nome + cognome**; chi non ha
account **disdice contattando il salone** (nessun link personale).

- [x] **Portale** — `/booking/new` non chiede più l'accesso. Al passo
  Conferma chi non è entrato vede «I tuoi dati»: nome, cognome, telefono →
  «Ricevi il codice su WhatsApp» → codice → «Invia richiesta». La richiesta
  nasce `pending` come tutte quelle online.
  - `POST /api/public/guest/code` e `POST /api/public/guest/appointments`
    (`app/api/public/guest.py`), pubbliche in `EXPECTED_GUARDS`: il
    controllo è il codice.
  - Codici in `guest_phone_codes` (migration `d7b2e5a91c30`), uno per
    numero, hash come le password, 15 minuti, 5 tentativi. In più un tetto
    che la registrazione non ha: **un codice al minuto e 5 al giorno per
    numero**, oltre a 5/ora per IP — ogni codice è un WhatsApp a pagamento
    sul telefono di chi il numero lo possiede.
  - **Un codice vale una prenotazione**, e si spende solo se l'orario regge:
    l'orario si controlla prima del codice, così uno appena preso da
    un'altra non brucia il codice.
  - La scheda: si riusa quella attiva con lo stesso numero **e** lo stesso
    nome (ignorando maiuscole, accenti, spazi — `app/utils/nomi.py`),
    preferendo quella con un account; altrimenti se ne crea una. Madre e
    figlia col fisso di casa restano due schede.
- [x] **Admin** — nel modale «Nuovo appuntamento», «Nuova cliente» in fondo
  al menu clienti: nome, cognome, telefono facoltativo, precompilati da
  quello che si era scritto nella ricerca. Se il numero c'è già avvisa
  («Con questo numero c'è già: … — Usa questa») senza bloccare. Insieme,
  la ricerca clienti del modale ora trova il telefono scritto con spazi o
  senza +39 (prima confrontava la stringa: «333 555 5555» non trovava
  `+393335555555`, e nasceva il doppione).
- [x] **Collegamento alla registrazione** — `_collega_per_telefono` in
  `auth.py`, **solo dopo il codice WhatsApp** della registrazione: prima il
  numero è digitato, non dimostrato. Stesso numero + stesso nome, solo
  schede attive e senza account; l'unione è quella di «Unisci»
  (`client_merge`): sopravvive la scheda più vecchia, con storico e note,
  e l'account ci si sposta sopra.
- Test: `test_prenotazione_senza_account.py` (19),
  `test_collegamento_per_telefono.py` (9); 798 in tutto. **Falsificati**:
  16 rotture (niente cooldown, niente tetto, codice riusabile, codice
  controllato prima dell'orario, niente filtro sul nome, schede con
  account o disattivate collegabili, …) → ciascuna fa diventare rosso il
  suo test. Una passava lo stesso (preferenza per la scheda con account:
  nel test era anche la più vecchia) → test corretto, ora rosso.
- Verificato nel browser in locale: prenotazione da ospite con codice
  sbagliato («Tentativi rimasti: 4») e poi giusto → schermata finale con
  numero del salone e «Crea un account»; nel DB scheda senza email né
  account, richiesta `pending` `online`. Modale admin: avviso doppione,
  cliente creata e selezionata, appuntamento salvato.
- [PR #137](https://github.com/lorenzomelchionna/gestionale_nsh/pull/137)
  → `develop`, [PR #138](https://github.com/lorenzomelchionna/gestionale_nsh/pull/138)
  → `main` (commit `8ed4dc1`), CI verde (8/8 su #138). **Deploy
  confermato** il 2026-09-25 alle 07:36 UTC: backend, frontend e worker
  `SUCCESS`; nei log `Running upgrade a1f3c8d27e64 -> d7b2e5a91c30, add
  guest_phone_codes`, poi bootstrap completato. Dal vivo, senza mandare
  codici né scrivere nulla: `/health` 200, `www` e `/booking/new` 200;
  `POST /guest/code` con numero non valido → 422; `POST
  /guest/appointments` alle 03:00 → 409 «Questo orario non è più
  disponibile» (l'orario si controlla prima del codice, come previsto); le
  stringhe nuove («Ricevi il codice su WhatsApp», «Nuova cliente», «Con
  questo numero», «Puoi prenotare anche senza account») nel bundle servito.
  ~~Non ancora provato dal vivo: l'invio reale del codice WhatsApp e una
  prenotazione completa da ospite in produzione.~~ **Provato il 2026-09-25**
  sul numero di Lorenzo: codice partito dal fisso alle 07:46 UTC,
  `delivered` secondo Twilio; prenotazione «Prova Ospite», Taglio uomo con
  Flavia, 1 ottobre 18:30 → 201, id 44, `pending`; lo stesso codice
  riusato → 400 «Nessun codice per questo numero»; `notify_new_booking(44)`
  eseguito dal worker senza errori (email di avviso a admin e Flavia).
  - [x] ~~**Pulizia**~~ — fatta da Lorenzo il 2026-09-25: richiesta 44
    rifiutata, scheda «Prova Ospite» eliminata. Verificato dal portale:
    Flavia il 1 ottobre ha di nuovo 22 orari, 18:30 compreso.

- [ ] **Chi prenota senza account non sa se è stata rifiutata** — il
  rifiuto (`POST /appointments/{id}/reject`) non manda niente a nessuno;
  chi ha un account lo vede nella sua area, chi non ce l'ha no. Per ora il
  salone la contatta (Chat o telefono). Il lavoro: un template WhatsApp
  per il rifiuto, da far approvare a Meta.

### Segnalazione — 2026-09-24: «dice che il numero non ha WhatsApp»

Alcune persone che provano a scrivere al salone su WhatsApp si sentono dire
che il numero non ha un account. **Il numero funziona**, controllato il
2026-09-24 da Twilio: sender `whatsapp:+3908251728148` `ONLINE`, qualità
`HIGH`, 11 messaggi in arrivo in tre giorni. E non solo risposte: **4 di
quei mittenti hanno aperto la chat da soli**, senza aver mai ricevuto
niente dal salone (3 il 24, 1 il 23; controllato incrociando ogni primo
messaggio in arrivo con tutti i messaggi in uscita dell'account). Quindi
il salone si trova anche partendo da zero: chi non ci riesce ha il numero
**salvato o digitato male**, e WhatsApp gli propone «Invita».

Cause, dalla più probabile (ricerca con fonti, 2026-09-24):
1. **Salvato senza lo 0**, `+39 825 1728148`: numero che non esiste. È la
   trappola delle istruzioni di WhatsApp stesse — la FAQ «formato
   internazionale», anche in italiano, dice di **togliere gli 0 iniziali**
   ed elenca eccezioni solo per Argentina e Messico
   ([FAQ](https://faq.whatsapp.com/1294841057948784/?locale=it_IT)). Per i
   fissi italiani è sbagliato: lo 0 resta anche col +39. Coi cellulari
   (iniziano con 3) non c'è nessuno 0 da togliere, ed è per questo che il
   problema tocca solo alcune persone.
2. **Salvato come `0825 1728148`**, senza +39 — cioè esattamente come lo
   mostra il sito. La FAQ dice che un numero nazionale salvato «come lo
   chiameresti» funziona; un blog italiano sostiene di no. **Non
   documentato**: lo decide solo una prova su un telefono (voce qui sotto).
3. **Il telefono non ha ancora «visto» il contatto**: su iPhone con accesso
   ai contatti limitato un contatto nuovo resta invisibile a WhatsApp
   finché non lo si autorizza; su Android la rubrica si risincronizza
   circa una volta al giorno (Nuova chat → ⋮ → Aggiorna la forza).
4. **Il vecchio numero sbagliato** `095 441 220` (Catania), mostrato dal
   portale fino al commit `b426a35` del 2026-09-02.

**Escluso**: il nome «Vincenzo Romolo», il profilo vuoto, il fatto che sia
un fisso, le chiamate WhatsApp disattivate. Nessuna fonte Meta o Twilio li
collega a «non è su WhatsApp», e un problema lato piattaforma toccherebbe
tutti, non alcune persone.

- [ ] **Prova su un telefono** (2 minuti), su un numero che non ha mai
  scritto al salone. Salvare tre contatti — `0825 1728148`,
  `+39 0825 1728148`, `+39 825 1728148` — poi WhatsApp → Nuova chat → ⋮ →
  Aggiorna, e annotare quali risultano su WhatsApp. Atteso: il secondo sì,
  il terzo no. Il primo decide se sul sito serve mostrare il +39.
  Meglio ancora: uno screenshot del contatto salvato da una delle clienti
  che non ci sono riuscite.
- [ ] **Dire alle clienti come salvarlo** — testo pronto: «Per scriverci
  su WhatsApp salva il numero così: **+39 0825 1728148**. Lo 0 dopo il +39
  va lasciato.» In alternativa: rispondere al messaggio di conferma
  ricevuto dal salone, che la chat giusta la apre già.
- [ ] **Pulsante «Scrivici su WhatsApp» sul sito** →
  `https://wa.me/3908251728148`: apre la chat senza salvare niente, cioè
  salta tutte e quattro le cause. Da ricavare da `TELEFONO.tel` in
  `frontend/src/config/business.ts` **togliendo solo il `+`** — mai
  togliere zeri: la FAQ italiana del click-to-chat dice «non includere
  alcuno zero», e seguita alla lettera darebbe `wa.me/398251728148`, rotto.
  Test unitario che `+3908251728148` dia `3908251728148`. Insieme, mostrare
  il numero come `+39 0825 1728148` invece di `0825 1728148`; il link
  `tel:` è già giusto. **Provare il link su un telefono vero prima del
  rilascio**: da qui non si verifica, perché `wa.me` risponde 302 verso
  `api.whatsapp.com` anche per numeri inesistenti (provato).
- [ ] **QR in salone con lo stesso link**, sul bancone. Si lega alla voce
  «Una pagina per chi arriva dal QR code» qui sotto: possono essere due QR
  (prenota / scrivici) o una pagina che li offre entrambi. Alternativa
  ufficiale: QR e short link di Meta (`wa.me/message/CODICE`, con testo
  precompilato) — da vedere se l'account gestito da Twilio dà accesso a
  WhatsApp Manager o se va chiesto a Twilio.
- [ ] **Profilo WhatsApp del fisso vuoto** — letto dal Sender il
  2026-09-24: nome «Vincenzo Romolo», nessuna descrizione, indirizzo, sito,
  categoria, logo. Il vecchio numero ponte li aveva. Da compilare come
  quello (descrizione, «Corso Italia, 32 — 83030 Melito Irpino (AV)»,
  «Beauty, Spa and Salon», `https://www.newstylehair.it`), così chi apre
  la chat vede che è il salone. **È pubblico: solo con l'ok di Lorenzo.**
  Il nome resta al ticket del display name.
- [ ] **Il vecchio `095 441 220` altrove** — il commit `b426a35` l'ha
  corretto solo nel portale. Controllare scheda Google, Facebook,
  Instagram, volantini e biglietti.

### Richieste di Flavia — 2026-09-23 (primo giorno col database vuoto)

Cinque punti, ognuno controllato sul codice prima di decidere se era una
risposta o un lavoro. Tre avevano una risposta immediata; ma due di quelle
tre, guardate da vicino, nascondevano un difetto vero, che è registrato qui
sotto come voce aperta.

- [x] ~~**Ordine dei collaboratori nel calendario**~~ — «Vincenzo al
  centro». **Fatto il 2026-09-23.** Non si poteva, e non per
  un'impostazione mancante: `list_collaborators` **non aveva nessun
  `ORDER BY`**, quindi le colonne uscivano nell'ordine fisico delle righe
  in Postgres. Non solo sbagliato, **instabile**: provato con un test,
  cambiare il telefono ad Anna in un elenco Anna, Bea, Carla dava Bea,
  Carla, Anna — la riga aggiornata diventa una tupla nuova e torna in fondo.

  Cosa c'è ora:
  - colonna `position` (migration `c4e7a2d91b05`, backfill in ordine di id,
    cioè l'ordine di prima: il rilascio da solo non sposta niente);
  - `ORDER BY position, id` sull'elenco admin **e** su quello del portale,
    così la cliente che sceglie con chi prenotare vede lo stesso ordine
    del calendario;
  - `PUT /api/admin/collaborators/order` con l'elenco completo degli id:
    una scrittura sola, niente buchi né doppioni, e un elenco che non
    combacia — pagina rimasta indietro, collaboratore appena aggiunto in
    un'altra scheda — viene **rifiutato per intero** invece che applicato
    a metà. Dichiarato prima delle rotte `/{collaborator_id}`: dopo,
    FastAPI legge «order» come un id e risponde 422 (verificato);
  - un collaboratore nuovo va **in fondo**;
  - nella pagina Collaboratori una striscia **«Ordine nel calendario»**
    con i nomi in fila e le frecce ‹ ›. Prima versione con le frecce su
    ogni card, scartata dopo averla vista: a 1024 px — un tablet in
    orizzontale — il nome restava largo **31 pixel**.

  Vincenzo al centro **si imposta dopo il rilascio**, con un clic, e non
  nella migration: sarebbero dati di un salone nella storia dello schema,
  e la migration gira anche su database vuoti.

  [PR #123](https://github.com/lorenzomelchionna/gestionale_nsh/pull/123)
  → `develop`, [PR #124](https://github.com/lorenzomelchionna/gestionale_nsh/pull/124)
  → `main` (commit `143bc51`), CI verde su entrambe (8/8 su #124). 750
  test. **Deploy confermato** il 2026-09-23 alle 10:20 UTC: backend,
  frontend e worker `SUCCESS` e `online`. Nei log del backend la
  migration `Running upgrade f8a2e916c4d3 -> c4e7a2d91b05, add position to
  collaborators`, poi bootstrap completato; worker `celery@... ready`,
  nessun errore vero. `/health` → 200, `www.newstylehair.it` → 200.
  Ordine letto dal portale subito dopo: Flavia, Raffaella, Vincenzo —
  quello di prima, come voleva il backfill.
  - [x] ~~**Mettere Vincenzo al centro**~~ — fatto il 2026-09-23 dal
    gestionale. Letto dal portale: Flavia | Vincenzo | Raffaella.

- [ ] **Vedere se un messaggio è arrivato** — domanda di Flavia: «dove vedo
  se al cliente è arrivato il messaggio?». **Nel gestionale oggi da
  nessuna parte.** Per le notifiche automatiche (conferme, promemoria) il
  gestionale non registra niente: la tabella `communications` esiste ma
  non la scrive nessuno, e sul Sender non c'è `status_callback`, quindi
  Twilio non gli racconta mai l'esito. Per le risposte dalla pagina Chat
  lo stato arriva fino a `sent`, che vuol dire «Twilio l'ha preso», non
  «è arrivato sul telefono».

  **Risposta data intanto**: l'esito vero sta nella console Twilio, Monitor
  → Logs → Messaging, con `delivered` / `read` / `failed` per messaggio.

  **Il lavoro**: un endpoint per i callback di stato di Twilio, impostato
  sul Sender, che aggiorni lo stato del messaggio — e da mostrare dove il
  salone lo cerca, cioè sulla scheda cliente e sull'appuntamento. È lo
  stesso punto cieco che questo file ha già registrato il 17 settembre in
  cima: «la richiesta va a buon fine, la consegna fallisce, e il registro
  di Twilio non lo guardava nessuno».

- [ ] **La PAUSA non si vede nel calendario** — Flavia chiede un «servizio
  PAUSA solo per i collaboratori». È **la stessa richiesta del 4 agosto**,
  risolta allora coi **permessi a ore** (`tests/test_partial_absences.py`):
  un servizio avrebbe voluto un cliente finto per ogni pausa, perché
  `appointments.client_id` è obbligatorio.

  ~~«Risposta data intanto: Collaboratori → il collaboratore → «Aggiungi
  assenza» → …»~~ — **istruzione incompleta, e Flavia non ha trovato il
  pulsante.** Scritta leggendo l'etichetta nel codice, senza aprire la
  pagina: «Aggiungi assenza» sta dentro una tab della card, che si
  chiamava **«Ferie»** — cioè il posto in cui nessuno cerca una pausa,
  anche se lì dentro ci sono pure permessi a ore e malattia. Tab
  rinominata **«Assenze»** il 2026-09-23. Con l'etichetta più lunga la
  riga di tab sforava la card a 1024 px (264 px in 237; già prima di 11,
  e «Straord.» risultava tagliata): recuperato lo spazio dalla spaziatura,
  non dai nomi.

  **Percorso verificato nel browser**, clic per clic: Collaboratori → card
  del collaboratore → tab **«Assenze»** → «Aggiungi assenza» → spunta
  «Solo alcune ore» → Dal / Al (stesso giorno) → Dalle / Alle → Tipo
  **«Permesso»** (è preselezionato «Ferie») → nota facoltativa, es.
  «Pausa pranzo» → Salva. Provato con 13:00–14:00: le prenotazioni online
  di quel collaboratore saltano da 12:00 a 14:00 — sparisce anche 12:30,
  perché un servizio di un'ora finirebbe dentro la pausa.

  [PR #125](https://github.com/lorenzomelchionna/gestionale_nsh/pull/125)
  → `develop`, [PR #126](https://github.com/lorenzomelchionna/gestionale_nsh/pull/126)
  → `main` (commit `0858991`), CI verde su entrambe (8/8 su #126).
  **Deploy confermato** il 2026-09-23 alle 10:47 UTC: backend, frontend e
  worker `SUCCESS` e `online`, `/health` → 200, `www.newstylehair.it` →
  200, e la stringa «Assenze» presente nel bundle JavaScript servito in
  produzione — cioè la tab rinominata è quella che vede chi apre la
  pagina, non solo quella nel repository.

  Ma se la richiede di nuovo, il permesso a ore non le basta, e il perché
  è nel codice: la griglia del calendario **le assenze non le carica né le
  disegna**. `getAbsences` in `CalendarPage.tsx` è chiamato solo dentro il
  modale di nuovo appuntamento. Una pausa blocca le prenotazioni online,
  ma nel calendario quell'ora sembra libera — chi guarda l'agenda non la
  vede. Il lavoro: disegnare assenze e permessi nella griglia, come blocco
  grigio nella colonna del collaboratore.

  ~~Trovato insieme, **un difetto**: nel modale di nuovo appuntamento
  `isClosedDay` considera chiusa l'intera giornata per qualunque assenza~~
  — **corretto il 2026-09-23**, dopo che Flavia l'ha incontrato: «se prendo
  delle ore di permesso, i clienti non riescono a prenotare con me l'intera
  giornata». Era peggio di come l'avevo scritto: il giorno «chiuso» nel
  calendarietto del modale è `disabled`, quindi un permesso di un'ora
  rendeva quel collaboratore **non prenotabile dal gestionale per tutto il
  giorno**. Il portale delle clienti invece era giusto — verificato in
  produzione e in locale, il calendario pubblico passa dal server, che il
  permesso a ore lo toglie solo dalle sue ore.

  Ora chiude il giorno solo un'assenza senza orari. E siccome, sbloccato il
  giorno, niente avrebbe più impedito di prenotare sopra la pausa (la
  griglia del calendario le assenze non le disegna), il modale **avvisa se
  l'appuntamento scelto si sovrappone a un permesso** — sovrapposizione
  vera, inizio e fine, non solo l'ora d'inizio: un taglio 12:30–13:30
  contro una pausa 13:00–14:00 viene fermato. Si può procedere comunque,
  come già per i giorni di chiusura.

  Verificato nel browser: col codice vecchio il giorno del permesso
  risulta barrato e non cliccabile (riprodotto il caso di Flavia); col
  nuovo è selezionabile, 12:30 mostra «L'orario cade in un'assenza del
  collaboratore (13:00–14:00)», 15:00 salva senza avvisi.

  [PR #129](https://github.com/lorenzomelchionna/gestionale_nsh/pull/129)
  → `develop`, [PR #130](https://github.com/lorenzomelchionna/gestionale_nsh/pull/130)
  → `main` (commit `2e419e0`), CI verde su entrambe (8/8 su #130).
  **Deploy confermato** il 2026-09-23: frontend e worker `SUCCESS` alle
  12:50 UTC, backend alle 12:51 (build più lento del solito, avvio pulito,
  nessuna migration da applicare). `/health` → 200, `www.newstylehair.it`
  → 200, e il testo del nuovo avviso («cade in un'assenza del
  collaboratore») presente nel bundle JavaScript servito in produzione.

  Da chiarire con Flavia: se «solo per i collaboratori» vuol dire anche
  che **i collaboratori stessi** devono potersela mettere. Oggi creare e
  cancellare assenze è solo admin (`EXPECTED_GUARDS`: `POST` e `DELETE`
  su `/api/admin/absences` → `admin`).

- [ ] **«Rivedere il tempo di risposta ai messaggi WhatsApp»** — richiesta
  ambigua, **da chiarire con Flavia prima di toccare codice**. La lettura
  più probabile, e quella che il codice rende plausibile: non è che i
  messaggi arrivino tardi, è che **ci si accorge tardi che sono
  arrivati**. Col fisso sull'app WhatsApp Business ogni messaggio era una
  notifica sul telefono; adesso finisce nella pagina Chat e basta:
  - il webhook in entrata salva il messaggio e **non avvisa nessuno**;
  - il badge nel menu si aggiorna ogni 30 secondi, la conversazione aperta
    ogni 15;
  - e nessuna query ha `refetchIntervalInBackground`, quindi con il
    gestionale in una scheda dietro — o lo schermo del telefono spento —
    **non si aggiorna proprio** finché non ci si torna sopra.

  Le strade vanno da un suono e un titolo di scheda lampeggiante (poco) a
  una notifica push o un'email allo staff per ogni messaggio in entrata
  (di più). Quale serve dipende da dove sta il gestionale durante la
  giornata in salone — domanda da fare, non da indovinare.

- [ ] **Una pagina per chi arriva dal QR code** — Flavia vuole mettere un
  QR in salone perché le clienti scoprano il nuovo sistema, e chiede una
  «schermata diversa». **Risposta data intanto**: `www.newstylehair.it`
  apre già la home del portale clienti (`BookingHomePage`), non il login
  dello staff — un QR verso quell'indirizzo funziona da oggi. Il lavoro,
  se lo vuole: una pagina di benvenuto che spieghi cosa si può fare
  (prenotare, vedere gli appuntamenti, la lista d'attesa) prima di
  chiedere la registrazione. Contenuto da decidere con lei. Il QR va
  comunque fatto puntare al dominio e non a un percorso interno: così
  resta valido qualunque pagina ci si metta dietro.

  Nella stessa domanda: **«come vedo le credenziali di tutti i
  collaboratori»**. Non si vedono, e di proposito: le password sono
  salvate come hash, nessuno può rileggerle — nemmeno l'admin, nemmeno
  dal database. **Risposta data**: Team e accessi → «Password» accanto al
  collaboratore → se ne imposta una nuova.

### Richieste di Flavia — 2026-08-04 (WhatsApp, dopo un giro sezione per sezione)

Ognuna verificata sul codice, non ipotizzata: dove il campo già esiste manca
solo il collegamento in UI, dove non esiste serve una migration.

- [x] ~~**Tempo di posa nei servizi**~~ — fatto 2026-08-04. `duration_slots`
  resta la durata totale (quella che vede la cliente); due campi nuovi dicono
  come si spezza: `slots_before_processing` (applicazione) e
  `processing_slots` (posa, collaboratore libero). Il resto è lavoro finale.
  `availability.py` ora calcola quali slot **impegnano davvero** il
  collaboratore, quindi durante la posa di una tinta l'agenda può infilare
  un'altra cliente. Verificato in produzione locale: Colore base 120 min con
  60 di posa → prenotato alle 09:00, le 09:30 e le 10:00 restano libere,
  09:00 e 10:30 occupate.
  Retrocompatibile: `processing_slots = 0` è il comportamento di sempre, e i
  19 servizi esistenti non cambiano di una virgola.
  **Prudenza deliberata**: se un appuntamento viene allungato a mano
  dall'agenda, la somma dei suoi servizi non lo descrive più e si torna a
  occupare tutta la fascia — meglio un buco sprecato che due clienti sulla
  stessa poltrona.

- [x] ~~**Servizio "Pausa" interno per le ore di permesso**~~ — fatto
  2026-08-04, ma **non** come servizio nascosto. Un appuntamento richiede
  sempre un `client_id`, quindi ogni pausa avrebbe voluto un cliente finto in
  anagrafica, sporcando elenco clienti e statistiche.
  `Absence` esiste già per questo e blocca il calendario nel modo giusto:
  mancava solo di poterla limitare a una fascia oraria. Aggiunti
  `start_time`/`end_time` opzionali — entrambi assenti = giornata intera,
  cioè il comportamento di prima. Nel form collaboratori c'è una casella
  «Solo alcune ore». Su un intervallo di più giorni la fascia vale per
  ognuno («tutte le mattine di questa settimana»).
  Sistemato per strada un bug latente: la query sulle assenze usava
  `scalar_one_or_none()`, che con due assenze nello stesso giorno **solleva**
  invece di rispondere. Coi permessi a ore quel caso diventa normale.

- [x] ~~**Descrizione prodotto nel form**~~ — fatto 2026-08-04, insieme al
  form di modifica come previsto. `description` esisteva già ovunque tranne
  che in un input, quindi restava sempre vuoto; `PUT /products/{id}` esisteva
  nel backend e non lo chiamava nessuno, quindi un prodotto una volta creato
  non si poteva più correggere. Ora lo stesso foglio serve a creare e a
  modificare, e dalla lista c'è una matita per riga.
  Due campi il PUT **non** li scrive, ed è deliberato:
  - `quantity` — ogni pezzo che entra o esce lascia una riga in
    `product_movements`. Scriverla dritta farebbe sparire dei pezzi senza che
    niente dica dove sono finiti. In modifica il campo non compare proprio, e
    al suo posto c'è la riga che rimanda a carico/scarico.
  - `photo_url` — è il permalink del token dell'immagine, non un dato da
    scrivere a mano: se fosse modificabile si potrebbe far puntare la foto di
    un prodotto a un host qualsiasi. Ha già i suoi endpoint.

  Tolti dallo schema di update, quindi rifiutati dal backend e non solo
  nascosti nel form. Verificato al contrario: rimettendoli, tre test falliscono.

- [x] ~~**I prodotti non sono visibili ai clienti**~~ — non un task, una
  domanda: verificato, non esiste nessun endpoint pubblico per i prodotti
  (`/api/public/` ha solo `services` e `collaborators`). Il magazzino è solo
  staff. Non serve fare nulla per questo punto, era solo un dubbio.

- [x] ~~**Fornitore sui prodotti**~~ — fatto 2026-08-04, stesso form.
  `supplier` è testo libero e non una tabella fornitori: il salone ordina da
  pochi marchi e quello che serve è sapere a chi telefonare quando un
  prodotto finisce. Colonna nullable senza default — sui prodotti già a
  magazzino NULL vuol dire «non lo sappiamo», non «nessuno».
  Nella lista sta sotto la categoria: il fornitore si legge quando un
  prodotto è finito e va riordinato, cioè una riga alla volta, non
  scorrendo una colonna.

#### Rimasto fuori da questo giro (prodotti) — chiuso il 2026-08-05
- [x] ~~**Archiviare un prodotto fuori catalogo**~~ — il parametro
  `active_only` esiste ora davvero lato backend (`api.ts` lo dichiarava già:
  era codice morto), e in pagina c'è «In catalogo / Archiviati». Archiviare
  non è più una perdita: dall'archivio si rimette dentro. Un prodotto
  archiviato **non** compare fra i sotto scorta — non è una scorta da
  riordinare, è roba che non si vende più.
  Archiviare e non cancellare: movimenti di magazzino e vendite passate
  puntano a quel prodotto, e toglierlo lascerebbe lo storico a parlare di un
  articolo che non esiste.
- [x] ~~**Prezzi negativi**~~ — `ge=0` su `ProductCreate`/`ProductUpdate`,
  **non** su `ProductBase`, che è anche lo schema di lettura: un vincolo lì
  avrebbe fatto fallire l'elenco del magazzino se una riga storta esistesse
  già, cioè proprio la pagina da cui ci si accorge del problema. C'è un test
  che lo tiene fermo scrivendo un prezzo negativo direttamente in SQL.
- [x] ~~**Deriva modello/migration**~~ — migration `b6e21c8f0a53`:
  `product_images.created_at` ora è NOT NULL come dice il modello.
  `alembic check` risponde «No new upgrade operations detected».
  Con un `UPDATE` di sicurezza prima del `SET NOT NULL`: in teoria non serve
  (il default l'ha sempre riempita), in pratica una sola riga nulla
  manderebbe giù il servizio all'avvio, visto che le migration girano nello
  startCommand.

- [x] ~~Le note cliente si salvano?~~ — sì, verificato: `Client.notes` è già
  salvato, modificabile e mostrato in scheda cliente. **Ma** per l'uso che ne
  vuole fare — segnare il colore ad ogni visita — un campo unico non
  distingue una visita dall'altra: la nota di oggi sovrascrive quella di tre
  mesi fa. Esiste già `Appointment.visit_notes`, pensato esattamente per una
  nota per singola visita — ma è nel modello e basta: **zero** UI lo scrive o
  lo mostra, in nessuna pagina. È il campo giusto per quello che chiede, va
  solo collegato (probabilmente nel flusso "completa appuntamento").

- [x] ~~**`visit_notes` collegato alla UI**~~ — fatto 2026-08-04, nel flusso
  «completa appuntamento» come previsto: chiudere la visita è il momento in
  cui si sa cosa scrivere. Il corpo della chiamata è facoltativo, quindi
  «Completa» senza nota resta un clic solo. La nota si rilegge nello storico
  della scheda cliente — che era il punto della richiesta — e si corregge
  dopo dalla scheda nel nuovo elenco appuntamenti.

  **Prima però andava chiusa una falla**, e non è un extra: il portale
  cliente rispondeva con `AppointmentOutWithNames`, che contiene
  `visit_notes` e `notes`. Finché il campo restava vuoto non usciva niente;
  dal momento in cui il salone ci scrive «capello in difficoltà, sconsigliata
  la decolorazione», sarebbe stata la cliente a leggerselo. Le due rotte
  pubbliche ora usano `PortalAppointmentOut`, scritto come **elenco di campi
  permessi** e non per sottrazione: un campo nuovo sul modello non finisce
  nel portale per distrazione. `rejection_reason` resta — è scritto per
  essere letto da chi l'ha subito. Verificato al contrario: rimettendo i due
  campi, tre test falliscono.

- [x] ~~**Elenco di tutti gli appuntamenti**~~ — fatto 2026-08-04, in
  `/admin/appointments/all`. Ricerca per nome, cognome o telefono, filtri per
  stato, periodo e collaboratore, e la nota di visita in riga: «che colore le
  ho fatto a marzo?» si risponde da qui.
  `GET /appointments` aveva già data, collaboratore e stato; mancavano
  ricerca, filtro cliente e ordine invertito. L'ordine è un parametro perché
  le due schermate lo vogliono opposto — il calendario legge una giornata in
  avanti, l'elenco parte da ieri e va indietro — e il default resta `asc`,
  che è quello che il calendario si aspettava già.
  Nella barra del telefono non entra: sta nel gruppo «Registro» accanto a
  Clienti, così le quattro voci in fondo allo schermo restano quelle di prima.

- [x] ~~**Gift card, arriva via email a chi la riceve**~~ — fatto 2026-08-05.
  Vendita al banco, codice generato, email al **destinatario** (non a chi
  paga), riscatto anche parziale col residuo che resta spendibile.

  Tre decisioni prese con Lorenzo, perché cambiavano cosa costruire:

  1. **Si vende solo al banco.** Nel progetto non esiste nessun gateway di
     pagamento — la vendita online avrebbe voluto dire integrare Stripe, un
     lavoro più grande della gift card stessa.
  2. **L'incasso è alla vendita.** Oggi entrano 50€ e si registrano oggi,
     perché oggi sono nel cassetto. Al riscatto **non** nasce nessun
     pagamento: registrarlo di nuovo conterebbe gli stessi euro due volte.
     `test_il_riscatto_non_incassa_di_nuovo` tiene fermo proprio questo.
  3. **Scadenza a 12 mesi**, calcolata dal server e non digitata: due
     operatori non devono poter produrre due scadenze diverse.

  Scelte tecniche che vale la pena ricordare:
  - **Lo stato non è una colonna** (attiva/esaurita/scaduta/annullata): si
    ricava da saldo, scadenza e annullamento. Una colonna andrebbe tenuta
    allineata a ogni riscatto, e il giorno che si disallinea è il giorno in
    cui una card esaurita risulta ancora spendibile.
  - **Il riscatto blocca la riga** (`SELECT ... FOR UPDATE`). Senza, due
    postazioni che riscattano insieme leggono lo stesso saldo e lo scalano
    entrambe: un buono da 50€ ne pagherebbe 80. Verificato al contrario —
    tolto il lock, il test concorrente fallisce.
  - **Due tabelle**: la card porta il saldo, `gift_card_redemptions` porta la
    storia. Il saldo da solo direbbe «restano 20€» senza saper rispondere a
    «dove sono finiti gli altri 30?», che su soldi di qualcun altro è la
    domanda che arriva sempre.
  - **Il codice evita `0`/`O` e `1`/`I`/`L`**: viene ricopiato a mano da
    un'email e dettato al telefono. La ricerca perdona maiuscole, spazi e
    trattini per lo stesso motivo.
  - **Tipo di pagamento suo** (`gift card`), così dieci buoni venduti non
    sembrano un mese di servizi record.

#### Rimasto fuori (gift card) — chiuso il 2026-08-05
- [x] ~~**Riscatto agganciato all'appuntamento**~~ — nel riquadro «usa il
  buono» si cerca la cliente per nome e si sceglie la visita. Resta
  facoltativo, ed è detto in chiaro: al banco capita di scalare un buono
  senza un appuntamento a cui agganciarlo (un prodotto, o chi passa senza
  prenotare). Nello storico dei riscatti compare «05/08/2026 · Laura Ricci»,
  etichetta composta dal server per non risolvere un id per ogni riga.
  Aggiunto anche il controllo che l'appuntamento esista: senza, un id
  sbagliato sarebbe arrivato alla foreign key e avrebbe dato 500 **dopo**
  aver già ridotto il saldo in transazione.
- [x] ~~**Latenza col broker giù**~~ — `task_publish_retry=False` più
  `socket_connect_timeout`/`socket_timeout` a 2 secondi in
  `tasks/celery_app.py`. Coi default Celery ritenta con backoff prima di
  sollevare, quindi l'eccezione arrivava — solo troppo tardi per essere
  utile, con qualcuno che aspettava alla cassa.
  Vale per **tutti** i trigger fire-and-forget, non solo le gift card, ed è
  per questo che sta nella configurazione e non nei singoli endpoint.
  `broker_connection_retry_on_startup=True` resta: riguarda il worker che si
  collega all'avvio, che invece Redis deve aspettarlo — altrimenti un riavvio
  simultaneo dei due servizi lo fa morire prima che il broker sia pronto.
  Toglie anche la deprecation che Celery stampava a ogni boot.

### Immagini dei prodotti — richiesta 2026-08-02, fatta 2026-08-03

- [x] ~~Caricare una foto per ogni prodotto e mostrarla in magazzino~~, anche
  sui prodotti già registrati.

**Dove finiscono i file**: in Postgres, in `product_images`, non su disco. Il
filesystem dei container Railway è effimero — sparisce a ogni push su `main` —
quindi il disco era escluso senza montare un volume, e un volume è infrastruttura
in più, non compresa nei backup del database. I byte stanno in una tabella
separata e non in una colonna di `products`, altrimenti ogni listino di
magazzino se li trascinerebbe dietro.

**Perché l'URL contiene un token e non l'id**: un tag `<img>` non può mandare
l'header Authorization, quindi l'endpoint che serve i byte deve essere pubblico.
Pubblico con un id sequenziale vorrebbe dire lasciare sfogliare tutto il
magazzino contando da 1; con 32 byte casuali no. Sostituire la foto rigenera il
token, il che serve anche da cache busting.

**Cosa viene rifiutato**: qualunque file che Pillow non decodifica, i formati
fuori da JPEG/PNG/WebP, oltre 10 MB, e i file vuoti. Il `Content-Type`
dichiarato non conta: l'immagine viene ri-codificata dal server, quindi quello
che finisce archiviato è sempre un file prodotto da noi. La ri-codifica butta
anche l'EXIF, che su una foto da telefono contiene le coordinate GPS di dove è
stata scattata.

**Ridimensionamento**: lato server, lato lungo massimo 900px. Una foto da
telefono passa da qualche megabyte a qualche decina di kilobyte, quindi lo
spazio nel database resta trascurabile anche con tutto il magazzino coperto.

Sistemato di conseguenza anche l'ordinamento del listino: non c'era un
`order_by`, quindi ogni modifica faceva saltare il prodotto in fondo alla
pagina. Con le sole modifiche di prezzo capitava di rado, con le foto sarebbe
successo ogni volta.

---

# (storico) — note di setup precedenti

> ⚠️ **Istantanea superata.** Quanto segue fotografa una situazione
> passata. Le caselle non spuntate qui sotto **non sono lavoro da fare**:
> lo stato vero è in cima al documento. Non modificare, serve da cronologia.

Stato attuale: codice pronto e funzionante. Entrambi i canali in **stub mode**
(nessun invio reale) finché le credenziali non sono configurate.

## Email (SMTP)

Manca solo: credenziali SMTP.

- [ ] `SMTP_USER` — indirizzo email mittente
- [ ] `SMTP_PASSWORD` — **App Password** Gmail (NON password account; richiede 2FA attivo)
- [ ] Settare in `.env` locale **e** variabili Railway (produzione)

Note:
- Default host: `smtp.gmail.com:587`
- `SMTP_USER` vuoto → modalità stub (`[EMAIL STUB]` su stdout)

## WhatsApp (Twilio)

1. [ ] Creare account **Twilio** + WhatsApp sender
   - Sandbox (test): `whatsapp:+14155238886`, clienti devono fare opt-in (join code)
   - Produzione: numero WhatsApp Business approvato
2. [ ] Riempire 3 env (locale + Railway):
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_WHATSAPP_FROM` (es. `whatsapp:+14155238886`)
3. [ ] Attivare `whatsapp_enabled = true` da pagina **Impostazioni**
   (altrimenti canale WA saltato anche con Twilio configurato)
4. [ ] **Template approvati** Meta/Twilio (per produzione reale):
   - Conferme / reminder / compleanno = messaggi business-initiated
   - WhatsApp Business richiede template pre-approvati fuori finestra 24h
5. [ ] Telefoni clienti in formato **E.164** (`+39...`)

Note:
- Twilio non configurato → modalità stub (`[WA STUB]` su stdout)

## Riferimenti codice

- Orchestratore: `backend/app/utils/notifications.py`
- Email: `backend/app/utils/email.py`
- WhatsApp: `backend/app/utils/whatsapp.py`
- Scheduler: `backend/app/tasks/reminders.py` + `celery_app.py`
- Config env: `backend/app/config.py`

## Eventi notifica (automatici)

| Evento | Trigger | Canali |
|--------|---------|--------|
| Conferma prenotazione | appuntamento confermato | email + WA |
| Reminder | X ore prima (`whatsapp_reminder_hours`, default 24h) | email + WA |
| Compleanno | ogni mattina 09:00 (Europe/Rome) | email + WA |
| Reset password | richiesta reset cliente | email + WA |
| Messaggio custom | pagina Messaggi admin | canale scelto |

## TODO minori (storici — le voci vive stanno nella Roadmap in cima)

- [x] ~~`service_names` non veniva mai popolato~~ — risolto. La proiezione sta
      in `AppointmentOutWithNames.from_appointment` e i caricamenti eager in
      `appointment_detail_loads()`: prima la regola era copiata in quattro
      router e in tre di essi mancava questo campo. Coperto da
      `tests/test_appointment_service_names.py`.
- [x] ~~Togliere la pastiglia "online" dalle schede collaboratore~~ — fatto.
      Il campo `visible_online` resta e si cambia dal form di modifica: decide
      se il collaboratore è selezionabile nel portale pubblico.
- [x] ~~Togliere la pastiglia "online" anche dai clienti~~ — fatto. Il campo
      `account_id` resta: è quello che collega il cliente al suo account del
      portale. Via solo l'etichetta, che diceva una cosa diversa da quella che
      sembrava.

---

# Stato produzione Railway (verificato 2026-05-30)

> ⚠️ **Istantanea superata.** Quanto segue fotografa una situazione
> passata. Le caselle non spuntate qui sotto **non sono lavoro da fare**:
> lo stato vero è in cima al documento. Non modificare, serve da cronologia.

Progetto: **zucchini-blessing** (id `88babcdd-d33d-4130-bb22-0a8c3d5d5037`)
Env: **production** (id `b92d9278-66c0-42a4-91d3-714e731f2669`)

## Servizi attivi
| Servizio | Ruolo | Stato | Ultimo deploy (UTC) |
|----------|-------|-------|---------------------|
| gestionale_nsh | backend FastAPI | Online | 2026-05-29 20:09 |
| happy-benevolence | frontend | Online | 2026-05-29 20:09 |
| Postgres | DB | Online | 2026-05-08 |
| Redis | broker Celery | Online | 2026-05-08 |

URL:
- Frontend: https://happy-benevolence-production.up.railway.app
- Backend: https://gestionalensh-production.up.railway.app

## ✅ RISOLTO: servizio Celery creato (2026-06-14)

Servizio **celery-worker** (id `09ed135b-d050-44bb-8854-47de4bdc077a`) Online.
- Repo collegato `lorenzomelchionna/gestionale_nsh`, branch `main`, root `backend`
- Config-as-code: **`railway.worker.toml`** (NON railway.toml — altrimenti partiva uvicorn)
- `worker-start.sh` fixato: `celery ... worker --beat` (worker + scheduler in 1 processo)
- Log verificati: `beat: Starting`, `celery@... ready`, task confermati consumati
- Var settate: DATABASE_URL, REDIS_URL (internal), SECRET_KEY, FRONTEND_URL,
  SMTP_HOST/PORT, EMAILS_FROM_*, APP_ENV, token config, SEED_DEMO=false

Nota gotcha: **railway.toml `startCommand` vince sul Custom Start Command del dashboard.**
Per servizi diversi nello stesso repo → file config-as-code diversi.

## Credenziali ANCORA mancanti (sia backend che worker)

- [ ] `SMTP_USER` — ASSENTE → email in stub
- [ ] `SMTP_PASSWORD` — ASSENTE (App Password Gmail)
- [ ] `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` — ASSENTI
- [ ] `whatsapp_enabled=true` da pagina Impostazioni (per attivare canale WA)

Stato canali:
| Canale | Infra | Credenziali | Invio reale |
|--------|-------|-------------|-------------|
| Email | ✅ pronta | ❌ manca SMTP_USER/PASSWORD | ❌ stub |
| WhatsApp | ✅ pronta | ❌ manca Twilio + flag | ❌ stub |

## Da fare

1. [ ] Aggiungere `SMTP_USER` + `SMTP_PASSWORD` a **backend + worker** (entrambi inviano)
2. [ ] (WhatsApp) Twilio: 3 var su backend + worker + `whatsapp_enabled=true`
3. [ ] (Opz.) Disattivare `SEED_DEMO=true` su backend (worker già false)

## Note utili
- Railway CLI installato (auth: lmelchionna73@gmail.com)
- Progetto linkato: `railway link` → zucchini-blessing / production
- Set var via CLI: `railway variable set --service <svc> "KEY=val"`
- MCP Railway instabile (si disconnette) → usare CLI
