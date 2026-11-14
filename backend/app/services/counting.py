"""Counting / checking business rules. Used by REST endpoints AND by the offline sync processor."""
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from ..core import audit, fail, num
from ..models import (Item, StockCount, StockCountDetail, StockOpname, StockRecount, StoLocator, User, now)

RECOUNT_REASONS = ["Salah Hitung", "Salah Locator", "Barang Tertukar", "Quantity Tidak Sesuai", "Other"]
COUNTABLE = ("NOT_STARTED", "IN_PROGRESS", "RECOUNT")


def _is_manager(user: User) -> bool:
    return bool({"ADMIN", "SUPERVISOR"} & set(user.roles))


def get_sl(db: Session, sl_id: int) -> StoLocator:
    sl = db.get(StoLocator, sl_id)
    if not sl:
        fail(404, "Locator tidak ditemukan.")
    return sl


def sto_of(db: Session, sl: StoLocator) -> StockOpname:
    return db.get(StockOpname, sl.sto_id)


def current_count(db: Session, sl: StoLocator, create=False) -> StockCount | None:
    c = db.scalar(select(StockCount).where(StockCount.sto_locator_id == sl.id,
                                           StockCount.round_no == sl.current_round))
    if not c and create:
        c = StockCount(sto_locator_id=sl.id, round_no=sl.current_round, counter_id=sl.counter_id, status="DRAFT")
        db.add(c)
        db.flush()
    return c


def _build_summary_from_count(c: StockCount | None, rn: int) -> dict:
    items: dict[int, dict] = {}
    if c:
        for d in sorted(c.details, key=lambda x: x.id):
            e = items.setdefault(d.item_id, {
                "item_id": d.item_id,
                "code": d.item.code,
                "name": d.item.name,
                "uom": d.item.uom,
                "verification_status": getattr(d.item, "verification_status", "APPROVED"),
                "qty": 0,
                "sheets": 0,
                "last_id": 0,
                "lines": [],
            })
            e["qty"] += float(d.quantity)
            e["sheets"] += 1
            e["last_id"] = d.id
            e["lines"].append({"id": d.id, "qty": num(d.quantity), "txn": d.client_txn_id})
    lst = sorted(items.values(), key=lambda x: -x["last_id"])
    for e in lst:
        e["qty"] = num(e["qty"])
    uoms: dict[str, float] = {}
    for e in lst:
        uoms[e["uom"]] = uoms.get(e["uom"], 0) + e["qty"]
    return {
        "round_no": rn,
        "count_status": c.status if c else None,
        "items": lst,
        "item_count": len(lst),
        "total_qty": num(sum(e["qty"] for e in lst)),
        "uom_totals": {k: num(v) for k, v in uoms.items()},
    }


def summary(db: Session, sl: StoLocator, round_no: int | None = None) -> dict:
    """Aggregated lines (SUM per item) for a round. Totals are always derived."""
    rn = round_no or sl.current_round
    c = db.scalar(select(StockCount).where(StockCount.sto_locator_id == sl.id, StockCount.round_no == rn))
    return _build_summary_from_count(c, rn)


def _format_locator_dict(sl: StoLocator, s: dict, with_items=False) -> dict:
    d = {
        "id": sl.id,
        "sto_id": sl.sto_id,
        "locator_id": sl.locator_id,
        "code": sl.locator.code,
        "warehouse_code": sl.locator.warehouse.code,
        "verification_status": getattr(sl.locator, "verification_status", "APPROVED"),
        "status": sl.status,
        "round": sl.current_round,
        "recount_reason": sl.recount_reason,
        "recount_note": sl.recount_note,
        "counter_id": sl.counter_id,
        "checker_id": sl.checker_id,
        "captain_id": sl.captain_id,
        "item_count": s["item_count"],
        "total_qty": s["total_qty"],
        "uom_totals": s["uom_totals"],
    }
    if with_items:
        d["items"] = s["items"]
    return d


def locator_dict(db: Session, sl: StoLocator, with_items=False) -> dict:
    s = summary(db, sl)
    return _format_locator_dict(sl, s, with_items=with_items)


def locator_dicts(db: Session, sls: list[StoLocator], with_items=False) -> list[dict]:
    """Batch version of locator_dict to eliminate N+1 queries on StockCount."""
    if not sls:
        return []
    pairs = [(sl.id, sl.current_round) for sl in sls]
    counts_by_pair: dict[tuple[int, int], StockCount] = {}
    for i in range(0, len(pairs), 400):
        chunk = pairs[i:i + 400]
        rows = db.scalars(
            select(StockCount).where(tuple_(StockCount.sto_locator_id, StockCount.round_no).in_(chunk))
        ).unique().all()
        for c in rows:
            counts_by_pair[(c.sto_locator_id, c.round_no)] = c
    out = []
    for sl in sls:
        c = counts_by_pair.get((sl.id, sl.current_round))
        s = _build_summary_from_count(c, sl.current_round)
        out.append(_format_locator_dict(sl, s, with_items=with_items))
    return out


# ---------------------------------------------------------------- counter actions (MH = counter)
def _check_counter(db: Session, user: User, sl: StoLocator, sto: StockOpname):
    user_roles = {str(r).upper() for r in user.roles}
    if sl.counter_id is None and "MH" in user_roles:
        sl.counter_id = user.id
    if sl.counter_id != user.id and not ({"ADMIN", "SUPERVISOR"} & user_roles):
        fail(409, "Locator ini sedang ditugaskan ke petugas lain.")
    if sto.status not in ("OPEN", "COUNTING"):
        fail(409, "STO tidak sedang dalam tahap counting.")


def parse_qty(v) -> Decimal:
    try:
        q = Decimal(str(v))
    except (InvalidOperation, ValueError):
        fail(422, "Quantity tidak valid.")
    if q <= 0 or q > Decimal("999999999") or q.as_tuple().exponent < -3:
        fail(422, "Quantity harus lebih dari 0 (maksimal 3 desimal).")
    return q


def add_line(db: Session, user: User, sl: StoLocator, item_id: int, qty, txn_id: str | None = None) -> dict:
    sto = sto_of(db, sl)
    if txn_id:
        dup = db.scalar(select(StockCountDetail).where(StockCountDetail.client_txn_id == txn_id))
        if dup:  # duplicate submission -> idempotent success
            return {"duplicate": True, "line_id": dup.id}
    _check_counter(db, user, sl, sto)
    if sl.status not in COUNTABLE:
        fail(409, "Locator sudah selesai dihitung dan menunggu pengecekan.")
    item = db.get(Item, item_id)
    if not item or not item.active:
        fail(404, "Item tidak ditemukan atau tidak aktif.")
    elig = {w.warehouse_id for w in item.warehouses}
    if elig and sto.warehouse_id not in elig:
        fail(422, f"Item {item.code} tidak terdaftar untuk gudang {sto.warehouse.code}.")
    q = parse_qty(qty)
    c = current_count(db, sl, create=True)
    max_sheet = db.scalar(select(func.max(StockCountDetail.sheet_no)).where(
        StockCountDetail.stock_count_id == c.id, StockCountDetail.item_id == item.id)) or 0
    line = StockCountDetail(stock_count_id=c.id, item_id=item.id, sheet_no=max_sheet + 1, quantity=q,
                            client_txn_id=txn_id, created_by=user.id)
    db.add(line)
    if sl.status in ("NOT_STARTED", "RECOUNT"):
        old = sl.status
        sl.status = "IN_PROGRESS"
        audit(db, user, "START_COUNTING", "sto_locator", sl.id, {"status": old}, {"status": sl.status})
    if sto.status == "OPEN":
        sto.status = "COUNTING"
        audit(db, user, "STO_STATUS", "stock_opname", sto.id, {"status": "OPEN"}, {"status": "COUNTING"})
    db.flush()
    audit(db, user, "SAVE_COUNT", "stock_count_detail", line.id, None,
          {"locator": sl.locator.code, "item": item.code, "sheet": line.sheet_no, "qty": float(q)})
    return {"duplicate": False, "line_id": line.id}


def remove_line(db: Session, user: User, sl: StoLocator, line_id: int):
    sto = sto_of(db, sl)
    _check_counter(db, user, sl, sto)
    if sl.status not in ("IN_PROGRESS", "RECOUNT", "NOT_STARTED"):
        fail(409, "Locator sudah selesai dihitung.")
    c = current_count(db, sl)
    d = db.get(StockCountDetail, line_id)
    if not c or not d or d.stock_count_id != c.id:
        fail(404, "Data hitung tidak ditemukan.")
    audit(db, user, "UNDO_COUNT", "stock_count_detail", d.id,
          {"item": d.item.code, "sheet": d.sheet_no, "qty": float(d.quantity)}, None)
    db.delete(d)


def finish_locator(db: Session, user: User, sl: StoLocator):
    sto = sto_of(db, sl)
    if sl.status == "WAITING_CHECK" and sl.counter_id == user.id:
        return  # idempotent
    _check_counter(db, user, sl, sto)
    if sl.status not in ("IN_PROGRESS", "NOT_STARTED", "RECOUNT"):
        fail(409, "Locator tidak dapat diselesaikan pada status ini.")
    c = current_count(db, sl, create=True)
    c.status = "SUBMITTED"
    c.submitted_at = now()
    old = sl.status
    sl.status = "WAITING_CHECK"
    sl.completed_at = now()
    audit(db, user, "FINISH_LOCATOR", "sto_locator", sl.id, {"status": old},
          {"status": sl.status, "round": sl.current_round, "locator": sl.locator.code})


def parse_correct_qty(v) -> Decimal:
    try:
        q = Decimal(str(v))
    except (InvalidOperation, ValueError):
        fail(422, "Quantity tidak valid.")
    if q < 0 or q > Decimal("999999999") or q.as_tuple().exponent < -3:
        fail(422, "Quantity tidak boleh negatif (maksimal 3 desimal).")
    return q


# ---------------------------------------------------------------- checker actions
def _check_checker(user: User, sl: StoLocator, sto: StockOpname):
    if not ({"CHECKER", "SUPERVISOR", "ADMIN"} & set(user.roles)):
        fail(403, "Anda tidak memiliki akses untuk tindakan ini.")
    if sl.checker_id and sl.checker_id != user.id and not _is_manager(user):
        fail(409, "Locator ini ditugaskan ke Checker lain.")
    if sl.counter_id == user.id:
        fail(409, "Counter tidak boleh mengecek hasil hitungnya sendiri.")
    if sto.status not in ("OPEN", "COUNTING", "CHECKING"):
        fail(409, "STO tidak sedang dalam tahap counting/checking.")


def _check_correct_access(user: User, sl: StoLocator, sto: StockOpname) -> str:
    if sto.status not in ("OPEN", "COUNTING", "CHECKING"):
        fail(409, "STO tidak sedang dalam tahap counting/checking.")
    user_roles = {str(r).upper() for r in user.roles}
    is_counter = (sl.counter_id == user.id) or ("MH" in user_roles and sl.counter_id is None)
    if is_counter and sl.counter_id is None:
        sl.counter_id = user.id
    if is_counter and sl.status in ("NOT_STARTED", "IN_PROGRESS", "RECOUNT"):
        return "MH"
    if is_counter and sl.status in ("WAITING_CHECK", "ACCEPTED", "COMPLETED"):
        fail(409, "Locator sudah selesai dihitung dan menunggu pengecekan Checker.")
    if not ({"CHECKER", "SUPERVISOR", "ADMIN"} & user_roles):
        fail(403, "Anda tidak memiliki akses untuk tindakan ini.")
    if sl.checker_id and sl.checker_id != user.id and not _is_manager(user):
        fail(409, "Locator ini ditugaskan ke Checker lain.")
    return "CHECKER"


def correct_item_qty(db: Session, user: User, sl: StoLocator, item_id: int, new_qty: Decimal):
    sto = sto_of(db, sl)
    role_used = _check_correct_access(user, sl, sto)
    if sl.status not in ("NOT_STARTED", "IN_PROGRESS", "RECOUNT", "WAITING_CHECK", "COMPLETED", "ACCEPTED"):
        fail(409, f"Locator tidak dapat dikoreksi pada status {sl.status}.")

    c = current_count(db, sl, create=True)
    details = [d for d in c.details if d.item_id == item_id]
    old_qty = sum(float(d.quantity) for d in details)

    if new_qty == 0:
        for d in details:
            db.delete(d)
    elif details:
        first = details[0]
        first.quantity = new_qty
        first.created_by = user.id
        for extra in details[1:]:
            db.delete(extra)
    else:
        d = StockCountDetail(stock_count_id=c.id, item_id=item_id, sheet_no=1,
                             quantity=new_qty, created_by=user.id)
        db.add(d)

    db.flush()
    action = "MH_CORRECT_QTY" if role_used == "MH" else "CHECKER_CORRECT_QTY"
    audit(db, user, action, "sto_locator", sl.id,
          {"item_id": item_id, "old_qty": old_qty},
          {"item_id": item_id, "new_qty": float(new_qty), "locator": sl.locator.code})


def accept_locator(db: Session, user: User, sl: StoLocator):
    sto = sto_of(db, sl)
    if sl.status == "ACCEPTED":
        return
    _check_checker(user, sl, sto)
    if sl.status != "WAITING_CHECK":
        fail(409, "Locator belum menunggu pengecekan.")
    c = current_count(db, sl)
    c.status = "FINAL"
    c.verified_by, c.verified_at = user.id, now()
    sl.status = "ACCEPTED"
    audit(db, user, "ACCEPT", "sto_locator", sl.id, {"status": "WAITING_CHECK"},
          {"status": "ACCEPTED", "locator": sl.locator.code, "round": sl.current_round})


def request_recount(db: Session, user: User, sl: StoLocator, reason: str, note: str | None = None):
    sto = sto_of(db, sl)
    if sl.status == "RECOUNT":
        return
    _check_checker(user, sl, sto)
    if reason not in RECOUNT_REASONS:
        fail(422, "Alasan recount wajib dipilih.")
    if reason == "Other" and not (note or "").strip():
        fail(422, "Mohon isi catatan untuk alasan 'Other'.")
    if sl.status != "WAITING_CHECK":
        fail(409, "Locator belum menunggu pengecekan.")
    c = current_count(db, sl)
    c.status = "RECOUNT"  # original kept as history, never overwritten
    new_round = sl.current_round + 1
    db.add(StockRecount(sto_locator_id=sl.id, original_count_id=c.id, requested_by=user.id,
                        reason=reason, note=(note or None) and note.strip()[:255], new_round_no=new_round))
    sl.current_round = new_round
    sl.status = "RECOUNT"
    sl.recount_reason, sl.recount_note = reason, (note or "").strip()[:255] or None
    audit(db, user, "RECOUNT", "sto_locator", sl.id, {"status": "WAITING_CHECK"},
          {"status": "RECOUNT", "reason": reason, "note": note, "new_round": new_round, "locator": sl.locator.code})


def count_map(db: Session, sl: StoLocator, round_no: int | None = None, only_final: bool = False) -> dict | None:
    """Physical quantity per item for a round as {item_id: {item_id, code, name, uom, qty}}.

    Returns None when only_final is set and the round is not FINAL (i.e. not yet accepted).
    """
    rn = round_no or sl.current_round
    c = db.scalar(select(StockCount).where(StockCount.sto_locator_id == sl.id, StockCount.round_no == rn))
    if only_final and (not c or c.status != "FINAL"):
        return None
    out: dict[int, dict] = {}
    if c:
        for d in c.details:
            e = out.setdefault(d.item_id, {"item_id": d.item_id, "code": d.item.code, "name": d.item.name,
                                           "uom": d.item.uom, "qty": 0.0})
            e["qty"] += float(d.quantity)
    for e in out.values():
        e["qty"] = num(e["qty"])
    return out


def history(db: Session, sl: StoLocator) -> list[dict]:
    out = []
    counts = db.scalars(select(StockCount).where(StockCount.sto_locator_id == sl.id)
                        .order_by(StockCount.round_no)).all()
    recounts = {r.new_round_no: r for r in db.scalars(select(StockRecount).where(StockRecount.sto_locator_id == sl.id))}
    for c in counts:
        s = _build_summary_from_count(c, c.round_no)
        r = recounts.get(c.round_no)
        user = db.get(User, c.counter_id) if c.counter_id else None
        out.append({"round_no": c.round_no, "label": "Count #1" if c.round_no == 1 else f"Recount #{c.round_no - 1}",
                    "status": c.status, "counter": user.full_name if user else None,
                    "submitted_at": c.submitted_at.isoformat() if c.submitted_at else None,
                    "reason": r.reason if r else None, "note": r.note if r else None,
                    "items": s["items"], "total_qty": s["total_qty"]})
    return out
