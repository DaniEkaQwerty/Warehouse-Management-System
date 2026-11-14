"""Mobile Stock Opname counting endpoints for MH (counter), plus offline sync.

Physical counting is stored via services.counting (round-based, never overwritten).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import audit, current_user, fail, require
from ..database import get_db
from ..models import StockOpname, StoLocator, SyncTransaction, User
from ..services import counting as svc
from .sto import get_visible_sto, sto_dict

router = APIRouter(prefix="/api/m/sto", tags=["sto-mobile"])
FIELD = Depends(require("MH", "CHECKER", "SUPERVISOR"))


def _my_locators(db: Session, user: User, sto_id: int):
    stmt = select(StoLocator).where(StoLocator.sto_id == sto_id)
    if not ({"ADMIN", "SUPERVISOR", "CHECKER"} & set(user.roles)):
        stmt = stmt.where(StoLocator.counter_id == user.id)
    return db.scalars(stmt).unique().all()


def _sl_or_404(db: Session, user: User, slid: int) -> StoLocator:
    sl = svc.get_sl(db, slid)
    sto = db.get(StockOpname, sl.sto_id)
    if not sto:
        fail(404, "STO tidak ditemukan.")
    get_visible_sto(db, user, sl.sto_id)
    if not ({"ADMIN", "SUPERVISOR", "CHECKER"} & set(user.roles)) and sl.counter_id != user.id:
        fail(403, "Locator ini bukan tugas Anda.")
    return sl


@router.get("")
def list_sto(db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(StockOpname).where(StockOpname.status.in_(["OPEN", "COUNTING", "CHECKING"]))
    mine = select(StoLocator.sto_id).where(StoLocator.counter_id == user.id)
    stmt = stmt.where((StockOpname.id.in_(mine)) | StockOpname.status.in_(["OPEN", "COUNTING", "CHECKING"]))
    rows = db.scalars(stmt.order_by(StockOpname.id.desc()).limit(50)).unique().all()
    out = []
    for s in rows:
        locs = _my_locators(db, user, s.id)
        todo = sum(1 for l in locs if l.status in ("NOT_STARTED", "IN_PROGRESS", "RECOUNT"))
        out.append({**sto_dict(db, s, detail=False), "my_locators": len(locs), "my_todo": todo})
    return {"items": out}


@router.get("/{sto_id}")
def sto_detail(sto_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sto = get_visible_sto(db, user, sto_id)
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    locs = _my_locators(db, user, sto_id)
    items = svc.locator_dicts(db, sorted(locs, key=lambda s: s.locator.code), with_items=False)
    for d, sl in zip(items, sorted(locs, key=lambda s: s.locator.code)):
        d.update(counter=names.get(sl.counter_id), checker=names.get(sl.checker_id))
    return {**sto_dict(db, sto, detail=True), "locators": items}


@router.get("/locators/{slid}")
def locator_detail(slid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sl = _sl_or_404(db, user, slid)
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    d = svc.locator_dict(db, sl, with_items=True)
    d.update(sto_number=db.get(StockOpname, sl.sto_id).sto_number,
             counter=names.get(sl.counter_id), checker=names.get(sl.checker_id), history=svc.history(db, sl))
    return d


class LineIn(BaseModel):
    item_id: int
    qty: float
    txn_id: str | None = Field(default=None, max_length=64)


@router.post("/locators/{slid}/lines")
def add_line(slid: int, body: LineIn, request: Request, db: Session = Depends(get_db), user: User = FIELD):
    sl = _sl_or_404(db, user, slid)
    r = svc.add_line(db, user, sl, body.item_id, body.qty, txn_id=body.txn_id)
    db.commit()
    return {"ok": True, "duplicate": r["duplicate"], "line_id": r["line_id"],
            "locator": svc.locator_dict(db, sl, with_items=True)}


@router.delete("/locators/{slid}/lines/{line_id}")
def remove_line(slid: int, line_id: int, request: Request, db: Session = Depends(get_db), user: User = FIELD):
    sl = _sl_or_404(db, user, slid)
    svc.remove_line(db, user, sl, line_id)
    db.commit()
    return {"ok": True, "locator": svc.locator_dict(db, sl, with_items=True)}


@router.post("/locators/{slid}/finish")
def finish(slid: int, request: Request, db: Session = Depends(get_db), user: User = FIELD):
    sl = _sl_or_404(db, user, slid)
    svc.finish_locator(db, user, sl)
    db.commit()
    return {"ok": True, "locator": svc.locator_dict(db, sl, with_items=False)}


class RecountIn(BaseModel):
    reason: str = Field(min_length=2, max_length=60)
    note: str | None = Field(default=None, max_length=255)


@router.post("/locators/{slid}/accept")
def accept(slid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require("CHECKER"))):
    sl = _sl_or_404(db, user, slid)
    svc.accept_locator(db, user, sl)
    db.commit()
    return {"ok": True, "locator": svc.locator_dict(db, sl, with_items=False)}


@router.post("/locators/{slid}/recount")
def recount(slid: int, body: RecountIn, request: Request, db: Session = Depends(get_db),
            user: User = Depends(require("CHECKER"))):
    sl = _sl_or_404(db, user, slid)
    svc.request_recount(db, user, sl, body.reason, body.note)
    db.commit()
    return {"ok": True, "locator": svc.locator_dict(db, sl, with_items=False)}


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
    p = t.payload
    if ttype == "STO_COUNT":
        sl = _sl_or_404(db, user, int(p.get("sto_locator_id", 0)))
        svc.add_line(db, user, sl, int(p.get("item_id", 0)), p.get("qty"), txn_id=t.txn_id)
    elif ttype == "STO_FINISH":
        sl = _sl_or_404(db, user, int(p.get("sto_locator_id", 0)))
        svc.finish_locator(db, user, sl)
    else:
        fail(422, "Jenis transaksi STO tidak dikenal.")


@router.post("/sync")
def sync(body: SyncIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    results = []
    ordered = sorted(body.transactions, key=lambda t: _ts(t.timestamp) or datetime.min)
    synced = 0
    for t in ordered:
        prev = db.scalar(select(SyncTransaction).where(SyncTransaction.txn_id == t.txn_id))
        if prev:
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
        audit(db, user, "STO_SYNC", "sync", None, None, {"records": synced}, request,
              device=(ordered[0].device_id if ordered else None))
        db.commit()
    return {"results": results, "synced": synced}
