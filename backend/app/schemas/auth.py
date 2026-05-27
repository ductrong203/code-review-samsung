"""Auth and review history schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ReviewHistoryItem(BaseModel):
    id: str
    pr_url: Optional[str] = None
    message: str
    comments_count: int = 0
    risk_level: Optional[str] = None
    review: Dict[str, Any]
    created_at: datetime


class ReviewHistoryResponse(BaseModel):
    items: List[ReviewHistoryItem]
