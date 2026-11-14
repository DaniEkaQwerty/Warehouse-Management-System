"""Security, auth dependencies, audit helper, shared utilities."""
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import AuditLog, User

log = logging.getLogger("sto")
bearer = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ passwords / tokens
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt(rounds=10)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_HOURS)
    return jwt.encode({"sub": str(user.id), "exp": exp}, config.SECRET_KEY, algorithm="HS256")


def get_client_ip(request: Request | None) -> str:
    if not request:
        return "-"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "-"


# ------------------------------------------------------------------ login rate limiting (in-process)
_attempts: dict[str, deque] = defaultdict(deque)


def rate_limit_check(key: str, max_attempts: int | None = None, window_seconds: int | None = None):
    max_att = max_attempts or config.LOGIN_MAX_ATTEMPTS
    win_sec = window_seconds or config.LOGIN_WINDOW_SECONDS
    now = time.time()
    cutoff = now - win_sec

    # Prune inactive entries to prevent memory leak/exhaustion attacks
    if len(_attempts) > 2000:
        stale = [k for k, q in _attempts.items() if not q or q[-1] < cutoff]
        for k in stale:
            _attempts.pop(k, None)

    q = _attempts[key]
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= max_att:
        retry_after = max(1, int(q[0] + win_sec - now))
        raise HTTPException(429, f"Terlalu banyak percobaan. Silakan coba lagi setelah {retry_after} detik.")


def rate_limit_fail(key: str):
    _attempts[key].append(time.time())


def rate_limit_reset(key: str):
    _attempts.pop(key, None)


# ------------------------------------------------------------------ current user / RBAC
def current_user(request: Request,
                 cred: HTTPAuthorizationCredentials | None = Depends(bearer),
                 token: str | None = None,
                 db: Session = Depends(get_db)) -> User:
    raw = None
    if cred and cred.credentials:
        raw = cred.credentials
    elif token:
        raw = token
    elif "token" in request.query_params:
        raw = request.query_params.get("token")
    if not raw:
        raise HTTPException(401, "Silakan login terlebih dahulu.")
    try:
        data = jwt.decode(raw, config.SECRET_KEY, algorithms=["HS256"])
        user = db.get(User, int(data["sub"]))
    except Exception:
        raise HTTPException(401, "Sesi berakhir. Silakan login kembali.")
    if not user or not user.active or user.deleted:
        raise HTTPException(401, "Akun tidak aktif.")
    return user


def require(*roles: str):
    """ADMIN always passes. Otherwise the user needs at least one of the roles."""
    allowed = set(roles) | {"ADMIN"}

    def dep(user: User = Depends(current_user)) -> User:
        if not allowed.intersection(user.roles):
            raise HTTPException(403, "Anda tidak memiliki akses untuk tindakan ini.")
        return user
    return dep


# ------------------------------------------------------------------ audit
def audit(db: Session, user: User | None, action: str, obj_type: str | None = None, obj_id=None,
          old=None, new=None, request: Request | None = None, device: str | None = None, username=None):
    ip = get_client_ip(request) if request else None
    ua = device or (request.headers.get("user-agent", "")[:120] if request else None)
    db.add(AuditLog(user_id=user.id if user else None, username=user.username if user else username,
                    action=action, object_type=obj_type, object_id=str(obj_id) if obj_id is not None else None,
                    old_value=old, new_value=new, ip=ip, device=ua))


def fail(code: int, msg: str):
    raise HTTPException(code, msg)


def num(v) -> float:
    f = float(v or 0)
    return int(f) if f == int(f) else round(f, 3)
