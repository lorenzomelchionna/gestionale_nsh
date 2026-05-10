# Sistema Notifiche — New Style Hair

Documentazione del sistema di invio messaggi ai clienti su Email + WhatsApp.

---

## 1. Schema dei trigger

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                         TUTTI GLI EVENTI                                  ║
║         (ogni evento prova entrambi i canali quando possibile)            ║
╚═══════════════════════════════════════════════════════════════════════════╝

┌───────────────────────────┬────────────┬──────────────┬──────────────────┐
│ EVENTO                    │ TIMING     │ CHIAMATA     │ TASK CELERY      │
├───────────────────────────┼────────────┼──────────────┼──────────────────┤
│ ⓐ Conferma prenotazione   │ Immediato  │ async (.delay)│ send_booking_   │
│   (admin crea / conferma) │            │              │  confirmation_  │
│                           │            │              │  task            │
├───────────────────────────┼────────────┼──────────────┼──────────────────┤
│ ⓑ Reminder appuntamento   │ X ore      │ Beat         │ send_appointment_│
│   X = whatsapp_reminder_  │ prima      │ ⟳ ogni 15min │  reminders       │
│   hours (config)          │            │              │                  │
├───────────────────────────┼────────────┼──────────────┼──────────────────┤
│ ⓒ Auguri compleanno       │ Ogni gg   │ Beat         │ send_birthday_   │
│                           │ alle 9:00  │ ⟳ daily      │  greetings       │
├───────────────────────────┼────────────┼──────────────┼──────────────────┤
│ ⓓ Reset password          │ Immediato  │ sync (HTTP)  │ —                │
│                           │            │              │                  │
├───────────────────────────┼────────────┼──────────────┼──────────────────┤
│ ⓔ Messaggio custom        │ Immediato  │ sync (HTTP)  │ —                │
│   (admin → Messaggi)      │            │              │ canale a scelta  │
└───────────────────────────┴────────────┴──────────────┴──────────────────┘

  ─────●───────────────────────●───────────────●───────────────●──────►  t
  Cliente prenota         Admin              X ore         Appuntamento
  online                  conferma           prima
                              │                │
                              ▼                ▼
                         ⓐ email + WA       ⓑ email + WA
                         conferma           reminder
```

---

## 2. Comportamento per canale

### Per ogni evento (eccetto custom)

Il sistema prova **entrambi i canali**:
- **Email** → inviato se `client.email` esiste
- **WhatsApp** → inviato se `client.phone` esiste E `BookingConfig.whatsapp_enabled = true`

Se uno dei due canali fallisce, l'altro non è bloccato. Errori loggati con prefisso `[NOTIFY:<event>:<channel>]`.

### Solo per messaggi custom (admin → pagina Messaggi)

L'admin sceglie nel form:
- **Solo email** → ignora WA, invia solo agli utenti con email
- **Solo WhatsApp** → ignora email, invia solo agli utenti con telefono (se WA abilitato)
- **Email + WA** → entrambi i canali

---

## 3. Architettura del codice

### Punto unico: `app/utils/notifications.py`

Tutto passa dall'orchestratore. Funzioni esposte:

| Funzione                          | Quando chiamarla                                 |
|-----------------------------------|--------------------------------------------------|
| `notify_booking_confirmation`     | Appuntamento creato/confermato dall'admin        |
| `notify_appointment_reminder`     | Beat task — reminder X ore prima                 |
| `notify_birthday`                 | Beat task — auguri compleanno                    |
| `notify_password_reset`           | Cliente richiede reset password                  |
| `notify_custom`                   | Admin invia messaggio custom (con `channel=…`)   |

Ogni funzione:
1. Legge `BookingConfig` dal DB per sapere se WA è abilitato
2. Prova email se contatti disponibili
3. Prova WA se contatti disponibili e config abilita
4. Cattura eccezioni canale per canale (un fallimento non blocca l'altro)

### Helpers di basso livello

```
app/utils/email.py       ── send_email()  + helper per ogni evento
app/utils/whatsapp.py    ── send_whatsapp() + helper per ogni evento
```

Per **modificare un messaggio**: edita la funzione corrispondente in `email.py` o `whatsapp.py`.

Per **personalizzare conferma/reminder dal pannello**: i template sono editabili in **Impostazioni → WhatsApp** (campi `whatsapp_booking_message`, `whatsapp_reminder_message`). Variabili supportate: `{nome}`, `{data}`, `{ora}`, `{collaboratore}`.

---

## 4. Configurazione produzione

### A. Variabili d'ambiente (Railway → backend service → Variables)

```bash
# Email (Gmail SMTP — alternative: SendGrid, Mailgun, AWS SES)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tua-email@gmail.com
SMTP_PASSWORD=<app password 16 char>     # NON la password normale Google
EMAILS_FROM_EMAIL=tua-email@gmail.com
EMAILS_FROM_NAME=New Style Hair

# WhatsApp via Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=<auth token>
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886    # Sandbox; in prod, numero approvato
```

Lasciate vuote → **stub mode**: i messaggi vengono loggati in console, niente invii reali. Utile in sviluppo.

### B. Setup Email (Gmail)

1. Account Google → **Sicurezza** → **Verifica in 2 passaggi** (deve essere attiva)
2. **Password per le app** → genera password di 16 caratteri
3. Usa quella come `SMTP_PASSWORD` su Railway (non la password Google normale)

**Limite Gmail**: 500 mail/giorno gratis. Per volumi maggiori → SendGrid, Mailgun, AWS SES.

### C. Setup WhatsApp (Twilio Sandbox — SVILUPPO)

1. Crea account gratis su [twilio.com](https://www.twilio.com)
2. Console Twilio → **Messaging** → **Try it out** → **Send a WhatsApp message**
3. Copia il **Sandbox number** (di default `whatsapp:+14155238886`)
4. **Importante**: ogni cliente deve PRIMA inviare il codice "join <parola-chiave>" da WhatsApp al numero sandbox per autorizzare i messaggi. Solo dopo riceverà i messaggi del salone.
5. Variabili Railway:
   ```
   TWILIO_ACCOUNT_SID=<account sid>
   TWILIO_AUTH_TOKEN=<auth token>
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   ```
6. Su pannello admin → **Impostazioni** → abilita "Notifiche WhatsApp" + imposta ore reminder

### D. Setup WhatsApp (Twilio Business — PRODUZIONE)

Per uso reale con clienti veri:

1. **Facebook Business Manager** verificato (richiesto da Meta)
2. **Numero WhatsApp Business** — acquistato da Twilio (~5$/mese) o portato da numero esistente
3. **Template approvati da Meta**: i messaggi proattivi (conferma e reminder) richiedono template pre-approvati. Free-form ammesso solo entro 24h da quando il cliente scrive per primo. Tempo approvazione: **1-3 giorni lavorativi**.
4. Costo: **~0.005 - 0.05€** per messaggio in Italia

**ATTENZIONE**: il codice attuale invia **body free-form**. In sandbox funziona. In produzione vera, per messaggi proattivi servirà refactor per usare i template Twilio Content API. Da fare quando si attiva il business account.

### E. Worker Celery su Railway

I task Celery (reminder, birthday, conferma async) richiedono un servizio worker separato.

**Crea su Railway** un nuovo service dallo stesso repo:
- **Root Directory**: `backend`
- **Start Command**:
  ```
  celery -A app.tasks.celery_app worker --beat --loglevel=info
  ```
  (`--beat` integra il beat scheduler nel worker — soluzione single-process)
- **Variables**: stesse del backend principale (DATABASE_URL, REDIS_URL, SMTP_*, TWILIO_*)
- **No port**, **no healthcheck**

**Senza worker attivo**:
- Conferma prenotazione → task in coda Redis, mai eseguito
- Reminder → mai inviati
- Birthday → mai inviati
- Reset password e custom messaging → ✅ funzionano (chiamata sincrona)

---

## 5. Test rapido in locale

### Email (stub mode)
Senza `SMTP_USER` configurato:
1. Crea un appuntamento dal calendario
2. In console del backend vedrai:
   ```
   [EMAIL STUB] To: cliente@example.com | Subject: Prenotazione confermata...
   ```

### WhatsApp (stub mode)
Senza `TWILIO_ACCOUNT_SID`:
1. Abilita WA in Impostazioni
2. Crea appuntamento
3. In console del **worker Celery**:
   ```
   [WA STUB] To: +393331234567 | Message: Ciao Mario! La tua prenotazione...
   ```

### Email reale (Gmail SMTP)
1. Configura `SMTP_USER` e `SMTP_PASSWORD` (app password Gmail)
2. Crea appuntamento per un cliente con email reale → arriva email vera

### WhatsApp reale (Twilio Sandbox)
1. Configura `TWILIO_*` con credenziali sandbox
2. Sul tuo telefono: invia "join <parola>" al numero sandbox da WhatsApp
3. Verifica che il telefono del cliente di test sia il tuo
4. Crea appuntamento → arriva messaggio WA vero

---

## 6. Personalizzazione messaggi

| Evento                | Personalizzabile dal pannello | File codice                    |
|-----------------------|-------------------------------|--------------------------------|
| Conferma prenotazione | ✅ WA (Impostazioni)           | `email.py::send_booking_confirmation_email` |
| Reminder              | ✅ WA (Impostazioni)           | `email.py::send_appointment_reminder` |
| Auguri compleanno     | ❌ (hardcoded)                 | `email.py` + `whatsapp.py`     |
| Reset password        | ❌ (hardcoded)                 | `email.py` + `whatsapp.py`     |
| Messaggio custom      | ✅ admin scrive ogni volta     | —                              |

**Variabili template WA** (solo conferma e reminder):
```
{nome}, {data}, {ora}, {collaboratore}
```

---

## 7. Logging

Tutti gli errori di invio loggano con prefisso identificativo:
```
[NOTIFY:booking-confirm:email] appt=42 err=...
[NOTIFY:reminder:wa]           appt=15 err=...
[NOTIFY:custom:email]          client=8 err=...
```

In produzione (Railway): visibili nei logs del **worker** (per task) o del **backend** (per sync calls).

---

## 8. Roadmap futura

- [ ] Tabella `NotificationLog` per audit (chi/quando/canale/esito)
- [ ] Retry con backoff per fallimenti temporanei
- [ ] Template WA approvati Twilio (per WhatsApp Business produzione)
- [ ] SMS fallback quando WA non disponibile
- [ ] Preferenze cliente (opt-out su canale specifico)
