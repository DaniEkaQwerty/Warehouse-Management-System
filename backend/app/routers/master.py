from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..core import audit, current_user, fail, hash_password, require
from ..database import get_db
from ..models import (ROLES, Item, ItemWarehouse, Locator, Role, StockCountDetail, StockMovement,
                      StockOpname, StoLocator, User, UserRole, Warehouse, now)
from ..services.export import page_params, respond

router = APIRouter(prefix="/api", tags=["master"])
ADMIN = Depends(require("ADMIN"))
MASTER_WRITE = Depends(require("ADMIN"))
ITEM_WRITE = Depends(require("ADMIN"))
ANY = Depends(current_user)


def paged(db, stmt, count_stmt, page, size, order):
    off, lim = page_params(page, size)
    total = db.scalar(count_stmt)
    rows = db.scalars(stmt.order_by(*order).offset(off).limit(lim)).unique().all()
    return rows, total


# ============================================================ users
class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    roles: list[str] = Field(min_length=1)
    active: bool = True


def _user_row(u):
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "roles": u.roles, "active": u.active}


def _set_roles(db, u, roles):
    bad = [r for r in roles if r not in ROLES]
    if bad:
        fail(422, f"Role tidak dikenal: {', '.join(bad)}")
    role_map = {r.code: r for r in db.scalars(select(Role))}
    u.user_roles.clear()
    db.flush()
    for code in dict.fromkeys(roles):
        u.user_roles.append(UserRole(role=role_map[code]))


@router.get("/users")
def list_users(q: str = "", role: str = "", page: int = 1, size: int = 20, db: Session = Depends(get_db),
               _=ADMIN):
    stmt = select(User).where(User.deleted == False)  # noqa
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.username.like(like), User.full_name.like(like)))
    if role:
        stmt = stmt.join(UserRole).join(Role).where(Role.code == role)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, lim = page_params(page, size)
    rows = db.scalars(stmt.order_by(User.username).offset(off).limit(lim)).unique().all()
    return {"items": [_user_row(u) for u in rows], "total": total}


@router.get("/users/export")
def export_users(fmt: str = "xlsx", db: Session = Depends(get_db), _=ADMIN):
    rows = db.scalars(select(User).where(User.deleted == False).order_by(User.username)).unique().all()  # noqa
    return respond(fmt, "users", "Master Pengguna", ["Username", "Nama Lengkap", "Roles", "Active"],
                   [[u.username, u.full_name, ", ".join(sorted(u.roles)), "Y" if u.active else "N"] for u in rows])


@router.get("/users/options")
def user_options(role: str = "", db: Session = Depends(get_db), _=Depends(require("SUPERVISOR"))):
    stmt = select(User).where(User.deleted == False, User.active == True)  # noqa
    if role:
        stmt = stmt.join(UserRole).join(Role).where(Role.code == role)
    return [{"id": u.id, "username": u.username, "full_name": u.full_name} for u in
            db.scalars(stmt.order_by(User.full_name)).unique()]


@router.post("/users")
def create_user(body: UserIn, request: Request, db: Session = Depends(get_db), me=ADMIN):
    if not body.password:
        fail(422, "Password wajib diisi.")
    if db.scalar(select(User).where(User.username == body.username)):
        fail(409, "Username sudah digunakan.")
    u = User(username=body.username, full_name=body.full_name, password_hash=hash_password(body.password),
             active=body.active)
    db.add(u)
    db.flush()
    _set_roles(db, u, body.roles)
    audit(db, me, "MASTER_CREATE", "user", u.id, None, {"username": u.username, "roles": body.roles}, request)
    db.commit()
    return _user_row(u)


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, request: Request, db: Session = Depends(get_db), me=ADMIN):
    u = db.get(User, uid)
    if not u or u.deleted:
        fail(404, "User tidak ditemukan.")
    clash = db.scalar(select(User).where(User.username == body.username, User.id != uid))
    if clash:
        fail(409, "Username sudah digunakan.")
    old = _user_row(u)
    if u.id == me.id and (not body.active or "ADMIN" not in body.roles):
        fail(422, "Anda tidak dapat menonaktifkan atau mencabut role ADMIN dari akun sendiri.")
    u.username, u.full_name, u.active = body.username, body.full_name, body.active
    if body.password:
        u.password_hash = hash_password(body.password)
    _set_roles(db, u, body.roles)
    audit(db, me, "MASTER_UPDATE", "user", u.id, old, _user_row(u), request)
    db.commit()
    return _user_row(u)


@router.delete("/users/{uid}")
def delete_user(uid: int, request: Request, db: Session = Depends(get_db), me=ADMIN):
    u = db.get(User, uid)
    if not u or u.deleted:
        fail(404, "User tidak ditemukan.")
    if u.id == me.id:
        fail(422, "Anda tidak dapat menghapus akun sendiri.")
    u.deleted, u.active = True, False
    audit(db, me, "MASTER_DELETE", "user", u.id, {"username": u.username}, None, request)
    db.commit()
    return {"ok": True}


# ============================================================ warehouses
class WarehouseIn(BaseModel):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="FG", max_length=40)
    sto_enabled: bool = True
    active: bool = True


def _wh(w):
    return {"id": w.id, "code": w.code, "name": w.name, "type": w.type, "sto_enabled": w.sto_enabled,
            "active": w.active}


@router.get("/warehouses")
def list_warehouses(q: str = "", sto_enabled: bool | None = None, active_only: bool = False, page: int = 1,
                    size: int = 100, db: Session = Depends(get_db), _=ANY):
    stmt = select(Warehouse)
    if q:
        stmt = stmt.where(or_(Warehouse.code.like(f"%{q}%"), Warehouse.name.like(f"%{q}%")))
    if sto_enabled is not None:
        stmt = stmt.where(Warehouse.sto_enabled == sto_enabled)
    if active_only:
        stmt = stmt.where(Warehouse.active == True)  # noqa
    rows, total = paged(db, stmt, select(func.count()).select_from(stmt.subquery()), page, size, [Warehouse.code])
    return {"items": [_wh(w) for w in rows], "total": total}


@router.get("/warehouses/export")
def export_warehouses(fmt: str = "xlsx", db: Session = Depends(get_db), _=ADMIN):
    rows = db.scalars(select(Warehouse).order_by(Warehouse.code)).unique().all()
    return respond(fmt, "warehouses", "Master Gudang", ["Kode Gudang", "Nama Gudang", "Tipe", "STO Enabled", "Active"],
                   [[w.code, w.name, w.type, "Y" if w.sto_enabled else "N", "Y" if w.active else "N"] for w in rows])


@router.post("/warehouses")
def create_warehouse(body: WarehouseIn, request: Request, db: Session = Depends(get_db), me=MASTER_WRITE):
    if db.scalar(select(Warehouse).where(Warehouse.code == body.code.upper())):
        fail(409, "Kode gudang sudah ada.")
    w = Warehouse(**{**body.model_dump(), "code": body.code.upper()})
    db.add(w)
    db.flush()
    audit(db, me, "MASTER_CREATE", "warehouse", w.id, None, _wh(w), request)
    db.commit()
    return _wh(w)


@router.put("/warehouses/{wid}")
def update_warehouse(wid: int, body: WarehouseIn, request: Request, db: Session = Depends(get_db), me=MASTER_WRITE):
    w = db.get(Warehouse, wid)
    if not w:
        fail(404, "Gudang tidak ditemukan.")
    if db.scalar(select(Warehouse).where(Warehouse.code == body.code.upper(), Warehouse.id != wid)):
        fail(409, "Kode gudang sudah ada.")
    old = _wh(w)
    for k, v in body.model_dump().items():
        setattr(w, k, v.upper() if k == "code" else v)
    audit(db, me, "MASTER_UPDATE", "warehouse", w.id, old, _wh(w), request)
    db.commit()
    return _wh(w)


@router.delete("/warehouses/{wid}")
def delete_warehouse(wid: int, request: Request, db: Session = Depends(get_db), me=MASTER_WRITE):
    w = db.get(Warehouse, wid)
    if not w:
        fail(404, "Gudang tidak ditemukan.")
    if db.scalar(select(StockOpname.id).where(StockOpname.warehouse_id == wid).limit(1)):
        fail(409, f"Gudang {w.code} sedang digunakan dalam data STO dan tidak dapat dihapus. Anda dapat menonaktifkannya.")
    if db.scalar(select(Locator.id).where(Locator.warehouse_id == wid).limit(1)):
        fail(409, f"Gudang {w.code} masih memiliki data locator. Hapus locator terlebih dahulu atau nonaktifkan gudang.")
    if db.scalar(select(StockMovement.id).where(StockMovement.warehouse_id == wid).limit(1)):
        fail(409, f"Gudang {w.code} sudah memiliki riwayat pergerakan stok dan tidak dapat dihapus. Anda dapat menonaktifkannya.")
    db.execute(delete(ItemWarehouse).where(ItemWarehouse.warehouse_id == wid))
    audit(db, me, "MASTER_DELETE", "warehouse", w.id, _wh(w), None, request)
    db.delete(w)
    db.commit()
    return {"ok": True}


# ============================================================ locators
class LocatorIn(BaseModel):
    warehouse_id: int
    code: str = Field(min_length=1, max_length=40)
    zone: str | None = Field(default=None, max_length=20)
    rack: str | None = Field(default=None, max_length=20)
    level: str | None = Field(default=None, max_length=20)
    active: bool = True


def _loc(l: Locator, names: dict[int, str] | None = None):
    d = {
        "id": l.id,
        "warehouse_id": l.warehouse_id,
        "warehouse_code": l.warehouse.code,
        "code": l.code,
        "zone": l.zone,
        "rack": l.rack,
        "level": l.level,
        "active": l.active,
        "verification_status": getattr(l, "verification_status", "APPROVED") or "APPROVED",
        "created_by": l.created_by,
        "verified_by": l.verified_by,
        "verified_at": l.verified_at.isoformat() if l.verified_at else None,
        "verification_note": l.verification_note,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }
    if names is not None:
        d["created_by_name"] = names.get(l.created_by)
        d["verified_by_name"] = names.get(l.verified_by)
    return d


@router.get("/locators")
def list_locators(q: str = "", warehouse_id: int | None = None, verification_status: str = "",
                  page: int = 1, size: int = 20, db: Session = Depends(get_db), _=ANY):
    stmt = select(Locator)
    if warehouse_id:
        stmt = stmt.where(Locator.warehouse_id == warehouse_id)
    if verification_status:
        stmt = stmt.where(Locator.verification_status == verification_status.upper())
    if q:
        stmt = stmt.where(Locator.code.like(f"%{q}%"))
    rows, total = paged(db, stmt, select(func.count()).select_from(stmt.subquery()), page, size,
                        [Locator.warehouse_id, Locator.code])
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    return {"items": [_loc(l, names) for l in rows], "total": total}


@router.get("/locators/export")
def export_locators(warehouse_id: str | None = None, fmt: str = "xlsx", db: Session = Depends(get_db), _=ADMIN):
    stmt = select(Locator)
    if warehouse_id and str(warehouse_id).strip():
        try:
            stmt = stmt.where(Locator.warehouse_id == int(str(warehouse_id).strip()))
        except ValueError:
            pass
    rows = db.scalars(stmt.order_by(Locator.warehouse_id, Locator.code)).unique().all()
    return respond(fmt, "locators", "Master Locator",
                   ["Warehouse Code", "Locator Code", "Zone", "Rack", "Level", "Verification", "Active"],
                   [[l.warehouse.code, l.code, l.zone or "", l.rack or "", l.level or "",
                     getattr(l, "verification_status", "APPROVED"), "Y" if l.active else "N"] for l in rows])


@router.post("/locators")
def create_locator(body: LocatorIn, request: Request, db: Session = Depends(get_db), me=MASTER_WRITE):
    if not db.get(Warehouse, body.warehouse_id):
        fail(404, "Gudang tidak ditemukan.")
    if db.scalar(select(Locator).where(Locator.warehouse_id == body.warehouse_id, Locator.code == body.code.upper())):
        fail(409, "Kode locator sudah ada di gudang ini.")
    l = Locator(
        **{**body.model_dump(), "code": body.code.upper()},
        verification_status="APPROVED",
        created_by=me.id,
        verified_by=me.id,
        verified_at=now(),
    )
    db.add(l)
    db.flush()
    audit(db, me, "MASTER_CREATE", "locator", l.id, None, {"code": l.code, "warehouse_id": l.warehouse_id}, request)
    db.commit()
    db.refresh(l)
    return _loc(l)


@router.put("/locators/{lid}")
def update_locator(lid: int, body: LocatorIn, request: Request, db: Session = Depends(get_db), me=MASTER_WRITE):
    l = db.get(Locator, lid)
    if not l:
        fail(404, "Locator tidak ditemukan.")
    if db.scalar(select(Locator).where(Locator.warehouse_id == body.warehouse_id,
                                       Locator.code == body.code.upper(), Locator.id != lid)):
        fail(409, "Kode locator sudah ada di gudang ini.")
    old = _loc(l)
    for k, v in body.model_dump().items():
        setattr(l, k, v.upper() if k == "code" else v)
    if l.verification_status == "PENDING" and l.active:
        l.verification_status = "APPROVED"
        l.verified_by = me.id
        l.verified_at = now()
    audit(db, me, "MASTER_UPDATE", "locator", l.id, old, {"code": l.code, "active": l.active}, request)
    db.commit()
    db.refresh(l)
    return _loc(l)


@router.delete("/locators/{lid}")
def delete_locator(lid: int, request: Request, db: Session = Depends(get_db), me=MASTER_WRITE):
    l = db.get(Locator, lid)
    if not l:
        fail(404, "Locator tidak ditemukan.")
    if db.scalar(select(StoLocator.id).where(StoLocator.locator_id == lid).limit(1)):
        fail(409, f"Locator {l.code} sudah digunakan dalam transaksi STO dan tidak dapat dihapus. Anda dapat menonaktifkannya.")
    if db.scalar(select(StockMovement.id).where(
            (StockMovement.from_locator_id == lid) | (StockMovement.to_locator_id == lid)).limit(1)):
        fail(409, f"Locator {l.code} sudah memiliki riwayat pergerakan stok dan tidak dapat dihapus. Anda dapat menonaktifkannya.")
    audit(db, me, "MASTER_DELETE", "locator", l.id, _loc(l), None, request)
    db.delete(l)
    db.commit()
    return {"ok": True}


class LocatorGen(BaseModel):
    warehouse_id: int
    zones: list[str] = Field(min_length=1, max_length=26)
    racks: int = Field(ge=1, le=99)
    levels: int = Field(ge=1, le=99)


@router.post("/locators/generate")
def generate_locators(body: LocatorGen, request: Request, db: Session = Depends(get_db), me=MASTER_WRITE):
    if not db.get(Warehouse, body.warehouse_id):
        fail(404, "Gudang tidak ditemukan.")
    existing = {c for (c,) in db.execute(select(Locator.code).where(Locator.warehouse_id == body.warehouse_id))}
    n = 0
    for z in body.zones:
        z = z.strip().upper()[:5]
        for r in range(1, body.racks + 1):
            for lv in range(1, body.levels + 1):
                code = f"{z}-{r:02d}-{lv:02d}"
                if code in existing:
                    continue
                db.add(Locator(warehouse_id=body.warehouse_id, code=code, zone=z, rack=f"{r:02d}", level=f"{lv:02d}",
                               verification_status="APPROVED", created_by=me.id, verified_by=me.id, verified_at=now()))
                n += 1
    audit(db, me, "MASTER_CREATE", "locator", None, None, {"generated": n, "warehouse_id": body.warehouse_id}, request)
    db.commit()
    return {"created": n}


# ============================================================ items
class ItemIn(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    group_code: str | None = Field(default=None, max_length=30)
    group_name: str | None = Field(default=None, max_length=120)
    uom: str = Field(min_length=1, max_length=15)
    qr_code: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=60)
    warehouse_ids: list[int] = []
    active: bool = True


def _item(i: Item, names: dict[int, str] | None = None):
    d = {
        "id": i.id,
        "code": i.code,
        "name": i.name,
        "group_code": i.group_code,
        "group_name": i.group_name,
        "uom": i.uom,
        "qr_code": i.qr_code,
        "barcode": i.barcode,
        "active": i.active,
        "verification_status": getattr(i, "verification_status", "APPROVED") or "APPROVED",
        "created_by": i.created_by,
        "verified_by": i.verified_by,
        "verified_at": i.verified_at.isoformat() if i.verified_at else None,
        "verification_note": i.verification_note,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "warehouse_ids": [w.warehouse_id for w in i.warehouses],
    }
    if names is not None:
        d["created_by_name"] = names.get(i.created_by)
        d["verified_by_name"] = names.get(i.verified_by)
    return d


def item_query(q: str, warehouse_id: int | None, active_only: bool, verification_status: str = ""):
    stmt = select(Item)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Item.code.like(like), Item.name.like(like), Item.barcode.like(like)))
    if warehouse_id:
        elig = select(ItemWarehouse.item_id).where(ItemWarehouse.warehouse_id == warehouse_id)
        any_elig = select(ItemWarehouse.item_id)
        stmt = stmt.where(or_(Item.id.in_(elig), ~Item.id.in_(any_elig)))
    if verification_status:
        stmt = stmt.where(Item.verification_status == verification_status.upper())
    if active_only:
        stmt = stmt.where(Item.active == True)  # noqa
    return stmt


@router.get("/items")
def list_items(q: str = "", warehouse_id: int | None = None, active_only: bool = False,
               verification_status: str = "", page: int = 1, size: int = 20,
               db: Session = Depends(get_db), _=ANY):
    stmt = item_query(q.strip(), warehouse_id, active_only, verification_status)
    rows, total = paged(db, stmt, select(func.count()).select_from(stmt.subquery()), page, size, [Item.code])
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    return {"items": [_item(i, names) for i in rows], "total": total}


@router.get("/items/lookup")
def lookup_item(code: str, warehouse_id: int | None = None, db: Session = Depends(get_db), _=ANY):
    """Resolve a scanned QR / barcode / item code to an item.
    If the code exists in several UOMs, `variants` lists all of them so the client can let the user choose."""
    code = code.strip()
    for col in (Item.qr_code, Item.code, Item.barcode):
        found = db.scalars(select(Item).where(col == code, Item.active == True).order_by(Item.uom)).unique().all()  # noqa
        if warehouse_id:
            ok = [i for i in found if not i.warehouses or warehouse_id in {w.warehouse_id for w in i.warehouses}]
            if found and not ok:
                fail(422, f"Item {found[0].code} tidak terdaftar untuk gudang ini.")
            found = ok
        if found:
            out = _item(found[0])
            out["variants"] = [_item(i) for i in found] if len(found) > 1 else []
            return out
    fail(404, "QR tidak dikenali.")


@router.get("/items/export")
def export_items(fmt: str = "xlsx", db: Session = Depends(get_db), _=ADMIN):
    rows = db.scalars(select(Item).order_by(Item.code, Item.uom)).unique().all()
    return respond(fmt, "items", "Item Master", ["Item Code", "Item Name", "Group Code", "Group Name", "UOM",
                                                  "QR Code", "Barcode", "Verification", "Active"],
                   [[i.code, i.name, i.group_code, i.group_name, i.uom, i.qr_code, i.barcode,
                     getattr(i, "verification_status", "APPROVED"), "Y" if i.active else "N"] for i in rows])


def _validate_item(db, body: ItemIn, iid=None):
    code = body.code.strip().upper()
    uom = body.uom.strip().upper()
    if db.scalar(select(Item).where(Item.code == code, Item.uom == uom, Item.id != (iid or 0))):
        fail(409, f"Kode item {code} dengan UOM {uom} sudah ada.")
    qr = (body.qr_code or "").strip() or None
    if qr and db.scalar(select(Item).where(Item.qr_code == qr, Item.id != (iid or 0))):
        fail(409, "QR code sudah dipakai item lain.")
    return code, qr


def _apply_item(db, i: Item, body: ItemIn, code, qr):
    i.code, i.name, i.uom = code, body.name.strip(), body.uom.strip().upper()
    i.group_code, i.group_name, i.qr_code = body.group_code, body.group_name, qr
    i.barcode, i.active = (body.barcode or "").strip() or None, body.active
    i.warehouses.clear()
    db.flush()
    for wid in dict.fromkeys(body.warehouse_ids):
        if db.get(Warehouse, wid):
            i.warehouses.append(ItemWarehouse(warehouse_id=wid))


@router.post("/items")
def create_item(body: ItemIn, request: Request, db: Session = Depends(get_db), me=ITEM_WRITE):
    code, qr = _validate_item(db, body)
    i = Item(code=code, name="", uom="", verification_status="APPROVED",
             created_by=me.id, verified_by=me.id, verified_at=now())
    db.add(i)
    db.flush()
    _apply_item(db, i, body, code, qr)
    audit(db, me, "MASTER_CREATE", "item", i.id, None, _item(i), request)
    db.commit()
    return _item(i)


@router.put("/items/{iid}")
def update_item(iid: int, body: ItemIn, request: Request, db: Session = Depends(get_db), me=ITEM_WRITE):
    i = db.get(Item, iid)
    if not i:
        fail(404, "Item tidak ditemukan.")
    code, qr = _validate_item(db, body, iid)
    old = _item(i)
    _apply_item(db, i, body, code, qr)
    if i.verification_status == "PENDING" and i.active and ({"ADMIN", "SUPERVISOR"} & set(me.roles)):
        i.verification_status = "APPROVED"
        i.verified_by = me.id
        i.verified_at = now()
    audit(db, me, "MASTER_UPDATE", "item", i.id, old, _item(i), request)
    db.commit()
    return _item(i)


@router.delete("/items/{iid}")
def delete_item(iid: int, request: Request, db: Session = Depends(get_db), me=ITEM_WRITE):
    i = db.get(Item, iid)
    if not i:
        fail(404, "Item tidak ditemukan.")
    if db.scalar(select(StockCountDetail.id).where(StockCountDetail.item_id == iid).limit(1)):
        fail(409, f"Item {i.code} ({i.uom}) sudah memiliki riwayat hitungan fisik STO dan tidak dapat dihapus. Anda dapat menonaktifkannya.")
    if db.scalar(select(StockMovement.id).where(StockMovement.item_id == iid).limit(1)):
        fail(409, f"Item {i.code} ({i.uom}) sudah memiliki riwayat pergerakan stok dan tidak dapat dihapus. Anda dapat menonaktifkannya.")
    audit(db, me, "MASTER_DELETE", "item", i.id, _item(i), None, request)
    db.delete(i)
    db.commit()
    return {"ok": True}

