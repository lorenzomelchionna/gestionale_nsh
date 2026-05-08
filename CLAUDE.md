# New Style Hair — CLAUDE.md

Gestionale per salone di parrucchiere (MVP v0.1.0).

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 async + PostgreSQL 16 + Redis + Celery
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Zustand + TanStack Query
- **Infra**: Docker Compose (db, redis, backend, celery_worker, celery_beat, frontend)

## Come avviare il progetto

### Docker Compose (tutto insieme)
```bash
docker compose up --build -d
```
Servizi esposti:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Docs Swagger: http://localhost:8000/docs
- PostgreSQL: localhost:5433
- Redis: localhost:6379

### Avvio locale (senza Docker)
```bash
# Prerequisiti: db e redis via Docker
docker compose up -d db redis

# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Setup iniziale (prima volta)
```bash
cp .env.example .env
# Compilare .env con le variabili richieste
cd backend && python seed.py   # Crea tabelle e dati demo
```

### Credenziali demo
| Ruolo | Email | Password |
|-------|-------|----------|
| Admin | admin@newstylair.it | admin123 |
| Collaboratore | sofia@newstylair.it | sofia123 |
| Cliente (portale) | giulia.marino@email.it | giulia123 |

## Struttura

```
new_style_hair/
├── backend/
│   ├── app/
│   │   ├── api/          # Router admin (/api/admin/*) e pubblici (/api/public/*)
│   │   ├── models/       # Modelli SQLAlchemy (16 tabelle)
│   │   ├── schemas/      # Schemi Pydantic
│   │   ├── services/     # Business logic (availability)
│   │   ├── tasks/        # Celery (reminders ogni 15 min)
│   │   ├── utils/        # Auth JWT, email
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py
│   ├── alembic/          # Migrations (initial schema in versions/)
│   ├── seed.py           # Drop + ricrea tabelle con dati demo (solo dev)
│   ├── bootstrap.py      # Bootstrap idempotente per produzione
│   ├── worker-start.sh   # Entrypoint Celery worker (Railway)
│   ├── railway.toml      # Config deploy Railway
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/admin/  # 11 pagine admin
│   │   ├── pages/booking/# 5 pagine portale pubblico
│   │   ├── services/     # Client Axios (api.ts + publicApi.ts)
│   │   ├── store/        # Zustand (authStore, uiStore)
│   │   └── types/
│   └── package.json
├── docker-compose.yml
├── .env.example
├── README.md
└── ROADMAP.md
```

## Database

- **Migrations**: Alembic configurato con migration iniziale in `backend/alembic/versions/`. In produzione si usa `alembic upgrade head` (eseguito automaticamente dal startCommand Railway).
- **Reset DB locale**: `cd backend && python seed.py` (drop + ricrea con dati demo)
- **Bootstrap produzione**: `python bootstrap.py` crea admin + BookingConfig (idempotente). Se `SEED_DEMO=true` popola anche dati demo.
- **Nota**: strategia di migrazione produzione da implementare (fase 2 del roadmap).

## API

- Admin: `/api/admin/*` — autenticato con JWT
- Pubblico: `/api/public/*` — portale prenotazioni clienti
- Due flussi auth separati: admin (`/login`) e cliente (`/booking/login`)
- JWT: access token 30 min, refresh token 7 giorni

## Variabili d'ambiente principali

```env
DATABASE_URL=postgresql+asyncpg://nsh:nshpass@localhost:5433/new_style_hair
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<min 32 caratteri in produzione>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
FRONTEND_URL=http://localhost:5173
```

## Vite proxy

In sviluppo, il frontend usa il proxy Vite: `/api/*` → `http://localhost:8000`.
Non serve configurare `VITE_API_URL` localmente.
