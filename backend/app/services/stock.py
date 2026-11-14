"""Stock ledger business rules. Single source of truth for balances and movement validation.

Balances are NEVER stored: they are always derived from stock_movements (voided rows excluded).
Used by REST endpoints AND by the offline sync processor.
"""
from decimal import Decimal, InvalidOperation

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..core import audit, fail, num
from ..models import Item, Locator, StockMovement, User, Warehouse, now

LOCATOR_IN_TYPES = ("INBOUND", "ADJUSTMENT", "TRANSFER")
VALID_TYPES = ("INBOUND", "OUTBOUND", "TRANSFER", "ADJUSTMENT")
ZERO = Decimal("0")


# ---------------------------------------------------------------- helpers
def parse_qty(v) -> Decimal:
    try:
        q = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        fail(422, "Quantity tidak valid.")
    if q <= 0 or q > Decimal("999999999") or q.as_tuple().exponent < -3:
        fail(422, "Quantity harus lebih dari 0 (maksimal 3 desimal).")
    return q


def movement_no(db: Session, when=None) -> str:
    year = (when or now()).year
    prefix = f"MV-{year}-"
    rows = db.scalars(select(StockMovement.movement_no).where(StockMovement.movement_no.like(prefix + "%"))).all()
    top = 0
    for mn in rows:
        try:
            top = max(top, int(mn.rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return f"{prefix}{top + 1:06d}"


def _locator_balance_expr(locator_id: int):
    """Signed contribution of every non-voided movement to one locator's balance."""
    return func.coalesce(func.sum(
        case((StockMovement.to_locator_id == locator_id, StockMovement.qty), else_=0)
        - case((StockMovement.from_locator_id == locator_id, StockMovement.qty), else_=0)
    ), 0)


def balance(db: Session, warehouse_id: int, item_id: int, locator_id: int) -> Decimal:
    q = select(_locator_balance_expr(locator_id)).where(
        StockMovement.warehouse_id == warehouse_id,
        StockMovement.item_id == item_id,
        StockMovement.voided.is_(False),
        (StockMovement.from_locator_id == locator_id) | (StockMovement.to_locator_id == locator_id),
    )
    return Decimal(str(db.scalar(q) or 0))


def stock_rows(db: Session, warehouse_id: int | None = None, locator_id: int | None = None,
               item_id: int | None = None, search: str | None = None, only_nonzero: bool = True):
    """Aggregated balance per (warehouse, item, locator). Returns list of dicts."""
    q = select(
        StockMovement.warehouse_id,
        StockMovement.item_id,
        StockMovement.to_locator_id.label("locator_id"),
        func.sum(StockMovement.qty).label("qty"),
    ).where(StockMovement.voided.is_(False), StockMovement.to_locator_id.is_not(None))
    q = q.group_by(StockMovement.warehouse_id, StockMovement.item_id, StockMovement.to_locator_id)
    out_q = select(
        StockMovement.warehouse_id,
        StockMovement.item_id,
        StockMovement.from_locator_id.label("locator_id"),
        func.sum(StockMovement.qty).label("qty"),
    ).where(StockMovement.voided.is_(False), StockMovement.from_locator_id.is_not(None))
    out_q = out_q.group_by(StockMovement.warehouse_id, StockMovement.item_id, StockMovement.from_locator_id)
    if warehouse_id:
        q = q.where(StockMovement.warehouse_id == warehouse_id)
        out_q = out_q.where(StockMovement.warehouse_id == warehouse_id)
    if item_id:
        q = q.where(StockMovement.item_id == item_id)
        out_q = out_q.where(StockMovement.item_id == item_id)
    if locator_id:
        q = q.where(StockMovement.to_locator_id == locator_id)
        out_q = out_q.where(StockMovement.from_locator_id == locator_id)

    agg: dict[tuple, float] = {}
    for r in db.execute(q):
        agg[(r.warehouse_id, r.item_id, r.locator_id)] = agg.get((r.warehouse_id, r.item_id, r.locator_id), 0) + float(r.qty)
    for r in db.execute(out_q):
        agg[(r.warehouse_id, r.item_id, r.locator_id)] = agg.get((r.warehouse_id, r.item_id, r.locator_id), 0) - float(r.qty)

    rows = [{"warehouse_id": k[0], "item_id": k[1], "locator_id": k[2], "qty": v} for k, v in agg.items()
            if (not only_nonzero or abs(v) > 1e-9)]
    if not rows:
        return []
    item_ids = {r["item_id"] for r in rows}
    loc_ids = {r["locator_id"] for r in rows}
    wh_ids = {r["warehouse_id"] for r in rows}
    items = {i.id: i for i in db.scalars(select(Item).where(Item.id.in_(item_ids)))}
    locs = {l.id: l for l in db.scalars(select(Locator).where(Locator.id.in_(loc_ids)))}
    whs = {w.id: w for w in db.scalars(select(Warehouse).where(Warehouse.id.in_(wh_ids)))}
    result = []
    for r in rows:
        it, lo, wh = items.get(r["item_id"]), locs.get(r["locator_id"]), whs.get(r["warehouse_id"])
        if not it or not lo:
            continue
        if search and search.lower() not in f"{it.code} {it.name} {lo.code}".lower():
            continue
        result.append({
            "warehouse_id": r["warehouse_id"], "warehouse_code": wh.code if wh else None,
            "item_id": it.id, "code": it.code, "name": it.name, "uom": it.uom,
            "locator_id": lo.id, "locator_code": lo.code,
            "qty": num(r["qty"]),
        })
    result.sort(key=lambda x: (x["code"], x["locator_code"]))
    return result


def item_eligible(db: Session, item: Item, warehouse_id: int) -> bool:
    elig = {w.warehouse_id for w in item.warehouses}
    return (not elig) or (warehouse_id in elig)


def get_locator(db: Session, locator_id: int | None, warehouse_id: int) -> Locator:
    loc = db.get(Locator, locator_id) if locator_id else None
    if not loc:
        fail(422, "Locator tidak ditemukan.")
    if loc.warehouse_id != warehouse_id:
        fail(422, "Locator bukan milik gudang yang dipilih.")
    if not loc.active or loc.verification_status != "APPROVED":
        fail(422, f"Locator {loc.code} belum aktif/disetujui.")
    return loc


def _lock_item(db: Session, item_id: int):
    """Serialize concurrent writes on the same item (MySQL row lock; SQLite writes are serialized)."""
    try:
        db.execute(select(Item.id).where(Item.id == item_id).with_for_update())
    except Exception:
        pass


# ---------------------------------------------------------------- create / void
def create_movement(db: Session, user: User | None, *, movement_type: str, warehouse_id: int, item_id: int, qty,
                    from_locator_id: int | None = None, to_locator_id: int | None = None,
                    ref_type: str | None = None, ref_no: str | None = None, notes: str | None = None,
                    device_id: str | None = None, client_txn_id: str | None = None,
                    corrects_movement_id: int | None = None) -> dict:
    movement_type = (movement_type or "").upper()
    if movement_type not in VALID_TYPES:
        fail(422, "Jenis pergerakan tidak valid.")
    if client_txn_id:
        dup = db.scalar(select(StockMovement).where(StockMovement.client_txn_id == client_txn_id))
        if dup:
            return {"duplicate": True, "movement": dup}

    _lock_item(db, item_id)
    item = db.get(Item, item_id)
    if not item or not item.active:
        fail(404, "Item tidak ditemukan atau tidak aktif.")
    if not item_eligible(db, item, warehouse_id):
        fail(422, f"Item {item.code} tidak terdaftar untuk gudang yang dipilih.")

    has_from, has_to = from_locator_id is not None, to_locator_id is not None
    if movement_type == "INBOUND":
        if not has_to or has_from:
            fail(422, "Inbound memerlukan locator tujuan.")
    elif movement_type == "OUTBOUND":
        if not has_from or has_to:
            fail(422, "Outbound memerlukan locator asal.")
    elif movement_type == "TRANSFER":
        if not has_from or not has_to:
            fail(422, "Transfer memerlukan locator asal dan tujuan.")
        if from_locator_id == to_locator_id:
            fail(422, "Locator asal dan tujuan harus berbeda.")
    elif movement_type == "ADJUSTMENT":
        if has_from == has_to:
            fail(422, "Penyesuaian harus menambah (locator tujuan) atau mengurangi (locator asal).")

    from_loc = get_locator(db, from_locator_id, warehouse_id) if has_from else None
    to_loc = get_locator(db, to_locator_id, warehouse_id) if has_to else None
    q = parse_qty(qty)

    if from_loc is not None:
        avail = balance(db, warehouse_id, item_id, from_loc.id)
        if q > avail:
            fail(409, f"Stok tidak cukup di {from_loc.code}. Tersedia {num(avail)} {item.uom}.")

    when = now()
    m = StockMovement(
        movement_no=movement_no(db, when), movement_type=movement_type, warehouse_id=warehouse_id,
        item_id=item_id, qty=q, from_locator_id=from_locator_id, to_locator_id=to_locator_id,
        ref_type=(ref_type or None), ref_no=(ref_no or None), notes=(notes or None),
        created_by=user.id if user else None, created_at=when, device_id=device_id,
        client_txn_id=client_txn_id, corrects_movement_id=corrects_movement_id,
    )
    db.add(m)
    db.flush()
    audit(db, user, f"MOVEMENT_{movement_type}", "stock_movement", m.id, None, {
        "movement_no": m.movement_no, "item": item.code, "qty": float(q),
        "from": from_loc.code if from_loc else None, "to": to_loc.code if to_loc else None,
        "ref_type": ref_type, "ref_no": ref_no,
    }, device=device_id)
    return {"duplicate": False, "movement": m}


def void_movement(db: Session, user: User, movement: StockMovement, reason: str) -> StockMovement:
    if movement.voided:
        fail(409, "Pergerakan ini sudah dibatalkan.")
    reason = (reason or "").strip()
    if not reason:
        fail(422, "Alasan pembatalan wajib diisi.")
    for loc_id in {movement.from_locator_id, movement.to_locator_id} - {None}:
        remaining = balance(db, movement.warehouse_id, movement.item_id, loc_id)
        if movement.to_locator_id == loc_id:
            remaining -= Decimal(str(movement.qty))
        if movement.from_locator_id == loc_id:
            remaining += Decimal(str(movement.qty))
        if remaining < 0:
            fail(409, f"Pembatalan ditolak: saldo di locator akan menjadi negatif.")
    movement.voided = True
    movement.voided_by = user.id
    movement.voided_at = now()
    movement.void_reason = reason[:255]
    db.flush()
    audit(db, user, "MOVEMENT_VOID", "stock_movement", movement.id,
          {"voided": False}, {"voided": True, "reason": reason, "movement_no": movement.movement_no})
    return movement


def movement_dict(m: StockMovement, item: Item | None = None, from_loc=None, to_loc=None, creator=None) -> dict:
    item = item or m.item
    from_loc = from_loc if from_loc is not None else m.from_locator
    to_loc = to_loc if to_loc is not None else m.to_locator
    creator = creator if creator is not None else m.creator
    return {
        "id": m.id, "movement_no": m.movement_no, "movement_type": m.movement_type,
        "warehouse_id": m.warehouse_id, "warehouse_code": m.warehouse.code if m.warehouse else None,
        "item_id": m.item_id, "code": item.code if item else None, "name": item.name if item else None,
        "uom": item.uom if item else None, "qty": num(m.qty),
        "from_locator_id": m.from_locator_id, "from_locator_code": from_loc.code if from_loc else None,
        "to_locator_id": m.to_locator_id, "to_locator_code": to_loc.code if to_loc else None,
        "ref_type": m.ref_type, "ref_no": m.ref_no, "notes": m.notes,
        "created_by": m.created_by, "created_by_name": creator.full_name if creator else None,
        "created_at": m.created_at.isoformat() if m.created_at else None, "device_id": m.device_id,
        "voided": bool(m.voided), "voided_by": m.voided_by,
        "voided_at": m.voided_at.isoformat() if m.voided_at else None, "void_reason": m.void_reason,
        "corrects_movement_id": m.corrects_movement_id,
    }
