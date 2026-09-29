"""
connectors/base.py
==================
Abstract base class that every platform connector must extend.

Contract
--------
Each concrete connector must:
  1. Set a unique class-level ``platform`` string (e.g. ``"amazon"``, ``"flipkart"``).
  2. Implement ``search(query)`` returning a list of ``SearchResult`` dicts.

SearchResult keys
-----------------
name         str            Product display name
price        float | None   Price in the local currency unit (no symbol)
rating       float | None   Aggregate rating, typically 0–5
review_count int   | None   Total number of reviews
image_url    str   | None   Absolute URL to the primary product image
product_url  str            Canonical URL to the product page
platform     str            Matches the connector's ``platform`` attribute
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TypedDict


class SearchResult(TypedDict):
    """Typed dictionary representing a single product search result."""

    name: str
    price: Optional[float]
    rating: Optional[float]
    review_count: Optional[int]
    image_url: Optional[str]
    product_url: str
    platform: str


class BaseConnector(ABC):
    """Abstract base for all e-commerce platform connectors.

    Subclass this, set ``platform``, and implement ``search``.
    The connector registry will discover your class automatically.

    Example
    -------
    .. code-block:: python

        class MyShopConnector(BaseConnector):
            platform = "myshop"

            async def search(self, query: str) -> list[SearchResult]:
                ...
    """

    #: Unique platform identifier — must be overridden in every subclass.
    platform: str = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Validate that every concrete subclass declares a non-empty platform."""
        super().__init_subclass__(**kwargs)
        # Allow intermediate abstract classes to skip the check
        if not getattr(cls, "__abstractmethods__", None) and not cls.platform:
            raise TypeError(
                f"{cls.__name__} must define a non-empty class attribute 'platform'."
            )

    @abstractmethod
    def search(self, query: str) -> list[SearchResult]:
        """Search the platform for products matching *query*.

        Parameters
        ----------
        query:
            Free-text search string (e.g. ``"wireless headphones"``).

        Returns
        -------
        list[SearchResult]
            Zero or more product dicts.  Every dict must contain at least
            ``name``, ``product_url``, and ``platform``; all other keys
            may be ``None`` when the information is unavailable.

        Raises
        ------
        ConnectorError
            If the upstream request fails or the response cannot be parsed.
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__} platform={self.platform!r}>"


class ConnectorError(Exception):
    """Raised when a connector cannot complete a search request."""

    def __init__(self, platform: str, message: str) -> None:
        self.platform = platform
        super().__init__(f"[{platform}] {message}")
