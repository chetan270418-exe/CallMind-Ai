"""Auth router — single-owner login + JWT issuance."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as tz_mod
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _make_token(owner_id: int) -> str:
    s = get_settings()
    payload = {
        "sub": str(owner_id),
        "iat": int(datetime.now(tz=tz_mod.utc).timestamp()),
        "exp": int(
            (datetime.now(tz=tz_mod.utc) + timedelta(minutes=s.jwt_expire_minutes)).timestamp()
        ),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def _decode_token(token: str) -> Optional[int]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        sub = payload.get("sub")
        return int(sub) if sub else None
    except (JWTError, ValueError):
        return None


def current_owner(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.Owner:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    owner_id = _decode_token(token)
    if owner_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    owner = db.get(models.Owner, owner_id)
    if owner is None:
        raise HTTPException(status_code=401, detail="Owner not found")
    return owner


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.email == body.email).one_or_none()
    if owner is None or not _verify_password(body.password, owner.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return schemas.TokenResponse(
        access_token=_make_token(owner.id),
        owner_name=owner.name,
        assistant_name=owner.assistant_name,
    )


@router.get("/me")
def me(owner: models.Owner = Depends(current_owner)):
    return {
        "id": owner.id,
        "name": owner.name,
        "email": owner.email,
        "assistant_name": owner.assistant_name,
    }