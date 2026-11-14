"""Stock Opname (Fase 2): physical count vs the stock ledger.

Roles (4): ADMIN/SUPERVISOR manage, CHECKER verifies & resolves differences,
MH (counter) performs the physical counting on the mobile interface.
Differences are aligned to the ledger by a Checker via an ADJUSTMENT movement.
"""
from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core import audit, current_user, fail, num, require
from ..database import get_db
from ..models import (STO_TRANSITIONS, ExcelImport, ExcelImportError, Locator, StockCount, StockCountDetail,
                      StockOpname, StockRecount, StoAssignment, StoLocator, User, Warehouse)
from ..services import counting as svc
from ..services import recon as recon_svc
from ..services.export import page_params

router = APIRouter(prefix="/api/sto", tags=["sto"])
MANAGER = Depends(require("SUPERVISOR"))


def is_wide(user: User) -> bool:
    return bool({"ADMIN", "SUPERVISOR", "CHECKER"} & set(user.roles))


def visible_stos(user: User):
    stmt = select(StockOpname)
    if not is_wide(user):
        mine = select(StoLocator.sto_id).where(or_(StoLocator.counter_id == user.id, StoLocator.checker_id == user.id))
        active_status = StockOpname.status.in_(["OPEN", "COUNTING", "CHECKING"])
        stmt = stmt.where(or_(StockOpname.id.in_(mine), active_status))
    return stmt


def get_visible_sto(db: Session, user: User, sto_id: int) -> StockOpname:
    sto = db.scalar(visible_stos(user).where(StockOpname.id == sto_id))
    if not sto:
        fail(404, "STO tidak ditemukan.")
    return sto


def progress(db: Session, sto: StockOpname, with_variance: bool = True) -> dict:
    stmt = select(StoLocator.status, func.count()).where(StoLocator.sto_id == sto.id).group_by(StoLocator.status)
    c = dict(db.execute(stmt).all())
    total = sum(c.values())
    accepted = c.get("ACCEPTED", 0)
    waiting = c.get("WAITING_CHECK", 0) + c.get("COMPLETED", 0)
    done = accepted + waiting
    variance = recon_svc.issues_count(db, sto) if with_variance else 0
    return {"total": total, "completed": done, "accepted": accepted, "waiting_check": waiting,
            "recount": c.get("RECOUNT", 0), "in_progress": c.get("IN_PROGRESS", 0),
            "not_started": c.get("NOT_STARTED", 0), "remaining": total - done, "variance": variance,
            "percent": round(done * 100 / total) if total else 0}


def sto_dict(db: Session, sto: StockOpname, detail=False) -> dict:
    d = {"id": sto.id, "sto_number": sto.sto_number, "sto_date": sto.sto_date.isoformat(),
         "warehouse_id": sto.warehouse_id, "warehouse_code": sto.warehouse.code, "warehouse_name": sto.warehouse.name,
         "description": sto.description, "status": sto.status, "next_status": STO_TRANSITIONS[sto.status],
         "progress": progress(db, sto, with_variance=detail)}
    if detail:
        names = {u.id: u.full_name for u in db.scalars(select(User))}
        d["assignments"] = [{"id": a.id, "locator_from": a.locator_from, "locator_to": a.locator_to,
                             "counter_id": a.counter_id, "checker_id": a.checker_id,
                             "counter": names.get(a.counter_id), "checker": names.get(a.checker_id)}
                            for a in sto.assignments]
    return d


# ------------------------------------------------------------------ list / detail
@router.get("")
def list_sto(status: str = "", q: str = "", page: int = 1, size: int = 20, db: Session = Depends(get_db),
             user: User = Depends(current_user)):
    stmt = visible_stos(user)
    if status:
        stmt = stmt.where(StockOpname.status == status)
    if q:
        stmt = stmt.where(StockOpname.sto_number.like(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, lim = page_params(page, size)
    rows = db.scalars(stmt.order_by(StockOpname.id.desc()).offset(off).limit(lim)).unique().all()
    return {"items": [sto_dict(db, s) for s in rows], "total": total}


@router.get("/{sto_id}")
def get_sto(sto_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return sto_dict(db, get_visible_sto(db, user, sto_id), detail=True)


# ------------------------------------------------------------------ create / assign
class AssignIn(BaseModel):
    locator_from: str = Field(min_length=1, max_length=40)
    locator_to: str = Field(min_length=1, max_length=40)
    counter_id: int
    checker_id: int


class StoIn(BaseModel):
    sto_number: str = Field(min_length=3, max_length=40)
    sto_date: date
    warehouse_id: int
    description: str | None = Field(default=None, max_length=255)
    assignments: list[AssignIn] = []


def _check_users(db, a: AssignIn):
    for uid, role in ((a.counter_id, "MH"), (a.checker_id, "CHECKER")):
        u = db.get(User, uid)
        if not u or u.deleted or not u.active or role not in u.roles:
            fail(422, f"User untuk peran {role} tidak valid.")
    if a.counter_id == a.checker_id:
        fail(422, "Petugas hitung dan Checker tidak boleh orang yang sama.")


def _expand(db: Session, sto: StockOpname, a: AssignIn) -> StoAssignment:
    _check_users(db, a)
    lo, hi = sorted([a.locator_from.strip().upper(), a.locator_to.strip().upper()])
    locs = db.scalars(select(Locator).where(Locator.warehouse_id == sto.warehouse_id, Locator.active == True,  # noqa
                                            Locator.code >= lo, Locator.code <= hi).order_by(Locator.code)).unique().all()
    if not locs:
        fail(422, f"Tidak ada locator aktif pada rentang {lo} s/d {hi} di gudang {sto.warehouse.code}.")
    taken = {r[0] for r in db.execute(select(StoLocator.locator_id).where(
        StoLocator.sto_id == sto.id, StoLocator.locator_id.in_([l.id for l in locs])))}
    if taken:
        codes = [l.code for l in locs if l.id in taken][:5]
        fail(409, f"Locator sudah ditugaskan pada STO ini: {', '.join(codes)}.")
    asg = StoAssignment(sto_id=sto.id, locator_from=lo, locator_to=hi,
                        counter_id=a.counter_id, checker_id=a.checker_id)
    db.add(asg)
    db.flush()
    for l in locs:
        db.add(StoLocator(sto_id=sto.id, locator_id=l.id, assignment_id=asg.id,
                          counter_id=a.counter_id, checker_id=a.checker_id))
    return asg


@router.post("")
def create_sto(body: StoIn, request: Request, db: Session = Depends(get_db), me: User = MANAGER):
    wh = db.get(Warehouse, body.warehouse_id)
    if not wh or not wh.active:
        fail(404, "Gudang tidak ditemukan.")
    if not wh.sto_enabled:
        fail(422, "Gudang ini belum diaktifkan untuk STO (sto_enabled = false).")
    number = body.sto_number.strip().upper()
    if db.scalar(select(StockOpname).where(StockOpname.sto_number == number)):
        fail(409, "Nomor STO sudah ada.")
    sto = StockOpname(sto_number=number, sto_date=body.sto_date, warehouse_id=wh.id, description=body.description,
                      status="DRAFT", created_by=me.id)
    db.add(sto)
    db.flush()
    db.refresh(sto)
    for a in body.assignments:
        _expand(db, sto, a)
        audit(db, me, "ASSIGN_TEAM", "stock_opname", sto.id, None, a.model_dump(), request)
    audit(db, me, "CREATE_STO", "stock_opname", sto.id, None,
          {"sto_number": number, "warehouse": wh.code, "assignments": len(body.assignments)}, request)
    db.commit()
    db.refresh(sto)
    return sto_dict(db, sto, detail=True)


def _editable(sto):
    if sto.status in ("COMPLETED", "CANCELLED"):
        fail(409, "STO sudah selesai/dibatalkan.")


@router.post("/{sto_id}/assignments")
def add_assignment(sto_id: int, body: AssignIn, request: Request, db: Session = Depends(get_db), me: User = MANAGER):
    sto = db.get(StockOpname, sto_id) or fail(404, "STO tidak ditemukan.")
    _editable(sto)
    _expand(db, sto, body)
    audit(db, me, "ASSIGN_TEAM", "stock_opname", sto.id, None, body.model_dump(), request)
    db.commit()
    db.refresh(sto)
    return sto_dict(db, sto, detail=True)


@router.delete("/{sto_id}/assignments/{aid}")
def delete_assignment(sto_id: int, aid: int, request: Request, db: Session = Depends(get_db), me: User = MANAGER):
    sto = db.get(StockOpname, sto_id) or fail(404, "STO tidak ditemukan.")
    _editable(sto)
    a = db.get(StoAssignment, aid)
    if not a or a.sto_id != sto_id:
        fail(404, "Penugasan tidak ditemukan.")
    started = db.scalar(select(func.count()).select_from(StoLocator).where(
        StoLocator.assignment_id == aid, StoLocator.status != "NOT_STARTED"))
    if started:
        fail(409, "Penugasan tidak dapat dihapus karena sudah ada locator yang mulai dihitung.")
    for sl in db.scalars(select(StoLocator).where(StoLocator.assignment_id == aid)):
        db.delete(sl)
    db.delete(a)
    audit(db, me, "UNASSIGN_TEAM", "stock_opname", sto_id, {"from": a.locator_from, "to": a.locator_to}, None, request)
    db.commit()
    db.refresh(sto)
    return sto_dict(db, sto, detail=True)


# ------------------------------------------------------------------ status transitions
class StatusIn(BaseModel):
    status: str
    force: bool = False


@router.post("/{sto_id}/status")
def change_status(sto_id: int, body: StatusIn, request: Request, db: Session = Depends(get_db), me: User = MANAGER):
    sto = db.get(StockOpname, sto_id) or fail(404, "STO tidak ditemukan.")
    if body.status not in STO_TRANSITIONS.get(sto.status, []):
        fail(409, f"Perubahan status {sto.status} → {body.status} tidak diizinkan.")
    if body.status == "OPEN" and not sto.assignments:
        fail(422, "Tambahkan minimal satu penugasan tim sebelum membuka STO.")
    if body.status in ("RECONCILIATION", "COMPLETED"):
        left = db.scalar(select(func.count()).select_from(StoLocator).where(
            StoLocator.sto_id == sto.id, StoLocator.status != "ACCEPTED"))
        if left and not body.force:
            fail(409, f"Masih ada {left} locator yang belum ACCEPTED. Selesaikan dulu atau gunakan 'Lanjutkan paksa'.")
    if body.status == "COMPLETED":
        issues = recon_svc.issues_count(db, sto)
        if issues and not body.force:
            fail(409, f"Masih ada {issues} selisih yang belum diselesaikan. Selesaikan via ADJUSTMENT atau gunakan 'Lanjutkan paksa'.")
    old = sto.status
    sto.status = body.status
    audit(db, me, "STO_STATUS", "stock_opname", sto.id, {"status": old}, {"status": body.status}, request)
    db.commit()
    return sto_dict(db, sto, detail=True)


@router.delete("/{sto_id}")
def delete_sto(sto_id: int, request: Request, db: Session = Depends(get_db), me: User = MANAGER):
    sto = db.get(StockOpname, sto_id) or fail(404, "STO tidak ditemukan.")
    sto_num = sto.sto_number

    for exi in db.scalars(select(ExcelImport).where(ExcelImport.sto_id == sto_id)):
        for err in db.scalars(select(ExcelImportError).where(ExcelImportError.import_id == exi.id)):
            db.delete(err)
        db.delete(exi)

    sls = db.scalars(select(StoLocator).where(StoLocator.sto_id == sto_id)).all()
    for sl in sls:
        for rc in db.scalars(select(StockRecount).where(StockRecount.sto_locator_id == sl.id)):
            db.delete(rc)
        for sc in db.scalars(select(StockCount).where(StockCount.sto_locator_id == sl.id)):
            for scd in sc.details:
                db.delete(scd)
            db.delete(sc)

        db.delete(sl)

    for a in db.scalars(select(StoAssignment).where(StoAssignment.sto_id == sto_id)):
        db.delete(a)

    db.delete(sto)
    audit(db, me, "DELETE_STO", "stock_opname", sto_id, {"sto_number": sto_num}, None, request)
    db.commit()
    return {"ok": True, "message": f"STO {sto_num} berhasil dihapus."}


@router.post("/{sto_id}/reset-counts")
def reset_sto_counts(sto_id: int, request: Request, db: Session = Depends(get_db), me: User = MANAGER):
    sto = db.get(StockOpname, sto_id) or fail(404, "STO tidak ditemukan.")
    sls = db.scalars(select(StoLocator).where(StoLocator.sto_id == sto_id)).all()
    count_deleted = 0
    for sl in sls:
        for rc in db.scalars(select(StockRecount).where(StockRecount.sto_locator_id == sl.id)):
            db.delete(rc)
        for sc in db.scalars(select(StockCount).where(StockCount.sto_locator_id == sl.id)):
            count_deleted += len(sc.details)
            for scd in sc.details:
                db.delete(scd)
            db.delete(sc)
        sl.status = "NOT_STARTED"
        sl.current_round = 1
        sl.completed_at = None
        sl.recount_reason = None
        sl.recount_note = None

    if sto.status not in ("DRAFT", "CANCELLED"):
        sto.status = "OPEN"

    audit(db, me, "RESET_STO_COUNTS", "stock_opname", sto_id, {"details_cleared": count_deleted}, None, request)
    db.commit()
    return {"ok": True, "message": f"Seluruh hasil hitungan STO {sto.sto_number} ({count_deleted} item) berhasil direset."}


# ------------------------------------------------------------------ locator monitoring
def _names(db):
    return {u.id: u.full_name for u in db.scalars(select(User))}


@router.get("/{sto_id}/locators")
def sto_locators(sto_id: int, status: str = "", q: str = "", page: int = 1, size: int = 50,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_visible_sto(db, user, sto_id)
    stmt = select(StoLocator).join(Locator, Locator.id == StoLocator.locator_id).where(StoLocator.sto_id == sto_id)
    if not is_wide(user):
        stmt = stmt.where(or_(StoLocator.counter_id == user.id, StoLocator.checker_id == user.id))
    if status:
        stmt = stmt.where(StoLocator.status == status)
    if q:
        stmt = stmt.where(Locator.code.like(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, lim = page_params(page, size)
    rows = db.scalars(stmt.order_by(Locator.code).offset(off).limit(lim)).unique().all()
    names = _names(db)
    out = svc.locator_dicts(db, rows, with_items=False)
    for d, sl in zip(out, rows):
        d.update(counter=names.get(sl.counter_id), checker=names.get(sl.checker_id))
    return {"items": out, "total": total}


@router.get("/{sto_id}/locators/{slid}")
def sto_locator_detail(sto_id: int, slid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_visible_sto(db, user, sto_id)
    sl = svc.get_sl(db, slid)
    if sl.sto_id != sto_id:
        fail(404, "Locator tidak ditemukan.")
    names = _names(db)
    d = svc.locator_dict(db, sl, with_items=True)
    d.update(counter=names.get(sl.counter_id), checker=names.get(sl.checker_id), history=svc.history(db, sl))
    return d


class ReassignIn(BaseModel):
    counter_id: int | None = None
    checker_id: int | None = None


@router.put("/{sto_id}/locators/{slid}/reassign")
def reassign(sto_id: int, slid: int, body: ReassignIn, request: Request, db: Session = Depends(get_db),
             me: User = Depends(require("SUPERVISOR"))):
    sto = get_visible_sto(db, me, sto_id)
    _editable(sto)
    sl = svc.get_sl(db, slid)
    if sl.sto_id != sto_id:
        fail(404, "Locator tidak ditemukan.")
    old = {"counter_id": sl.counter_id, "checker_id": sl.checker_id}
    if body.counter_id:
        u = db.get(User, body.counter_id)
        if not u or "MH" not in u.roles or not u.active:
            fail(422, "Petugas hitung (MH) tidak valid.")
        if body.counter_id == (body.checker_id or sl.checker_id):
            fail(422, "Petugas hitung dan Checker tidak boleh orang yang sama.")
        sl.counter_id = body.counter_id
        c = svc.current_count(db, sl)
        if c and c.status == "DRAFT":
            c.counter_id = body.counter_id
    if body.checker_id:
        u = db.get(User, body.checker_id)
        if not u or "CHECKER" not in u.roles or not u.active:
            fail(422, "Checker tidak valid.")
        if body.checker_id == sl.counter_id:
            fail(422, "Petugas hitung dan Checker tidak boleh orang yang sama.")
        sl.checker_id = body.checker_id
    audit(db, me, "REASSIGN", "sto_locator", sl.id, old,
          {"counter_id": sl.counter_id, "checker_id": sl.checker_id, "locator": sl.locator.code}, request)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ reconciliation (physical vs ledger)
@router.get("/{sto_id}/reconciliation")
def reconciliation(sto_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sto = get_visible_sto(db, user, sto_id)
    return recon_svc.compare(db, sto)


class ResolveIn(BaseModel):
    sto_locator_id: int
    item_id: int
    reason: str = Field(min_length=3, max_length=255)


@router.post("/{sto_id}/reconciliation/resolve")
def resolve_variance(sto_id: int, body: ResolveIn, request: Request, db: Session = Depends(get_db),
                     me: User = Depends(require("CHECKER"))):
    sto = get_visible_sto(db, me, sto_id)
    sl = svc.get_sl(db, body.sto_locator_id)
    out = recon_svc.resolve(db, me, sto, sl, body.item_id, body.reason)
    db.commit()
    return out
