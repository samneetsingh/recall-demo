"""The FastAPI application for the Recall demo backend.

This module holds the application object, the middleware and the two
infrastructure routes. Task 2 adds the routers from ``app.routes`` here. Keep
the business logic and the configuration values out of this file. The
configuration is in ``app.config``.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_HEADERS, CORS_METHODS, CORS_ORIGINS

app = FastAPI(
    title="Recall demo backend",
    description="An AI pre-visit intake assistant that joins a video call.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=CORS_METHODS,
    allow_headers=CORS_HEADERS,
)

# Task 2 registers the routers here:
#     from app.routes import sessions, webhooks
#     app.include_router(sessions.router)
#     app.include_router(webhooks.router)


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
