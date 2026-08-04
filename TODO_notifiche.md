# TODO — Configurazione notifiche (Email + WhatsApp)

## ✅✅ STATO: EMAIL + WHATSAPP FUNZIONANTI IN PRODUZIONE (2026-06-19)

Pipeline completa testata e verificata end-to-end:
appuntamento confermato → Redis → Celery worker → invio → consegnato.

| Canale | Stato | Provider | Via |
|--------|-------|----------|-----|
| **Email** | ✅ Funziona | Brevo | HTTP API (HTTPS) |
| **WhatsApp** | ✅ Funziona | Twilio | HTTP API — **Sandbox** |

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
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886`,
`SMTP_*` (fallback). `whatsapp_enabled=true` in BookingConfig.

### Restano (NON bloccanti)
- [ ] **WhatsApp produzione**: ora è Sandbox (solo numeri che fanno `join`, scade 72h).
  Per clienti reali serve numero WhatsApp Business + template Meta approvati.
- [x] ~~`SEED_DEMO` da disattivare~~ — verificato 2026-08-01: `SEED_DEMO=false`
  sul backend, non impostata sul worker. Anche se tornasse `true` non
  succederebbe nulla: `seed_demo()` esce subito se esiste almeno un servizio,
  e in produzione ce ne sono 19 reali coi prezzi del salone.
- [ ] (Opz.) Dominio + branding `noreply@newstylehair.it` (ora From = Gmail).
- [x] ~~`notify_new_booking` è solo un `print()`~~ — fatto 2026-08-02. Erano tre
  bug in fila, non uno: l'endpoint non accodava niente, il task stampava e
  basta, e accodare prima del commit avrebbe fatto trovare al worker una
  prenotazione che ancora non esiste. Ora la richiesta parte via email a tutti
  gli admin attivi + al collaboratore prenotato (chiunque possa rispondere:
  confermare è un permesso `staff`, non solo admin). Niente WhatsApp allo
  staff: passerebbe dalla stessa Sandbox Twilio che parla solo con chi ha
  mandato `join`, quindi sarebbe un canale che perde i messaggi in silenzio.

---

## Roadmap go-live clienti reali

### WhatsApp produzione — DECISIONE numero (da prendere al go-live)
Il salone ha GIÀ un numero su WhatsApp Business usato col gestionale attuale.
Vincolo Meta/Twilio: un numero può stare su WhatsApp Business in UN solo posto.

- **Scenario A — migrare numero esistente su Twilio**: il numero passa all'API,
  si PERDE l'app WhatsApp Business manuale (niente più chat a mano da quel numero).
  Richiede port-in Meta.
- **Scenario B — numero nuovo dedicato (consigliato)**: SIM nuova solo per le
  notifiche automatiche; il numero attuale resta sull'app per le chat manuali.
  Nessuna migrazione rischiosa.

→ Quasi sempre i saloni vogliono tenere la chat manuale = **Scenario B**.
Decisione confermata: sostituzione numero SOLO al momento del go-live effettivo.

Passi WhatsApp produzione (qualunque scenario):
1. Numero (nuovo per B, o migrazione per A)
2. Account Meta Business verificato
3. Registrare numero come WhatsApp Sender su Twilio (verifica SMS/voce)
4. Template messaggi approvati da Meta (1-2 giorni) — testi in `whatsapp.py`
5. Aggiornare `TWILIO_WHATSAPP_FROM` (1 variabile, zero codice)

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
- [ ] **Verifica del numero di telefono** — da fare. Oggi il telefono viene
  normalizzato in E.164 ma **non verificato**: nulla impedisce di inserire il
  numero di qualcun altro, che si ritroverebbe i messaggi WhatsApp del salone.
  Serve lo stesso schema dell'email — codice via SMS o WhatsApp, con scadenza e
  tetto ai tentativi. Il modulo `app/services/email_verification.py` è già
  scritto in modo riutilizzabile: cambia solo il canale di invio.
  **Prerequisito**: WhatsApp fuori dalla Sandbox Twilio, altrimenti il codice
  arriva solo a chi ha già fatto il `join` (vedi sezione WhatsApp produzione).
  In alternativa SMS Twilio, che si paga a messaggio.
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
- [ ] **Rate limiting** con `slowapi` (storage su Redis, che c'è già) sui soli
  endpoint costosi: register 5/ora, login 10/min, verify-email 10/min,
  resend-code 3/ora. È l'unica mossa che *ferma* qualcuno, e chiude in un colpo
  DoS, anagrafiche spazzatura e quota Brevo bruciata.
- [ ] **bcrypt fuori dall'event loop** — `run_in_threadpool` in `utils/auth.py`,
  incluse `issue_code` e `check_code` in `services/email_verification.py`, che
  sono quelle che si dimenticano. Gli handler non possono diventare `def`
  sincroni: il corpo fa `await db.execute`.
- [ ] **Unione di due schede dall'area admin** — conseguenza del fix sopra: il
  salone può ritrovarsi due righe per la stessa persona (una sua, una creata
  dalla registrazione) e oggi le può solo modificare a mano una per volta.
  Serve un pulsante "unisci": sposta appuntamenti e pagamenti su una riga sola
  e cancella l'altra. Diventa meno urgente quando il numero sarà verificabile.
- [ ] **Due `scalar_one_or_none()` ancora esposti in `availability.py`** —
  stessa famiglia del bug chiuso il 2026-08-04 sulle assenze, trovati mentre
  lo si sistemava. Riga 81 (`CollaboratorExtraDay`) e riga 98
  (`CollaboratorSchedule`): nessuna delle due tabelle ha un vincolo unico, e
  `POST /api/admin/extra-days` non controlla nulla, quindi due giorni extra
  sulla stessa data si creano con due click — e da quel momento il calcolo
  della disponibilità **solleva** per quel collaboratore, in quel giorno,
  invece di rispondere. Il fix è lo stesso: `scalars().all()` più una regola
  su cosa fare con più righe (e possibilmente un vincolo unico in migration).
- [ ] **Ordine dei controlli in `services/images.py`**: `image.format in
  ALLOWED_FORMATS` e un tetto sui pixel vanno **fra** `Image.open()` e
  `image.load()`. Oggi l'allowlist arriva dopo che il decoder ha già girato. Il
  commento "Pillow refuses absurd pixel counts on its own" è sbagliato.
- [ ] **Open redirect** in `LoginPage.tsx:58`: `next` letto dalla query e
  passato a `navigate()` senza validazione, quindi `?next=//sito-cattivo` porta
  fuori dominio dopo il login. Due righe.
- [x] ~~**`visit_notes` fuori dal portale**~~ — fatto 2026-08-04, e proprio
  come diceva questa riga: **prima** di iniziare a usarla. Le due rotte
  pubbliche degli appuntamenti ora rispondono con `PortalAppointmentOut`,
  che elenca i campi permessi invece di toglierne due — così un campo nuovo
  sul modello non esce dal portale per distrazione. Fuori anche `notes`, che
  dal calendario la scrive il salone. Dentro resta `rejection_reason`: è la
  spiegazione di un rifiuto, scritta per chi l'ha subito.
- [ ] **Dependabot + `pip-audit` in CI** — è il motivo per cui il DoS di
  python-multipart è rimasto scoperto venti mesi.
- [ ] **Un minimo di logging**: in `backend/app/` non c'è una sola riga. Se
  domani entra qualcuno non puoi dire cosa ha visto, che è esattamente quello
  che chiede l'art. 33 GDPR.
- [ ] `Field(min_length=10)` su `ClientRegister.password` e
  `PasswordReset.new_password`: lo staff ha 12, i clienti niente lato server.

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

- [ ] **I prodotti non sono visibili ai clienti** — risposta diretta alla sua
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

#### Rimasto fuori da questo giro (prodotti)
- **Archiviare un prodotto fuori catalogo**: `is_active` esiste ed è
  modificabile via API, ma la lista filtra `is_active == True` e non esiste
  nessun filtro per rivederli — archiviarlo dalla UI vorrebbe dire perderlo
  senza modo di tornare indietro. Servono il parametro `active_only` lato
  backend (`api.ts` lo dichiara già, il backend non lo accetta: è codice
  morto) più un interruttore in pagina.
- **Prezzi negativi**: nessun vincolo lato server, solo `min="0"` nel form.
  Da mettere su `ProductCreate`/`ProductUpdate` e **non** su `ProductBase`,
  che è anche lo schema di lettura: un vincolo lì farebbe fallire l'elenco
  invece della scrittura, se una riga storta esistesse già.
- **Deriva modello/migration**: `alembic check` segnala
  `product_images.created_at` NOT NULL nel modello ma nullable a database
  (viene dalla migration delle foto, non da questa). Senza conseguenze —
  `server_default=now()` lo riempie sempre — ma la prossima autogenerate si
  porterà dietro l'operazione spuria. La CI fa `upgrade head`, non `check`,
  quindi non se ne accorge.

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

#### Rimasto fuori (gift card)
- **Riscatto agganciato all'appuntamento**: il campo `appointment_id` esiste
  sul riscatto ma nessuna schermata lo valorizza — oggi si scala l'importo e
  basta. Collegarlo direbbe *su quale visita* è stato speso il buono.
- **Latenza col broker giù**: `_trigger_gift_card_email` usa `.delay()` come
  tutte le altre notifiche, e con Redis irraggiungibile la richiesta resta
  appesa finché Celery non smette di ritentare (visto in locale). La vendita
  non si perde — l'eccezione viene raccolta e il buono resta emesso — ma alla
  cassa un'attesa così è comunque brutta. Riguarda **tutti** i trigger
  fire-and-forget, non solo questo: la correzione sta nella configurazione
  Celery (timeout di connessione basso, niente retry), non nel singolo
  endpoint.

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
