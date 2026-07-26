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

`seed.py` e `bootstrap.py` (con `SEED_DEMO=true`) creano account demo con
password debolissime. Valgono **solo per lo sviluppo locale** — le trovi nel
codice dei due script.

⚠️ Non usarli su un ambiente raggiungibile da internet: questo repository è
pubblico, quindi qualunque password scritta qui è una password nota. In
produzione tieni `SEED_DEMO=false`, imposta l'admin con `ADMIN_EMAIL` /
`ADMIN_PASSWORD`, e ruota la password con:

```bash
DATABASE_URL=... python scripts/set_admin_password.py
```

Per disattivare eventuali login demo già creati:

```bash
DATABASE_URL=... python scripts/disable_demo_logins.py
```

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

## Test automatici

La suite gira su un **PostgreSQL reale** (non SQLite): l'app usa enum, colonne
JSON e `extract`, quindi un dialect diverso nasconderebbe bug che la produzione
avrebbe comunque.

```bash
docker compose up -d db                                    # serve il DB
docker compose exec db psql -U nsh -d postgres -c "CREATE DATABASE nsh_test;"

cd backend
pip install -r requirements-dev.txt
pytest -q
```

Il DB di test viene troncato prima di ogni test, quindi non tocca i dati di
sviluppo. Per puntare altrove: `TEST_DATABASE_URL=postgresql+asyncpg://...`.

### Cosa copre

| File | Cosa garantisce |
|------|-----------------|
| `tests/test_auth_boundaries.py` | Confini fra admin, collaboratore e cliente. Regressioni della escalation cliente→admin: un fallimento qui è un problema di sicurezza, non un test instabile. |
| `tests/test_permissions_matrix.py` | `EXPECTED_GUARDS` fissa il livello di permesso di **ogni** rotta. Aggiungere o cambiare un endpoint fa fallire i test finché la mappa non viene aggiornata di proposito — così nessuna rotta finisce in produzione senza una decisione sui permessi. |
| `tests/test_appointments.py` | Macchina a stati degli appuntamenti e disponibilità: annullato/rifiutato devono liberare lo slot. |

### CI e flusso di rilascio

`.github/workflows/ci.yml` esegue tre job: test backend, typecheck + build
frontend, e `alembic upgrade head` da database vuoto — l'ultimo perché il deploy
lancia le migration all'avvio, quindi una migration che non applica manderebbe
giù il servizio al rilascio.

Trigger: push su `develop` (feedback immediato) e pull request verso `develop` o
`main`.

**`main` è protetto**, `develop` è libero:

| Branch | Protezione |
|--------|-----------|
| `develop` | nessuna — push diretto libero |
| `main` | 3 check obbligatori, validi anche per gli admin. Push diretto impossibile, force push e cancellazione bloccati. Nessuna review richiesta (si può mergiare da soli). |

Il gate sta su `main` perché è il branch che Railway deploya: se `develop` si
rompe non va offline nulla.

Lavoro quotidiano:

```bash
git checkout develop && git pull
# ... modifiche ...
git push origin develop      # la CI gira e segnala
```

Rilascio, quando `develop` è verde:

```bash
gh pr create --base main --head develop --fill
gh pr merge --merge
git checkout develop && git merge --ff-only origin/main && git push
```

L'ultima riga non è opzionale: il merge della PR crea un commit di merge che
esiste **solo** su `main`, quindi senza allineamento `develop` risulta "N commit
behind" anche a contenuto identico, e la distanza cresce a ogni rilascio.

La suite finisce anche su `main` (i file tracciati arrivano col merge), ma non
pesa sul deploy: `.dockerignore` la esclude dall'immagine e le dipendenze di
test stanno in `requirements-dev.txt`, fuori da `requirements.txt`.

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
