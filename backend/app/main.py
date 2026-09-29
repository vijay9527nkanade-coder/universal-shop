from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
import app.models  # noqa: F401 — register all ORM models with Base

settings = get_settings()

# Create all tables on startup (switch to Alembic migrations in production)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FastAPI + PostgreSQL Starter",
    description="Backend API powered by FastAPI and SQLAlchemy",
    version="0.1.0",
    debug=settings.debug,
)

from app.scheduler import start_scheduler, scheduler

@app.on_event("startup")
def on_startup():
    start_scheduler()

@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown()

# ---------------------------------------------------------------------------
# CORS — tighten allow_origins before deploying to production
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers  (add your routers here as you build them)
# ---------------------------------------------------------------------------
from app.routers import search, activity
from app import lens

app.include_router(search.router, prefix="/api/v1")
app.include_router(lens.router, prefix="/api/v1")
app.include_router(activity.router, prefix="/api/v1")



@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "env": settings.app_env}


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "healthy"}
