"""ASGI entrypoint: ``uvicorn airline_core.main:app``."""

from airline_core.api import app

__all__ = ["app"]
