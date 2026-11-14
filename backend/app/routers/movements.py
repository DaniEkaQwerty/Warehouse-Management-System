"""Desktop endpoints: movement history, stock balances, dashboard and corrections."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core import audit, current_user, fail, require
from ..database import get_db
from ..models import (Item, Locator, StockMovement, SyncTransaction, User, Warehouse, now)
from ..services import stock as svc
from ..services.export import page_params, respond

router = APIRouter(prefix="/api", tags=["movements", "dashboard"])
WIDE = Depends(require("SUPERVISOR", "CHECKER"))
CORRECT = Depends(require("CHECKER"))


def _date_range(date_from: str, date_to: str) -> tuple[datetime | None, datetime | None]:
    start = end = None
    try:
        if date_from:
            start = datetime.fromisoformat(date_from)
        if date_to:
            end = datetime.fromisoformat(date_to) + timedelta(days=1)
    except ValueError:
        fail(422, "Format tanggal tidak valid (gunakan YYYY-MM-DD).")
    return start, end


def _wh_list(db: Session) -> list[dict]:
    return [{"id": w.id, "code": w.code, "name": w.name}
            for w in db.scalars(select(Warehouse).order_by(Warehouse.code))]


# ============================================================ movements
@router.get("/movements")
def list_movements(warehouse_id: int | None = None, movement_type: str = "", date_from: str = "", date_to: str = "",
                   q: str = "", include_void: bool = True, page: int = 1, size: int = 20,
                   db: Session = Depends(get_db), _=WIDE):
    stmt = select(StockMovement)
    if warehouse_id:
        stmt = stmt.where(StockMovement.warehouse_id == warehouse_id)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type.upper())
    start, end = _date_range(date_from, date_to)
    if start:
        stmt = stmt.where(StockMovement.created_at >= start)
    if end:
        stmt = stmt.where(StockMovement.created_at < end)
    if not include_void:
        stmt = stmt.where(StockMovement.voided.is_(False))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(StockMovement.movement_no.like(like), StockMovement.ref_no.like(like),
                              StockMovement.item_id.in_(select(Item.id).where(
                                  or_(Item.code.like(like), Item.name.like(like))))))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, lim = page_params(page, size)
    rows = db.scalars(stmt.order_by(StockMovement.id.desc()).offset(off).limit(lim)).unique().all()
    return {"items": [svc.movement_dict(m) for m in rows], "total": total}


@router.get("/movements/export")
def export_movements(warehouse_id: int | None = None, movement_type: str = "", date_from: str = "", date_to: str = "",
                     q: str = "", include_void: bool = True, fmt: str = "xlsx",
                     db: Session = Depends(get_db), _=WIDE):
    stmt = select(StockMovement)
    if warehouse_id:
        stmt = stmt.where(StockMovement.warehouse_id == warehouse_id)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type.upper())
    start, end = _date_range(date_from, date_to)
    if start:
        stmt = stmt.where(StockMovement.created_at >= start)
    if end:
        stmt = stmt.where(StockMovement.created_at < end)
    if not include_void:
        stmt = stmt.where(StockMovement.voided.is_(False))
    rows = db.scalars(stmt.order_by(StockMovement.id.desc()).limit(20000)).unique().all()
    headers = ["No Pergerakan", "Jenis", "Gudang", "Kode Item", "Nama Barang", "Satuan", "Qty",
               "Dari Lokator", "Ke Lokator", "Ref", "No Ref", "Petugas", "Waktu", "Dibatalkan", "Alasan Batal"]
    out = [[m.movement_no, m.movement_type, m.warehouse.code if m.warehouse else "", m.item.code if m.item else "",
            m.item.name if m.item else "", m.item.uom if m.item else "", svc.num(m.qty),
            m.from_locator.code if m.from_locator else "", m.to_locator.code if m.to_locator else "",
            m.ref_type or "", m.ref_no or "", m.creator.full_name if m.creator else "",
            m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
            "Y" if m.voided else "N", m.void_reason or ""] for m in rows]
    return respond(fmt, f"riwayat_pergerakan_{datetime.now():%Y%m%d}", "Riwayat Pergerakan Stok", headers, out)


@router.get("/movements/{mid}")
def movement_detail(mid: int, db: Session = Depends(get_db), _=WIDE):
    m = db.get(StockMovement, mid)
    if not m:
        fail(404, "Pergerakan tidak ditemukan.")
    d = svc.movement_dict(m)
    voided_by = db.get(User, m.voided_by) if m.voided_by else None
    d["voided_by_name"] = voided_by.full_name if voided_by else None
    return d


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


@router.post("/movements/{mid}/void")
def void_movement(mid: int, body: VoidIn, request: Request, db: Session = Depends(get_db), me: User = CORRECT):
    m = db.get(StockMovement, mid)
    if not m:
        fail(404, "Pergerakan tidak ditemukan.")
    svc.void_movement(db, me, m, body.reason)
    db.commit()
    db.refresh(m)
    return svc.movement_dict(m)


class AdjustIn(BaseModel):
    warehouse_id: int
    item_id: int
    locator_id: int
    qty: float
    direction: str = Field(pattern=r"^(ADD|REMOVE)$")
    reason: str = Field(min_length=3, max_length=255)
    ref_no: str | None = Field(default=None, max_length=60)
    corrects_movement_id: int | None = None


@router.post("/movements/adjust")
def adjust_movement(body: AdjustIn, request: Request, db: Session = Depends(get_db), me: User = CORRECT):
    r = svc.create_movement(
        db, me, movement_type="ADJUSTMENT", warehouse_id=body.warehouse_id, item_id=body.item_id, qty=body.qty,
        to_locator_id=body.locator_id if body.direction == "ADD" else None,
        from_locator_id=body.locator_id if body.direction == "REMOVE" else None,
        ref_type="LAINNYA", ref_no=body.ref_no, notes=body.reason, corrects_movement_id=body.corrects_movement_id)
    db.flush()
    out = svc.movement_dict(r["movement"])
    out["duplicate"] = r["duplicate"]
    db.commit()
    return out


# ============================================================ stock
@router.get("/stock")
def stock(warehouse_id: int | None = None, locator_id: int | None = None, item_id: int | None = None,
          q: str = "", page: int = 1, size: int = 50, db: Session = Depends(get_db), _=WIDE):
    rows = svc.stock_rows(db, warehouse_id=warehouse_id, locator_id=locator_id, item_id=item_id,
                          search=q.strip() or None)
    off, lim = page_params(page, size)
    return {"items": rows[off:off + lim], "total": len(rows)}


@router.get("/stock/export")
def export_stock(warehouse_id: int | None = None, locator_id: int | None = None, q: str = "", fmt: str = "xlsx",
                 db: Session = Depends(get_db), _=WIDE):
    rows = svc.stock_rows(db, warehouse_id=warehouse_id, locator_id=locator_id, search=q.strip() or None)
    out = [[r["warehouse_code"], r["locator_code"], r["code"], r["name"], r["uom"], r["qty"]] for r in rows]
    return respond(fmt, f"saldo_stok_{datetime.now():%Y%m%d}", "Laporan Saldo Stok",
                   ["Gudang", "Lokator", "Kode Item", "Nama Barang", "Satuan", "Saldo"], out)


# ============================================================ sync problems
@router.get("/sync-transactions")
def sync_transactions(result: str = "REJECTED", page: int = 1, size: int = 20, db: Session = Depends(get_db), _=WIDE):
    stmt = select(SyncTransaction)
    if result:
        stmt = stmt.where(SyncTransaction.result == result.upper())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, lim = page_params(page, size)
    rows = db.scalars(stmt.order_by(SyncTransaction.id.desc()).offset(off).limit(lim)).unique().all()
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    return {"items": [{"id": t.id, "txn_id": t.txn_id, "txn_type": t.txn_type, "result": t.result,
                       "message": t.message, "user": names.get(t.user_id), "device_id": t.device_id,
                       "processed_at": t.processed_at.isoformat() if t.processed_at else None,
                       "payload": t.payload} for t in rows], "total": total}


# ============================================================ dashboard
def _sum_qty(db: Session, mtype: str, start: datetime | None, end: datetime | None, warehouse_id: int | None) -> float:
    q = select(func.coalesce(func.sum(StockMovement.qty), 0)).where(
        StockMovement.voided.is_(False), StockMovement.movement_type == mtype)
    if start:
        q = q.where(StockMovement.created_at >= start)
    if end:
        q = q.where(StockMovement.created_at < end)
    if warehouse_id:
        q = q.where(StockMovement.warehouse_id == warehouse_id)
    return svc.num(db.scalar(q) or 0)


@router.get("/dashboard")
def dashboard(warehouse_id: int | None = None, date_from: str = "", date_to: str = "",
              db: Session = Depends(get_db), user: User = WIDE):
    start, end = _date_range(date_from, date_to)
    if not start:
        start = (now() - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    if not end:
        end = now() + timedelta(days=1)
    day_start = now().replace(hour=0, minute=0, second=0, microsecond=0)

    cards = {"movements_period": 0, "problems": 0}
    for mtype in ("INBOUND", "OUTBOUND", "TRANSFER"):
        key = mtype.lower()
        cards[f"{key}_today"] = _sum_qty(db, mtype, day_start, None, warehouse_id)
        cards[f"{key}_period"] = _sum_qty(db, mtype, start, end, warehouse_id)
        cnt = select(func.count()).select_from(StockMovement).where(
            StockMovement.voided.is_(False), StockMovement.movement_type == mtype,
            StockMovement.created_at >= start, StockMovement.created_at < end)
        if warehouse_id:
            cnt = cnt.where(StockMovement.warehouse_id == warehouse_id)
        cards["movements_period"] += db.scalar(cnt) or 0

    bal_rows = svc.stock_rows(db, warehouse_id=warehouse_id)
    cards["items"] = len({r["item_id"] for r in bal_rows})
    cards["filled_locators"] = len({r["locator_id"] for r in bal_rows})
    prob = select(func.count()).select_from(SyncTransaction).where(SyncTransaction.result == "REJECTED")
    cards["problems"] = db.scalar(prob) or 0

    chart = []
    since = (day_start - timedelta(days=6))
    cq = select(func.date(StockMovement.created_at), StockMovement.movement_type, func.sum(StockMovement.qty)).where(
        StockMovement.voided.is_(False), StockMovement.created_at >= since)
    if warehouse_id:
        cq = cq.where(StockMovement.warehouse_id == warehouse_id)
    cq = cq.group_by(func.date(StockMovement.created_at), StockMovement.movement_type)
    agg: dict = {}
    for d, mtype, qty in db.execute(cq):
        agg.setdefault(str(d), {})[mtype.lower()] = svc.num(qty or 0)
    for i in range(7):
        d = (since + timedelta(days=i)).date().isoformat()
        entry = agg.get(d, {})
        chart.append({"date": d, "inbound": entry.get("inbound", 0), "outbound": entry.get("outbound", 0),
                      "transfer": entry.get("transfer", 0)})

    recent = db.scalars(select(StockMovement).order_by(StockMovement.id.desc()).limit(10)).unique().all()
    return {"cards": cards, "chart": chart, "warehouses": _wh_list(db),
            "stock": bal_rows[:10], "recent": [svc.movement_dict(m) for m in recent],
            "filters": {"warehouse_id": warehouse_id, "date_from": start.date().isoformat(),
                        "date_to": (end - timedelta(days=1)).date().isoformat()}}
