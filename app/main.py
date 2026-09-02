"""
FastAPI application entrypoint (P14).

uvicorn app.main:app

LIFESPAN:
  - calls load_models() on BOTH ML modules exactly once at startup (never at module
    import, never per request — AGENTS.md section 2). A missing artifact is a handled
    degradation, not a startup failure: load_models() marks the state degraded and the
    /recommend path falls back with recommendation_source = DETERMINISTIC_FALLBACK
    flagged on the response.
  - opens the personalization store so routes share one connection.

Routes live in app/api/routes.py and contain no business logic. This module only
assembles the app, wires CORS, and maps uncaught errors to structured JSON.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.ml import recommender as ml_recommender
from app.ml import risk as ml_risk
from app.personalization.store import PersonalizationStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # The personalization store opens one sqlite connection for the process.
    store = PersonalizationStore()
    _app.state.store = store

    # Models load ONCE at startup, never per request and never at module import.
    ml_risk.load_models()
    ml_recommender.load_models()

    logger.info(
        "startup: recommender %s, risk %s",
        "loaded" if not ml_recommender.is_degraded() else "fallback",
        "loaded" if not ml_risk.is_degraded() else "imputed",
    )
    yield

    store.close()


def _parse_origins(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Personalized Loan Recommendation System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_origins(settings.CORS_ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    """
    Structured error JSON, never a raw stack trace. A NO_SUITABLE_LOAN result is a
    200 with a complete body — it is not routed here.
    """
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An internal error occurred."},
    )
