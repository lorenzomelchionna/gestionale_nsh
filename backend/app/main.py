from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings

# Admin routers
from app.api.admin.auth import router as admin_auth_router
from app.api.admin.collaborators import router as collaborators_router
from app.api.admin.clients import router as clients_router
from app.api.admin.services import router as services_router
from app.api.admin.appointments import router as appointments_router
from app.api.admin.availability import router as availability_router
from app.api.admin.products import router as products_router
from app.api.admin.payments import router as payments_router
from app.api.admin.expenses import router as expenses_router
from app.api.admin.absences import router as absences_router
from app.api.admin.settings import router as settings_router
from app.api.admin.dashboard import router as dashboard_router
from app.api.admin.messaging import router as messaging_router

# Public routers
from app.api.public.auth import router as public_auth_router
from app.api.public.booking import router as booking_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing special needed (migrations via Alembic)
    yield
    # Shutdown


app = FastAPI(
    title="New Style Hair – Gestionale",
    version="0.1.0",
    description="API per il gestionale del salone New Style Hair",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Errore interno del server"},
    )


# ── Admin API (/api/admin/...) ────────────────────────────────────
ADMIN_PREFIX = "/api/admin"

app.include_router(admin_auth_router, prefix=ADMIN_PREFIX)
app.include_router(collaborators_router, prefix=ADMIN_PREFIX)
app.include_router(clients_router, prefix=ADMIN_PREFIX)
app.include_router(services_router, prefix=ADMIN_PREFIX)
app.include_router(appointments_router, prefix=ADMIN_PREFIX)
app.include_router(availability_router, prefix=ADMIN_PREFIX)
app.include_router(products_router, prefix=ADMIN_PREFIX)
app.include_router(payments_router, prefix=ADMIN_PREFIX)
app.include_router(expenses_router, prefix=ADMIN_PREFIX)
app.include_router(absences_router, prefix=ADMIN_PREFIX)
app.include_router(settings_router, prefix=ADMIN_PREFIX)
app.include_router(dashboard_router, prefix=ADMIN_PREFIX)
app.include_router(messaging_router, prefix=ADMIN_PREFIX)

# ── Public API (/api/public/...) ──────────────────────────────────
PUBLIC_PREFIX = "/api/public"

app.include_router(public_auth_router, prefix=PUBLIC_PREFIX)
app.include_router(booking_router, prefix=PUBLIC_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
