"""
connectors/connector_registry.py
=================================
Auto-discovery registry for BaseConnector subclasses.

How it works
------------
On first access (lazy, via ``get_registry()``), the registry:

1. Iterates every ``*.py`` file inside the ``connectors/`` package directory
   (skipping ``__init__.py``, ``base.py``, and ``connector_registry.py`` itself).
2. Dynamically imports each module with ``importlib``.
3. Inspects every name in the module for classes that:
   - Are a *strict* subclass of ``BaseConnector`` (not ``BaseConnector`` itself).
   - Are not abstract (i.e. have no remaining ``abstractmethods``).
4. Registers each qualifying class under its ``platform`` key.

Adding a new connector
----------------------
Drop a new ``<platform>_connector.py`` file in ``connectors/``, subclass
``BaseConnector``, set ``platform = "<name>"``, implement ``search()`` — done.
Nothing else needs editing.

Public API
----------
``get_registry() -> dict[str, type[BaseConnector]]``
    Return the singleton mapping  ``{platform: ConnectorClass}``.

``get_connector(platform) -> BaseConnector``
    Return a *fresh instance* of the connector for the given platform.

``list_platforms() -> list[str]``
    Return sorted list of registered platform names.

``search_all(query) -> list[SearchResult]``
    Run ``search()`` on every registered connector and merge results.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Optional

# Import lazily to avoid circular issues at module load time
import connectors as _connectors_pkg
from connectors.base import BaseConnector, SearchResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal singleton
# ---------------------------------------------------------------------------

_registry: Optional[dict[str, type[BaseConnector]]] = None


def _build_registry() -> dict[str, type[BaseConnector]]:
    """Walk the connectors package and collect all concrete BaseConnector subclasses."""
    registry: dict[str, type[BaseConnector]] = {}

    # Files to skip (not connectors)
    _SKIP = {"__init__", "base", "connector_registry"}

    package_path = _connectors_pkg.__path__
    package_name = _connectors_pkg.__name__

    for module_info in pkgutil.iter_modules(package_path):
        if module_info.name in _SKIP:
            continue

        full_module_name = f"{package_name}.{module_info.name}"
        try:
            module = importlib.import_module(full_module_name)
        except Exception:
            logger.exception("Failed to import connector module %r", full_module_name)
            continue

        for attr_name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseConnector)
                and obj is not BaseConnector
                and not inspect.isabstract(obj)
            ):
                platform = obj.platform
                if not platform:
                    logger.warning(
                        "Skipping %s.%s: empty platform attribute.",
                        full_module_name,
                        attr_name,
                    )
                    continue
                if platform in registry:
                    logger.warning(
                        "Platform %r already registered by %s; "
                        "%s.%s will overwrite it.",
                        platform,
                        registry[platform].__module__,
                        full_module_name,
                        attr_name,
                    )
                registry[platform] = obj
                logger.debug("Registered connector %r → %s", platform, obj)

    logger.info(
        "Connector registry built: %d platform(s) found: %s",
        len(registry),
        sorted(registry),
    )
    return registry


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_registry() -> dict[str, type[BaseConnector]]:
    """Return the singleton platform → ConnectorClass mapping.

    The registry is built once on first call and cached for the lifetime
    of the process.
    """
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def get_connector(platform: str) -> BaseConnector:
    """Return a fresh instance of the connector for *platform*.

    Parameters
    ----------
    platform:
        The platform key (e.g. ``"amazon"``).

    Raises
    ------
    KeyError
        If no connector is registered for the given platform.
    """
    registry = get_registry()
    try:
        cls = registry[platform]
    except KeyError:
        available = sorted(registry)
        raise KeyError(
            f"No connector registered for platform {platform!r}. "
            f"Available: {available}"
        ) from None
    return cls()


def list_platforms() -> list[str]:
    """Return a sorted list of all registered platform names."""
    return sorted(get_registry())


def search_all(query: str) -> list[SearchResult]:
    """Run ``search(query)`` across every registered connector.

    Results from all platforms are concatenated.  Failures in individual
    connectors are logged and skipped so one bad connector never blocks
    the rest.

    Parameters
    ----------
    query:
        Free-text search string.

    Returns
    -------
    list[SearchResult]
        Merged results from all connectors, in platform registration order.
    """
    results: list[SearchResult] = []
    for platform, cls in get_registry().items():
        try:
            connector = cls()
            results.extend(connector.search(query))
        except Exception:
            logger.exception("Connector %r raised an error for query %r", platform, query)
    return results


def reload_registry() -> dict[str, type[BaseConnector]]:
    """Force a full re-scan of the connectors package.

    Useful in development / testing when new connector files are added
    without restarting the process.
    """
    global _registry
    _registry = None
    return get_registry()
