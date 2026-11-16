"""Messages: announcements / instructions from managers (Admin/Supervisor/Checker) to field operators."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core import audit, current_user, fail, require
from ..database import get_db
from ..models import MESSAGE_LEVELS, MESSAGE_TARGETS, Message, MessageRead, User

router = APIRouter(prefix="/api", tags=["messages"])
MANAGER = Depends(require("SUPERVISOR"))


def _sender_name(db: Session, sender_id: int | None) -> str | None:
    if not sender_id:
        return None
    u = db.get(User, sender_id)
    return u.full_name if u else None


def message_dict(m: Message, sender: str | None, read: bool) -> dict:
    return {"id": m.id, "title": m.title, "body": m.body, "level": m.level,
            "target_role": m.target_role, "sender": sender,
            "created_at": m.created_at.isoformat() if m.created_at else None, "read": read}


def inbox(db: Session, user: User, limit: int = 50) -> list[dict]:
    roles = set(user.roles) or {"MH"}
    rows = db.scalars(select(Message).where(
        Message.active.is_(True),
        or_(Message.target_role.in_(roles), Message.target_role == "ALL"),
    ).order_by(Message.id.desc()).limit(limit)).unique().all()
    read_ids = {r.message_id for r in db.scalars(select(MessageRead).where(MessageRead.user_id == user.id))}
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    return [message_dict(m, names.get(m.sender_id), m.id in read_ids) for m in rows]


# ------------------------------------------------------------------ manager side
class MessageIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    body: str = Field(min_length=1, max_length=2000)
    level: str = "INFO"
    target_role: str = "MH"


@router.post("/messages")
def send_message(body: MessageIn, request: Request, db: Session = Depends(get_db), me: User = MANAGER):
    level = (body.level or "INFO").upper()
    target = (body.target_role or "MH").upper()
    if level not in MESSAGE_LEVELS:
        fail(422, "Level pesan tidak dikenal.")
    if target not in MESSAGE_TARGETS:
        fail(422, "Target penerima tidak dikenal.")
    m = Message(sender_id=me.id, title=(body.title or "").strip() or None,
                body=body.body.strip(), level=level, target_role=target)
    db.add(m)
    db.flush()
    audit(db, me, "SEND_MESSAGE", "message", m.id, None,
          {"target": target, "level": level}, request)
    db.commit()
    return message_dict(m, me.full_name, False)


@router.get("/messages")
def list_messages(target_role: str = "", page: int = 1, size: int = 30,
                  db: Session = Depends(get_db), me: User = MANAGER):
    page, size = max(1, page), min(100, max(1, size))
    stmt = select(Message).where(Message.active.is_(True))
    if target_role:
        stmt = stmt.where(Message.target_role == target_role.upper())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Message.id.desc()).offset((page - 1) * size).limit(size)).unique().all()
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    reads = dict(db.execute(select(MessageRead.message_id, func.count())
                            .group_by(MessageRead.message_id)).all())
    items = [{**message_dict(m, names.get(m.sender_id), False), "reads": reads.get(m.id, 0)} for m in rows]
    return {"items": items, "total": total}


@router.delete("/messages/{mid}")
def delete_message(mid: int, request: Request, db: Session = Depends(get_db), me: User = MANAGER):
    m = db.get(Message, mid)
    if not m or not m.active:
        fail(404, "Pesan tidak ditemukan.")
    m.active = False
    audit(db, me, "DELETE_MESSAGE", "message", mid, {"title": m.title}, None, request)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ operator (mobile) side
@router.get("/m/messages")
def my_messages(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = inbox(db, user, limit=50)
    return {"items": items, "unread": sum(1 for i in items if not i["read"])}


@router.post("/m/messages/{mid}/read")
def mark_read(mid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(Message, mid)
    if not m or not m.active:
        fail(404, "Pesan tidak ditemukan.")
    existing = db.scalar(select(MessageRead).where(MessageRead.message_id == mid, MessageRead.user_id == user.id))
    if not existing:
        db.add(MessageRead(message_id=mid, user_id=user.id))
        db.commit()
    return {"ok": True}
