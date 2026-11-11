"""Локальна межа між пристроєм і веб-інтерфейсом."""

from .service import LocalWebService, MemoryAsset, MemoryStream, WebServiceError, snapshot

__all__ = ["LocalWebService", "MemoryAsset", "MemoryStream", "WebServiceError", "snapshot"]
