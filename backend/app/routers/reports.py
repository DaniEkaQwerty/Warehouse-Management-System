"""Reports: stock balance, movement history, inbound/outbound/transfer, corrections and audit log."""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core import fail, num, require
from ..database import get_db
from ..models import AuditLog, Item, Locator, StockMovement, User, Warehouse
from ..services import stock as svc
from ..services.export import page_params, respond

router = APIRouter(prefix="/api", tags=["reports"])
WIDE = Depends(require("SUPERVISOR", "CHECKER"))
ADMIN_ONLY = Depends(require("ADMIN"))


def _range(p):
    start = end = None
    try:
        if p["date_from"]:
            start = datetime.fromisoformat(p["date_from"])
        if p["date_to"]:
            end = datetime.fromisoformat(p["date_to"]) + timedelta(days=1)
    except ValueError:
        fail(422, "Format tanggal tidak valid (gunakan YYYY-MM-DD).")
    return start, end


def _movement_query(p, mtype=None, corrections=False):
    stmt = select(StockMovement)
    if p["warehouse_id"]:
        stmt = stmt.where(StockMovement.warehouse_id == p["warehouse_id"])
    if mtype:
        stmt = stmt.where(StockMovement.movement_type == mtype)
    if corrections:
        stmt = stmt.where(or_(StockMovement.voided.is_(True), StockMovement.movement_type == "ADJUSTMENT"))
    start, end = _range(p)
    if start:
        stmt = stmt.where(StockMovement.created_at >= start)
    if end:
        stmt = stmt.where(StockMovement.created_at < end)
    if p["q"]:
        like = f"%{p['q']}%"
        stmt = stmt.where(or_(StockMovement.movement_no.like(like), StockMovement.ref_no.like(like),
                              StockMovement.item_id.in_(select(Item.id).where(
                                  or_(Item.code.like(like), Item.name.like(like))))))
    return stmt


_MOVE_HEADERS = ["No Pergerakan", "Jenis", "Gudang", "Kode Item", "Nama Barang", "Satuan", "Qty",
                 "Dari Lokator", "Ke Lokator", "Ref", "No Ref", "Petugas", "Waktu", "Dibatalkan", "Alasan Batal"]


def _movement_rows(rows):
    return [[m.movement_no, m.movement_type, m.warehouse.code if m.warehouse else "", m.item.code if m.item else "",
             m.item.name if m.item else "", m.item.uom if m.item else "", num(m.qty),
             m.from_locator.code if m.from_locator else "", m.to_locator.code if m.to_locator else "",
             m.ref_type or "", m.ref_no or "", m.creator.full_name if m.creator else "",
             m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
             "Y" if m.voided else "N", m.void_reason or ""] for m in rows]


def r_stock_balance(db, user, p):
    rows = svc.stock_rows(db, warehouse_id=p["warehouse_id"], search=p["q"] or None)
    out = [[r["warehouse_code"], r["locator_code"], r["code"], r["name"], r["uom"], r["qty"]] for r in rows]
    return ("Laporan Saldo Stok", ["Gudang", "Lokator", "Kode Item", "Nama Barang", "Satuan", "Saldo"], out)


def r_movement_history(db, user, p):
    rows = db.scalars(_movement_query(p).order_by(StockMovement.id.desc()).limit(20000)).unique().all()
    return ("Riwayat Pergerakan Stok", _MOVE_HEADERS, _movement_rows(rows))


def r_inbound(db, user, p):
    rows = db.scalars(_movement_query(p, "INBOUND").order_by(StockMovement.id.desc()).limit(20000)).unique().all()
    return ("Laporan Barang Masuk (Inbound)", _MOVE_HEADERS, _movement_rows(rows))


def r_outbound(db, user, p):
    rows = db.scalars(_movement_query(p, "OUTBOUND").order_by(StockMovement.id.desc()).limit(20000)).unique().all()
    return ("Laporan Barang Keluar (Outbound)", _MOVE_HEADERS, _movement_rows(rows))


def r_transfer(db, user, p):
    rows = db.scalars(_movement_query(p, "TRANSFER").order_by(StockMovement.id.desc()).limit(20000)).unique().all()
    return ("Laporan Transfer Antar Lokator", _MOVE_HEADERS, _movement_rows(rows))


def r_corrections(db, user, p):
    rows = db.scalars(_movement_query(p, corrections=True).order_by(StockMovement.id.desc()).limit(20000)).unique().all()
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    out = []
    for m in rows:
        out.append([m.movement_no, m.movement_type, m.warehouse.code if m.warehouse else "",
                    m.item.code if m.item else "", m.item.name if m.item else "", num(m.qty),
                    m.from_locator.code if m.from_locator else "", m.to_locator.code if m.to_locator else "",
                    "DIBATALKAN" if m.voided else "PENYESUAIAN",
                    (m.void_reason or m.notes or ""), names.get(m.voided_by or m.created_by, ""),
                    m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else ""])
    return ("Laporan Koreksi & Pembatalan", ["No Pergerakan", "Jenis", "Gudang", "Kode Item", "Nama Barang", "Qty",
                                             "Dari Lokator", "Ke Lokator", "Status", "Alasan", "Petugas", "Waktu"], out)


def r_audit(db, user, p):
    stmt = select(AuditLog)
    if p["q"]:
        like = f"%{p['q']}%"
        stmt = stmt.where(or_(AuditLog.username.like(like), AuditLog.action.like(like), AuditLog.object_type.like(like),
                              AuditLog.object_id.like(like)))
    if p["action"]:
        stmt = stmt.where(AuditLog.action == p["action"])
    start, end = _range(p)
    if start:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end:
        stmt = stmt.where(AuditLog.created_at < end)
    out = [[a.created_at.strftime("%Y-%m-%d %H:%M:%S"), a.username, a.action, a.object_type, a.object_id,
            _j(a.old_value), _j(a.new_value), a.ip, a.device] for a in db.scalars(
        stmt.order_by(AuditLog.id.desc()).limit(20000))]
    return ("Audit Log Aktivitas", ["Waktu", "Pengguna", "Aksi", "Objek", "ID Objek", "Nilai Lama", "Nilai Baru", "IP",
                                    "Perangkat"], out)


def _j(v):
    return json.dumps(v, ensure_ascii=False, default=str) if v else ""


REPORTS = {"stock_balance": r_stock_balance, "movement_history": r_movement_history, "inbound": r_inbound,
           "outbound": r_outbound, "transfer": r_transfer, "corrections": r_corrections, "audit_log": r_audit}

FILE_PREFIX = {"stock_balance": "Laporan_Saldo_Stok", "movement_history": "Riwayat_Pergerakan_Stok",
               "inbound": "Laporan_Barang_Masuk", "outbound": "Laporan_Barang_Keluar",
               "transfer": "Laporan_Transfer", "corrections": "Laporan_Koreksi", "audit_log": "Audit_Log"}


@router.get("/reports/{name}")
def report(name: str, warehouse_id: str | None = None, q: str = "", action: str = "", date_from: str = "",
           date_to: str = "", fmt: str = "json", page: int = 1, size: int = 50,
           db: Session = Depends(get_db), user: User = Depends(require("SUPERVISOR", "CHECKER"))):
    fn = REPORTS.get(name)
    if not fn:
        fail(404, "Laporan tidak ditemukan.")
    if name == "audit_log" and "ADMIN" not in user.roles:
        fail(403, "Anda tidak memiliki akses ke audit log.")
    parsed_wh: int | None = None
    if warehouse_id is not None and str(warehouse_id).strip():
        try:
            parsed_wh = int(str(warehouse_id).strip())
        except ValueError:
            fail(422, "ID gudang tidak valid.")
    try:
        title, headers, rows = fn(db, user, {"warehouse_id": parsed_wh, "q": q.strip(), "action": action,
                                             "date_from": date_from, "date_to": date_to})
    except ValueError:
        fail(422, "Format tanggal tidak valid (gunakan YYYY-MM-DD).")
    if fmt in ("xlsx", "csv", "pdf"):
        date_str = datetime.now().strftime("%Y%m%d")
        return respond(fmt, f"{FILE_PREFIX.get(name, 'Laporan')}_{date_str}", title, headers, rows)
    off, lim = page_params(page, size)
    return {"title": title, "headers": headers, "rows": rows[off:off + lim], "total": len(rows)}


@router.get("/audit/actions")
def audit_actions(db: Session = Depends(get_db), _=WIDE):
    return [a for (a,) in db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))]
