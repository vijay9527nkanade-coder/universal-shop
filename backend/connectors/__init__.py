"""
connectors/__init__.py
=======================
Package entry-point.  Re-exports the most commonly needed symbols so
callers can do::

    from connectors import get_connector, search_all, list_platforms

without knowing the internal module layout.
"""

from connectors.base import BaseConnector, ConnectorError, SearchResult
from connectors.connector_registry import (
    get_connector,
    get_registry,
    list_platforms,
    reload_registry,
    search_all,
)

__all__ = [
    # base
    "BaseConnector",
    "ConnectorError",
    "SearchResult",
    # registry
    "get_connector",
    "get_registry",
    "list_platforms",
    "reload_registry",
    "search_all",
]
