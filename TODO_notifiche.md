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
