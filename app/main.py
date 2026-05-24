"""
Red Rose Laundry — FastAPI Backend
====================================
Run locally:
    uvicorn app.main:app --reload --port 8000

Swagger docs: http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.database import init_db
from app.services.mpesa import mpesa_service
from app.api.routes import payments, orders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("🌹 Red Rose Laundry API starting...")
    await init_db()
    logger.info("Database tables ready")
    yield
    # Shutdown
    await mpesa_service.close()
    logger.info("M-Pesa HTTP client closed")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Backend API for Red Rose Laundry — laundry, carpet, and sofa cleaning services. "
        "Supports M-Pesa STK Push payments via Safaricom Daraja API."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Restrict origins in production: replace "*" with your app domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else [
        "https://yourapp.com",
        "https://www.yourapp.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(orders.router, prefix=settings.API_PREFIX)
app.include_router(payments.router, prefix=settings.API_PREFIX)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": settings.APP_NAME, "env": settings.APP_ENV}
