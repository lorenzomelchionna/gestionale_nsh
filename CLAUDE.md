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
| `tests/test_logging.py` | Che nei log non finiscano password, token e codici, e che la riga del registro accessi dica **chi** ha fatto la richiesta. Senza quel campo il registro è un elenco di URL. |

## Dipendenze e vulnerabilità

Due meccanismi che si tengono per mano: `.github/workflows/audit.yml` trova,
`.github/dependabot.yml` porta la correzione già scritta.

L'audit gira **a calendario** (lunedì mattina) oltre che sulle PR verso `main`,
ed è la parte che conta: una vulnerabilità viene pubblicata quando viene
pubblicata, non quando qualcuno tocca il codice. Un controllo legato solo ai
push direbbe soltanto che le dipendenze erano pulite l'ultima volta che si è
scritto qualcosa — che su un gestionale fermo per mesi non vuol dire niente.
È andata proprio così col DoS di `python-multipart`: venti mesi in produzione,
trovato da altri.

**Non è un check obbligatorio di `main`, di proposito.** Una falla pubblicata
stanotte in una dipendenza transitiva non deve poter bloccare il rilascio di
una correzione che non c'entra: sarebbe un cancello che il giorno che serve si
scavalca, e scavalcato una volta non torna più su. Ma fallisce davvero, con la
X rossa: rosso vuol dire «c'è lavoro in coda», e il lavoro arriva da solo come
PR di Dependabot.

`npm audit` gira due volte, perché sono due rischi diversi: `--omit=dev` è il
codice che finisce nel browser delle clienti e fa fallire il job; la catena di
build gira solo in CI e viene segnalata senza bloccare.

Le esclusioni stanno in `backend/.pip-audit-ignore`, **una per riga e ognuna
con scritto il perché**. La regola: si esclude solo ciò per cui non esiste una
versione corretta. Se la correzione esiste, la risposta è la PR di Dependabot,
non una riga in quel file.

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

## Log

Tutto su stdout, che è quello che Railway raccoglie. In sviluppo escono
leggibili a occhio, altrove in JSON — una riga, un oggetto — perché si possano
filtrare per campo invece che a regex: `@level:warn`, `@attore:admin:3`,
`@percorso:/api/admin/clients`.

Due chiavi sono in inglese fra tutte le altre in italiano, e devono restarci:
`level` e `message` sono le **uniche due che Railway interpreta**, tutte le
altre le indicizza soltanto. Con `livello` al posto di `level` ogni riga
risultava `info` (è il default per stdout) e `@level:warn` non trovava niente,
cioè i login falliti erano `WARNING` nel codice e indistinguibili dal traffico
normale nel posto in cui i log si guardano davvero.

| Logger | Cosa scrive |
|--------|-------------|
| `nsh.accessi` | Una riga per richiesta servita: metodo, percorso, stato, durata, IP, **attore**. `/health` escluso. |
| `nsh.sicurezza` | Login riusciti e falliti, token rifiutati, permessi negati, 429, reset password. Nomi di evento costanti (`app/audit.py`), così si cercano. |
| `nsh.notifiche`, `nsh.email`, `nsh.whatsapp`, `nsh.attivita` | Notifiche non partite, con lo stack. |

`attore` è il campo che conta: `admin:3`, `client:41`, `anonimo`. Senza quello
il registro dice che *qualcuno* ha aperto una scheda, non chi — cioè non
risponde alla domanda che si fa dopo un furto di credenziali, che è la sola
ragione per cui il registro esiste. Ogni riga porta anche un `richiesta` che
torna al chiamante nell'header `X-Request-ID`.

Cosa non ci finisce mai: password, token, codici di verifica. Non per
disciplina di chi scrive la chiamata ma per filtro (`FiltroSegreti` in
`app/logging_config.py`), che oscura i campi il cui **nome** sa di segreto e
toglie dal testo i JWT e gli header `Bearer`. Gli indirizzi email sono
mascherati (`m***i@gmail.com`) e i telefoni pure: un log di sicurezza è a sua
volta un archivio di dati personali, e su un login fallito l'indirizzo digitato
può essere di qualcuno che non c'entra niente.

Conseguenza pratica per chi aggiunge log: **non chiamare un campo
`status_code`** o simili — `code` è in elenco e verrebbe oscurato. In questo
codice quel campo si chiama `stato`.

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
