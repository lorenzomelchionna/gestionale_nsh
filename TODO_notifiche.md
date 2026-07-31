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
- [ ] `SEED_DEMO=true` sul backend → disattivare prima del go-live reale.
- [ ] (Opz.) Dominio + branding `noreply@newstylehair.it` (ora From = Gmail).

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
- [ ] Servizi assegnati a ciascun collaboratore (dopo che Flavia inserisce il listino)
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

### Allineamento da controllare
- [x] `closed_weekdays` allineato — 2026-07-29: confermato chiuso **domenica e
  lunedì**. Orario dei 3 collaboratori aggiornato da lun–ven a **mar–sab
  08:00–19:00** (nessun appuntamento attivo di lunedì nel DB, nessuna
  prenotazione persa).

---

# (storico) — note di setup precedenti

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

## TODO minori

- [ ] `notify_new_booking` solo `print()` — implementare notifica reale allo staff per prenotazioni online
- [ ] `service_names` è dichiarato in `backend/app/schemas/appointment.py:67`
      ma **nessuno lo popola**: arriva sempre `[]`. Di conseguenza il frontend
      non può mostrare che servizio è stato fatto — né nella scheda cliente né
      nell'area del cliente. Va riempito nel router leggendo
      `appointment_services` → `Service.name`, oppure va tolto dallo schema.
- [ ] Togliere la pastiglia "online" dalle schede collaboratore
      (`frontend/src/pages/admin/CollaboratorsPage.tsx`): al salone non
      interessa sapere chi è visibile online. Il campo `visible_online` resta —
      decide se il collaboratore è selezionabile nel portale pubblico — va via
      solo il badge sulla scheda.

---

# Stato produzione Railway (verificato 2026-05-30)

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
