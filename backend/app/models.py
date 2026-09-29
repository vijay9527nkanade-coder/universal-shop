"""
SQLAlchemy ORM models.

Tables
------
- products       : scraped product listings
- reviews        : per-product reviews with sentiment
- users          : app users identified by device_id
- user_activity  : log of user actions (searches, clicks, etc.)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# products
# ---------------------------------------------------------------------------

class Product(Base):
    """A scraped product listing from any supported platform."""

    __tablename__ = "products"

    id: Mapped[int] = sa.Column(sa.Integer, primary_key=True, index=True)

    # Source
    platform: Mapped[str] = sa.Column(sa.String(100), nullable=False, index=True)
    product_url: Mapped[str] = sa.Column(sa.Text, nullable=False, unique=True)

    # Listing details
    name: Mapped[str] = sa.Column(sa.String(512), nullable=False)
    category: Mapped[str] = sa.Column(sa.String(255), nullable=True, index=True)
    price: Mapped[float] = sa.Column(sa.Numeric(12, 2), nullable=True)
    rating: Mapped[float] = sa.Column(sa.Float, nullable=True)
    review_count: Mapped[int] = sa.Column(sa.Integer, nullable=True, default=0)
    image_url: Mapped[str] = sa.Column(sa.Text, nullable=True)

    # Metadata
    is_fallback: Mapped[bool] = sa.Column(sa.Boolean, nullable=False, default=False)
    last_scraped_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=True,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    # Relationships
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="product", cascade="all, delete-orphan"
    )
    activity_entries: Mapped[list["UserActivity"]] = relationship(
        "UserActivity", back_populates="product"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} platform={self.platform!r} name={self.name!r}>"


# ---------------------------------------------------------------------------
# reviews
# ---------------------------------------------------------------------------

class Review(Base):
    """A scraped review for a product, with optional sentiment scoring."""

    __tablename__ = "reviews"

    id: Mapped[int] = sa.Column(sa.Integer, primary_key=True, index=True)
    product_id: Mapped[int] = sa.Column(
        sa.Integer,
        sa.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    review_text: Mapped[str] = sa.Column(sa.Text, nullable=False)
    sentiment_score: Mapped[float] = sa.Column(
        sa.Float,
        nullable=True,
        comment="Sentiment polarity in [-1.0, 1.0]; NULL when not yet scored",
    )
    scraped_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="reviews")

    def __repr__(self) -> str:
        return f"<Review id={self.id} product_id={self.product_id} sentiment={self.sentiment_score}>"


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

class User(Base):
    """An app user, identified by a unique device_id."""

    __tablename__ = "users"

    id: Mapped[int] = sa.Column(sa.Integer, primary_key=True, index=True)
    device_id: Mapped[str] = sa.Column(
        sa.String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Relationships
    activity: Mapped[list["UserActivity"]] = relationship(
        "UserActivity", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} device_id={self.device_id!r}>"


# ---------------------------------------------------------------------------
# user_activity
# ---------------------------------------------------------------------------

class UserActivity(Base):
    """Timestamped log of every user action (search, view, click, etc.)."""

    __tablename__ = "user_activity"

    id: Mapped[int] = sa.Column(sa.Integer, primary_key=True, index=True)
    user_id: Mapped[int] = sa.Column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action_type: Mapped[str] = sa.Column(
        sa.String(100),
        nullable=False,
        index=True,
        comment="e.g. 'search', 'view_product', 'click_link', 'filter'",
    )
    query_text: Mapped[str] = sa.Column(sa.Text, nullable=True)

    # Optional reference to a product — NULL for non-product actions
    product_id: Mapped[int] = sa.Column(
        sa.Integer,
        sa.ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    timestamp = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="activity")
    product: Mapped["Product"] = relationship("Product", back_populates="activity_entries")

    def __repr__(self) -> str:
        return (
            f"<UserActivity id={self.id} user_id={self.user_id}"
            f" action={self.action_type!r}>"
        )
