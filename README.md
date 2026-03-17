# New Style Hair — Gestionale

Sistema di gestione per salone di parrucchiere. Include calendario appuntamenti, portale prenotazioni online, gestione collaboratori, clienti, servizi, prodotti e cassa.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 16
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS
- **Task queue**: Celery + Redis
- **Infrastruttura**: Docker Compose

## Prerequisiti

- Docker Desktop
- Python 3.12+ con virtualenv
- Node.js 20+

## Avvio in locale

> **Prerequisito**: Docker Desktop deve essere aperto e in esecuzione.

### Prima installazione (solo la prima volta)

**1. Copia le variabili d'ambiente**
```bash
cp .env.example .env
```

**2. Installa le dipendenze Python**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Installa le dipendenze Node**
```bash
cd frontend
npm install
```

---

### Avvio (ogni volta)

Apri **3 terminali separati** e lancia in ordine:

**Terminale 1 — Database e Redis**
```bash
docker-compose up -d db redis
```

**Terminale 2 — Backend**
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminale 3 — Frontend**
```bash
cd frontend
npm run dev
```

L'app è disponibile su **http://localhost:5173**
L'API è disponibile su **http://localhost:8000/docs**

> **Prima volta in assoluto**: dopo aver avviato il DB, esegui `python seed.py` (dal terminale 2 con venv attivo) per popolare il database con i dati demo.

---

### Stop (ogni volta)

**Terminale 2 e 3**: premi `Ctrl+C` per fermare backend e frontend.

**Terminale 1 — Ferma i container Docker**
```bash
docker-compose stop db redis
```

> Usa `docker-compose down` invece di `stop` solo se vuoi eliminare i container (i dati nel DB verranno persi).

## Credenziali demo

| Ruolo | Email | Password |
|-------|-------|----------|
| Admin | admin@newstylair.it | admin123 |
| Collaboratrice (Sofia) | sofia@newstylair.it | sofia123 |
| Cliente portale (Giulia) | giulia.marino@email.it | giulia123 |

## Struttura

```
new_style_hair/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── admin/      # Endpoints gestionale (auth, appuntamenti, clienti…)
│   │   │   └── public/     # Endpoints portale clienti (booking)
│   │   ├── models/         # Modelli SQLAlchemy
│   │   ├── schemas/        # Schemi Pydantic
│   │   ├── services/       # Logica disponibilità slot
│   │   ├── tasks/          # Celery (reminder, notifiche)
│   │   └── utils/          # Auth JWT, email
│   ├── alembic/            # Migrazioni DB
│   ├── seed.py             # Dati demo
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── admin/      # Dashboard, Calendario, Clienti, Cassa…
│   │   │   └── booking/    # Portale prenotazioni pubblico
│   │   ├── components/
│   │   ├── services/       # Client API (axios)
│   │   └── store/          # Stato globale (Zustand)
│   └── package.json
├── docker-compose.yml
└── .env
```

## API

- Documentazione interattiva: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Variabili d'ambiente principali

| Variabile | Descrizione |
|-----------|-------------|
| `DATABASE_URL` | URL connessione PostgreSQL |
| `REDIS_URL` | URL connessione Redis |
| `SECRET_KEY` | Chiave JWT (cambiare in produzione) |
| `SMTP_*` | Configurazione email per notifiche |
