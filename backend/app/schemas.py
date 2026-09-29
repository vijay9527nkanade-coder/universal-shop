"""
Pydantic v2 request / response schemas for all four domain models.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Product schemas
# ============================================================

class ProductBase(BaseModel):
    platform: str = Field(..., max_length=100)
    name: str = Field(..., max_length=512)
    category: Optional[str] = Field(None, max_length=255)
    price: Optional[Decimal] = Field(None, ge=0)
    rating: Optional[float] = Field(None, ge=0, le=5)
    review_count: Optional[int] = Field(None, ge=0)
    image_url: Optional[str] = None
    product_url: str
    is_fallback: bool = False


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    platform: Optional[str] = Field(None, max_length=100)
    name: Optional[str] = Field(None, max_length=512)
    category: Optional[str] = None
    price: Optional[Decimal] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    is_fallback: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int
    last_scraped_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Review schemas
# ============================================================

class ReviewBase(BaseModel):
    review_text: str
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)


class ReviewCreate(ReviewBase):
    product_id: int


class ReviewUpdate(BaseModel):
    review_text: Optional[str] = None
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)


class ReviewResponse(ReviewBase):
    id: int
    product_id: int
    scraped_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# User schemas
# ============================================================

class UserBase(BaseModel):
    device_id: str = Field(..., max_length=255)


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# UserActivity schemas
# ============================================================

class UserActivityBase(BaseModel):
    action_type: str = Field(..., max_length=100)
    query_text: Optional[str] = None
    product_id: Optional[int] = None


class UserActivityCreate(UserActivityBase):
    user_id: int


class UserActivityResponse(UserActivityBase):
    id: int
    user_id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
