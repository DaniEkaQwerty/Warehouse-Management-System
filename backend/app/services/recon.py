"""Stock Opname reconciliation against the STOCK LEDGER (not ERP).

Expected quantity = ledger balance per (warehouse, item, locator).
Physical quantity = accepted count (StockCount status FINAL) per locator.
Any difference is resolved by a Checker through an ADJUSTMENT movement so the
ledger is aligned with what was physically counted.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import audit, fail, num
from ..models import Item, StockOpname, StoLocator, User
from . import counting
from . import stock as svc


def _ledger_map(db: Session, warehouse_id: int, locator_id: int) -> dict:
    rows = svc.stock_rows(db, warehouse_id=warehouse_id, locator_id=locator_id, only_nonzero=False)
    return {r["item_id"]: r for r in rows}


def compare_locator(db: Session, sl: StoLocator, only_accepted: bool = True) -> list[dict] | None:
    """Comparison rows for one locator. Returns None when the locator is not accepted (if required)."""
    if only_accepted and sl.status != "ACCEPTED":
        return None
    phys = counting.count_map(db, sl, only_final=only_accepted) or {}
    ledger = _ledger_map(db, sl.locator.warehouse_id, sl.locator_id)
    rows = []
    for iid in set(phys) | set(ledger):
        p, l = phys.get(iid), ledger.get(iid)
        src = p or l
        physical = float(p["qty"]) if p else 0.0
        expected = float(l["qty"]) if l else 0.0
        diff = round(physical - expected, 3)
        if diff == 0:
            status = "MATCH"
        elif physical == 0:
            status = "MISSING"       # ledger has stock, physical found none
        elif expected == 0:
            status = "UNEXPECTED"    # physical found stock, ledger shows zero
        else:
            status = "VARIANCE"
        rows.append({"item_id": iid, "code": src["code"], "name": src["name"], "uom": src["uom"],
                     "physical_qty": num(physical), "ledger_qty": num(expected), "diff": diff, "status": status})
    rows.sort(key=lambda r: (r["status"] == "MATCH", r["code"]))
    return rows


def compare(db: Session, sto: StockOpname) -> dict:
    """Full reconciliation matrix for a Stock Opname: accepted locators vs ledger."""
    locs = sorted(db.scalars(select(StoLocator).where(StoLocator.sto_id == sto.id)).unique().all(),
                  key=lambda s: s.locator.code)
    loc_rows, counts = [], {"MATCH": 0, "VARIANCE": 0, "UNEXPECTED": 0, "MISSING": 0}
    pending = 0
    for sl in locs:
        rows = compare_locator(db, sl, only_accepted=True)
        if rows is None:
            pending += 1
            continue
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        loc_rows.append({"sto_locator_id": sl.id, "locator_id": sl.locator_id, "locator_code": sl.locator.code,
                         "status": sl.status, "rows": rows})
    issues = counts["VARIANCE"] + counts["UNEXPECTED"] + counts["MISSING"]
    return {"sto_id": sto.id, "sto_number": sto.sto_number, "warehouse_code": sto.warehouse.code,
            "accepted_locators": len(loc_rows), "pending_locators": pending,
            "summary": {**counts, "issues": issues}, "locators": loc_rows}


def issues_count(db: Session, sto: StockOpname) -> int:
    return compare(db, sto)["summary"]["issues"]


def resolve(db: Session, user: User, sto: StockOpname, sl: StoLocator, item_id: int, reason: str) -> dict:
    """Align the ledger to the physically counted quantity for one (locator, item) via ADJUSTMENT."""
    if sl.sto_id != sto.id:
        fail(404, "Locator tidak ditemukan pada STO ini.")
    if sl.status != "ACCEPTED":
        fail(409, "Locator belum di-ACCEPT. Selesaikan pengecekan terlebih dahulu.")
    reason = (reason or "").strip()
    if not reason:
        fail(422, "Alasan penyesuaian wajib diisi.")
    phys = counting.count_map(db, sl, only_final=True) or {}
    physical = float(phys[item_id]["qty"]) if item_id in phys else 0.0
    expected = float(svc.balance(db, sl.locator.warehouse_id, item_id, sl.locator_id))
    diff = round(physical - expected, 3)
    if diff == 0:
        fail(409, "Tidak ada selisih untuk item ini.")
    item = db.get(Item, item_id)
    if not item:
        fail(404, "Item tidak ditemukan.")
    notes = f"Penyesuaian STO {sto.sto_number} ({sl.locator.code}): {reason}"
    kwargs = dict(movement_type="ADJUSTMENT", warehouse_id=sl.locator.warehouse_id, item_id=item_id,
                  qty=abs(diff), ref_type="LAINNYA", ref_no=sto.sto_number, notes=notes)
    if diff > 0:
        kwargs["to_locator_id"] = sl.locator_id
    else:
        kwargs["from_locator_id"] = sl.locator_id
    r = svc.create_movement(db, user, **kwargs)
    audit(db, user, "STO_RESOLVE_VARIANCE", "sto_locator", sl.id,
          {"physical_qty": num(physical), "ledger_qty": num(expected)},
          {"item": item.code, "diff": diff, "reason": reason, "locator": sl.locator.code,
           "movement_no": r["movement"].movement_no})
    return svc.movement_dict(r["movement"])
