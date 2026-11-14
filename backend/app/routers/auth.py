from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..core import (audit, create_token, current_user, fail, get_client_ip, hash_password,
                    rate_limit_check, rate_limit_fail, rate_limit_reset, verify_password)
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Pre-computed dummy hash to prevent timing-based user enumeration
DUMMY_HASH = "$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    device_id: str | None = Field(default=None, max_length=64)


def user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "roles": u.roles, "active": u.active}


@router.get("/config")
def auth_config():
    return {"demo_mode": config.SEED_DEMO, "app_name": config.APP_NAME, "app_subtitle": config.APP_SUBTITLE}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    key = f"{ip}|{body.username.strip().lower()}"
    rate_limit_check(key)
    u = db.scalar(select(User).where(User.username == body.username.strip()))

    # Timing attack prevention: always execute bcrypt check even if user does not exist
    hash_to_verify = u.password_hash if (u and not u.deleted and u.active) else DUMMY_HASH
    valid_pw = verify_password(body.password, hash_to_verify)

    if not u or u.deleted or not u.active or not valid_pw:
        rate_limit_fail(key)
        audit(db, None, "LOGIN_FAILED", "user", body.username[:50], request=request, username=body.username[:50])
        db.commit()
        fail(401, "Username atau password salah.")
    rate_limit_reset(key)
    audit(db, u, "LOGIN", "user", u.id, request=request, device=body.device_id)
    db.commit()
    return {"token": create_token(u), "user": user_dict(u)}


@router.post("/logout")
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit(db, user, "LOGOUT", "user", user.id, request=request)
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


class PwIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


@router.post("/change-password")
def change_password(body: PwIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    pw_key = f"pw_change|{ip}|{user.id}"
    rate_limit_check(pw_key, max_attempts=5, window_seconds=600)

    if not verify_password(body.old_password, user.password_hash):
        rate_limit_fail(pw_key)
        audit(db, user, "CHANGE_PASSWORD_FAILED", "user", user.id, request=request)
        db.commit()
        fail(400, "Password lama salah.")

    rate_limit_reset(pw_key)
    user.password_hash = hash_password(body.new_password)
    audit(db, user, "CHANGE_PASSWORD", "user", user.id, request=request)
    db.commit()
    return {"ok": True}
