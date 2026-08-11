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
- [ ] **PR #65 di Dependabot: il gruppo «minori» contiene FastAPI** — la CI la
  blocca (pytest rosso sulla matrice permessi, esattamente come previsto), ma
  intanto sedici aggiornamenti buoni restano fermi dietro a uno che nessuno può
  mergiare. La causa: sotto la 1.0 la major è `0`, quindi per semver **ogni**
  rilascio di FastAPI è un minor e la riga `ignore` sui major non lo prendeva.
  `dependabot.yml` ora esclude `fastapi`, `starlette`, `sqlalchemy` e
  `pydantic*` dal gruppo, così prendono una PR ciascuno. La #65 va chiusa e
  riaperta da Dependabot con la configurazione nuova.
  Nota utile: sulla #65 `pip-audit` è **passato**. Cioè l'aggiornamento chiude
  davvero tutte le vulnerabilità rimaste, e il solo ostacolo è il test da
  riscrivere. Le due previsioni fatte a mano sono state confermate dalla CI in
  modo indipendente.
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
