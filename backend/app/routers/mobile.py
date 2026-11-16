"""Mobile endpoints for Material Handling (MH): inbound / outbound / transfer, offline bundle and sync."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core import audit, current_user, fail, require
from ..database import get_db
from ..models import (Item, ItemWarehouse, Locator, StockMovement, SyncTransaction, User, Warehouse, now)
from ..services import stock as svc
from .messages import inbox
from .sto_mobile import my_sto_tasks

router = APIRouter(prefix="/api/m", tags=["mobile"])
FIELD = Depends(require("MH", "CHECKER", "SUPERVISOR"))


def _warehouses(db: Session, active_only=True) -> list[dict]:
    stmt = select(Warehouse)
    if active_only:
        stmt = stmt.where(Warehouse.active == True)  # noqa
    return [{"id": w.id, "code": w.code, "name": w.name} for w in db.scalars(stmt.order_by(Warehouse.code))]


def _active_items(db: Session, warehouse_id: int | None):
    stmt = select(Item).where(Item.active == True)  # noqa
    if warehouse_id:
        elig_ids = select(ItemWarehouse.item_id).where(ItemWarehouse.warehouse_id == warehouse_id)
        any_elig = select(ItemWarehouse.item_id)
        stmt = stmt.where(or_(Item.id.in_(elig_ids), ~Item.id.in_(any_elig)))
    return db.scalars(stmt).unique().all()


def _item_dict(i: Item) -> dict:
    return {"id": i.id, "code": i.code, "name": i.name, "uom": i.uom, "qr_code": i.qr_code,
            "barcode": i.barcode, "group_name": i.group_name}


@router.get("/home")
def home(warehouse_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    day_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    recent = db.scalars(select(StockMovement).where(StockMovement.created_by == user.id)
                        .order_by(StockMovement.id.desc()).limit(10)).unique().all()
    counts = {}
    for mtype in ("INBOUND", "OUTBOUND", "TRANSFER"):
        q = select(func.coalesce(func.sum(StockMovement.qty), 0)).where(
            StockMovement.voided.is_(False), StockMovement.movement_type == mtype,
            StockMovement.created_at >= day_start)
        if warehouse_id:
            q = q.where(StockMovement.warehouse_id == warehouse_id)
        counts[mtype.lower()] = svc.num(db.scalar(q) or 0)
    msgs = inbox(db, user, limit=50)
    return {"warehouses": _warehouses(db), "counts": counts,
            "recent": [svc.movement_dict(m) for m in recent], "server_time": now().isoformat(),
            "messages": msgs[:20], "unread": sum(1 for m in msgs if not m["read"]),
            "tasks": my_sto_tasks(db, user)}


@router.get("/bundle")
def bundle(warehouse_id: int | None = None, include_items: bool = True,
           db: Session = Depends(get_db), user: User = Depends(current_user)):
    loc_stmt = select(Locator).where(Locator.active == True, Locator.verification_status == "APPROVED")  # noqa
    if warehouse_id:
        loc_stmt = loc_stmt.where(Locator.warehouse_id == warehouse_id)
    locs = db.scalars(loc_stmt.order_by(Locator.warehouse_id, Locator.code)).unique().all()
    locator_list = [{"id": l.id, "warehouse_id": l.warehouse_id, "code": l.code,
                     "zone": l.zone, "rack": l.rack, "level": l.level} for l in locs]
    items_list = [_item_dict(i) for i in _active_items(db, warehouse_id)] if include_items else []
    return {"warehouses": _warehouses(db), "locators": locator_list, "items": items_list,
            "ref_types": ["PO", "SURAT_JALAN", "DO", "LAINNYA"], "server_time": now().isoformat()}


@router.get("/stock")
def m_stock(warehouse_id: int, locator_id: int | None = None, item_id: int | None = None, q: str = "",
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = svc.stock_rows(db, warehouse_id=warehouse_id, locator_id=locator_id, item_id=item_id, search=q.strip() or None)
    return {"items": rows}


class MovementIn(BaseModel):
    warehouse_id: int
    item_id: int
    qty: float
    from_locator_id: int | None = None
    to_locator_id: int | None = None
    ref_type: str | None = Field(default=None, max_length=15)
    ref_no: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=1000)
    txn_id: str | None = Field(default=None, max_length=64)
    device_id: str | None = Field(default=None, max_length=64)


def _create_movement(db: Session, user: User, movement_type: str, body: MovementIn) -> dict:
    """Create a movement and build its dict. Does NOT commit (caller controls the transaction)."""
    r = svc.create_movement(db, user, movement_type=movement_type, warehouse_id=body.warehouse_id,
                            item_id=body.item_id, qty=body.qty, from_locator_id=body.from_locator_id,
                            to_locator_id=body.to_locator_id, ref_type=body.ref_type, ref_no=body.ref_no,
                            notes=body.notes, device_id=body.device_id, client_txn_id=body.txn_id)
    db.flush()
    out = svc.movement_dict(r["movement"])
    out["duplicate"] = r["duplicate"]
    return out


@router.post("/inbound")
def inbound(body: MovementIn, request: Request, db: Session = Depends(get_db), user: User = FIELD):
    out = _create_movement(db, user, "INBOUND", body)
    db.commit()
    return out


@router.post("/outbound")
def outbound(body: MovementIn, request: Request, db: Session = Depends(get_db), user: User = FIELD):
    out = _create_movement(db, user, "OUTBOUND", body)
    db.commit()
    return out


@router.post("/transfer")
def transfer(body: MovementIn, request: Request, db: Session = Depends(get_db), user: User = FIELD):
    out = _create_movement(db, user, "TRANSFER", body)
    db.commit()
    return out


# ------------------------------------------------------------------ offline sync
class Txn(BaseModel):
    txn_id: str = Field(min_length=8, max_length=64)
    txn_type: str
    payload: dict
    timestamp: str | None = None
    device_id: str | None = Field(default=None, max_length=64)


class SyncIn(BaseModel):
    transactions: list[Txn] = Field(max_length=500)


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None) if s else None
    except ValueError:
        return None


def _apply(db: Session, user: User, t: Txn):
    ttype = (t.txn_type or "").upper()
    if ttype not in ("INBOUND", "OUTBOUND", "TRANSFER"):
        fail(422, "Jenis transaksi tidak dikenal.")
    p = t.payload
    body = MovementIn(
        warehouse_id=int(p.get("warehouse_id", 0)), item_id=int(p.get("item_id", 0)),
        qty=float(p.get("qty", 0)), from_locator_id=p.get("from_locator_id"), to_locator_id=p.get("to_locator_id"),
        ref_type=p.get("ref_type"), ref_no=p.get("ref_no"), notes=p.get("notes"),
        txn_id=t.txn_id, device_id=t.device_id)
    _create_movement(db, user, ttype, body)


@router.post("/sync")
def sync(body: SyncIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    results = []
    ordered = sorted(body.transactions, key=lambda t: _ts(t.timestamp) or datetime.min)
    synced = 0
    for t in ordered:
        prev = db.scalar(select(SyncTransaction).where(SyncTransaction.txn_id == t.txn_id))
        if prev:  # duplicate submission: return the original outcome
            results.append({"txn_id": t.txn_id, "result": "DUPLICATE" if prev.result == "OK" else prev.result,
                            "message": prev.message})
            continue
        try:
            with db.begin_nested():
                _apply(db, user, t)
            result, msg = "OK", None
            synced += 1
        except HTTPException as e:
            result, msg = "REJECTED", str(e.detail)
        except (KeyError, ValueError, TypeError):
            result, msg = "REJECTED", "Data transaksi tidak valid."
        db.add(SyncTransaction(txn_id=t.txn_id, user_id=user.id, device_id=t.device_id, txn_type=t.txn_type,
                               client_timestamp=_ts(t.timestamp), payload=t.payload, result=result, message=msg))
        db.commit()
        results.append({"txn_id": t.txn_id, "result": result, "message": msg})
    if synced:
        audit(db, user, "SYNC", "sync", None, None, {"records": synced}, request,
              device=(ordered[0].device_id if ordered else None))
        db.commit()
    return {"results": results, "synced": synced}
