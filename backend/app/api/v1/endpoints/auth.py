"""Authentication endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.api.deps import get_current_user
from app.core.database import get_database
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        created_at=user["created_at"],
    )


def _auth_response(user: dict) -> AuthResponse:
    token = create_access_token(str(user["_id"]), {"email": user["email"]})
    return AuthResponse(access_token=token, user=_user_response(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    db = get_database()
    now = datetime.now(timezone.utc)
    user = {
        "name": request.name.strip(),
        "email": request.email.lower(),
        "password_hash": hash_password(request.password),
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db.users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Email is already registered")

    user["_id"] = result.inserted_id
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    db = get_database()
    user = await db.users.find_one({"email": request.email.lower()})
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_response(user)


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    return _user_response(current_user)
