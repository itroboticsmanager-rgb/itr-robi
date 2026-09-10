"""Локальна межа між пристроєм і веб-інтерфейсом."""

from .service import LocalWebService, WebServiceError, snapshot

__all__ = ["LocalWebService", "WebServiceError", "snapshot"]
