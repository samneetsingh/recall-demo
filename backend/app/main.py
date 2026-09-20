"""The FastAPI application for the Recall demo backend.

This module holds the application object, the middleware, the two
infrastructure routes and the wiring. Business logic, SQL and
configuration values should stay out of this file. 
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_HEADERS, CORS_METHODS, CORS_ORIGINS
from app.db import session_store
from app.routes import sessions, webhooks


# uvicorn configures its own loggers only. Without this line the root logger
# stays at WARNING, and the webhook handler runs after the response with no
# trace in the container log.
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Make the database table before the application takes requests."""
    session_store.init_db()
    yield


app = FastAPI(
    title="Recall demo backend",
    description="An AI pre-visit intake assistant that joins a video call.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=CORS_METHODS,
    allow_headers=CORS_HEADERS,
)

app.include_router(sessions.router)
app.include_router(webhooks.router)


@app.get("/")
def root() -> dict[str, str]:
    """Give a placeholder response. This response shows that the route is live."""
    return {
        "service": "recall-demo-backend",
        "status": "placeholder",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Give the health of the application.

    The Docker healthcheck and the nginx stack use this route.
    """
    return {"status": "ok"}
