"""Excel import: upload -> validate -> preview (nothing written) -> commit / cancel.

Master-data only: ITEM | WAREHOUSE | LOCATOR | USER.
"""
import io
import re

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from openpyxl import load_workbook
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config
from ..core import audit, fail, hash_password, require
from ..database import get_db
from ..models import (ROLES, ExcelImport, ExcelImportError, Item, Locator, Role, User, UserRole, Warehouse, now)
from ..services.export import make_xlsx, page_params, respond

router = APIRouter(prefix="/api/imports", tags=["imports"])
IMPORTER = Depends(require("ADMIN"))
KINDS = ("ITEM", "WAREHOUSE", "LOCATOR", "USER")

ITEM_SYNONYMS = {"item code": "code", "code": "code", "item original": "code", "item": "code",
                 "item name": "name", "name": "name",
                 "group code": "group_code", "item group code": "group_code", "group name": "group_name",
                 "item group name": "group_name", "uom": "uom", "unit": "uom", "qr code": "qr", "qr": "qr",
                 "barcode": "barcode", "active": "active", "warehouse": "warehouse"}
WAREHOUSE_SYNONYMS = {
    "kode gudang": "code", "code": "code", "warehouse code": "code", "wh code": "code", "wh": "code", "gudang": "code",
    "nama gudang": "name", "name": "name", "warehouse name": "name", "nama": "name",
    "tipe": "type", "type": "type", "tipe gudang": "type",
    "active": "active", "aktif": "active", "status": "active",
}
LOCATOR_SYNONYMS = {
    "warehouse code": "wh", "wh code": "wh", "wh": "wh", "warehouse": "wh", "gudang": "wh", "kode gudang": "wh",
    "locator code": "code", "kode locator": "code", "code": "code", "locator": "code", "loc": "code",
    "zone": "zone", "zona": "zone",
    "rack": "rack", "rak": "rack",
    "level": "level", "tingkat": "level",
    "active": "active", "aktif": "active", "status": "active",
}
USER_SYNONYMS = {
    "username": "username", "user": "username", "nama user": "username",
    "full name": "full_name", "nama lengkap": "full_name", "name": "full_name", "nama": "full_name",
    "password": "password", "pass": "password", "kata sandi": "password",
    "roles": "roles", "role": "roles", "peran": "roles",
    "active": "active", "aktif": "active", "status": "active",
}


# ------------------------------------------------------------------ file handling
def read_sheet(raw: bytes, filename: str) -> list[list]:
    if not filename.lower().endswith(".xlsx"):
        fail(422, "Format file tidak didukung. Gunakan file Excel .xlsx.")
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        fail(413, f"Ukuran file melebihi batas {config.MAX_UPLOAD_MB} MB.")
    if not raw[:2] == b"PK":
        fail(422, "File bukan Excel .xlsx yang valid.")
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = []
        for idx, r in enumerate(ws.iter_rows(values_only=True)):
            if idx > 100_000:
                fail(422, "File Excel melebihi batas maksimum 100.000 baris.")
            rows.append(list(r))
        wb.close()
    except Exception:
        fail(422, "File Excel tidak dapat dibaca. Pastikan file tidak rusak atau diproteksi password.")
    if not rows:
        fail(422, "File Excel kosong.")
    return rows


def norm_header(h) -> str:
    return re.sub(r"\s+", " ", str(h or "").strip().lower())


def find_header(rows: list[list], syn: dict, required: set[str]):
    """Locate header row (first 15 rows) and return (row_index, {field: col_idx})."""
    for ri, row in enumerate(rows[:15]):
        cols = {}
        for ci, h in enumerate(row):
            key = norm_header(h)
            if key in syn and syn[key] not in cols:
                cols[syn[key]] = ci
        if required <= set(cols):
            return ri, cols
    return None, None


def cell(row, idx):
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    if isinstance(v, str):
        v = v.strip()
    return None if v == "" else v


def code_of(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return str(v).strip().upper()


class Collector:
    def __init__(self):
        self.errors: list[tuple] = []
        self.err_rows: set[int] = set()
        self.warn_rows: set[int] = set()

    def err(self, row, col, msg):
        self.errors.append((row, "ERROR", col, msg))
        self.err_rows.add(row)

    def warn(self, row, col, msg):
        self.errors.append((row, "WARNING", col, msg))
        self.warn_rows.add(row)


# ------------------------------------------------------------------ parsers
def parse_items(db, rows, col: Collector):
    ri, cols = find_header(rows, ITEM_SYNONYMS, {"code", "name", "uom"})
    if ri is None:
        fail(422, "Kolom wajib tidak ditemukan. Dibutuhkan: Item Code / Item Original, Item Name, UOM / Unit.")
    existing_qr = {i.qr_code: (i.code, i.uom) for i in db.scalars(select(Item)).unique() if i.qr_code}
    seen_key, seen_qr, parsed, total_rows = set(), set(), [], 0
    for i, row in enumerate(rows[ri + 1:], start=ri + 2):
        if all(v in (None, "") for v in row):
            continue
        total_rows += 1
        code, name, uom = code_of(cell(row, cols["code"])), cell(row, cols["name"]), code_of(cell(row, cols["uom"]))
        qr = cell(row, cols.get("qr"))
        qr = str(qr).strip() if qr is not None else None
        ok = True
        if not code or len(code) > 60:
            col.err(i, "Item Code", "Item code kosong/terlalu panjang."); ok = False
        if not name:
            col.err(i, "Item Name", "Nama item kosong."); ok = False
        if not uom or len(uom) > 15:
            col.err(i, "UOM", "UOM kosong/tidak valid."); ok = False
        if (code, uom) in seen_key:
            col.err(i, "Item Code", "Kode item + UOM duplikat di file."); ok = False
        if qr and (qr in seen_qr or existing_qr.get(qr, (code, uom)) != (code, uom)):
            col.err(i, "QR Code", "QR code sudah dipakai item lain."); ok = False
        if ok:
            seen_key.add((code, uom))
            if qr:
                seen_qr.add(qr)
            act = str(cell(row, cols.get("active")) or "Y").strip().upper()
            parsed.append({"row": i, "code": code, "name": str(name)[:200], "uom": uom,
                           "group_code": str(cell(row, cols.get("group_code")) or "") or None,
                           "group_name": str(cell(row, cols.get("group_name")) or "") or None,
                           "qr": qr, "barcode": str(cell(row, cols.get("barcode")) or "") or None,
                           "active": act not in ("N", "NO", "0", "FALSE")})
    return total_rows, parsed


def parse_warehouses(db, rows, col: Collector):
    ri, cols = find_header(rows, WAREHOUSE_SYNONYMS, {"code", "name"})
    if ri is None:
        fail(422, "Kolom wajib tidak ditemukan. Dibutuhkan: Kode Gudang, Nama Gudang.")
    seen_code, parsed, total_rows = set(), [], 0
    for i, row in enumerate(rows[ri + 1:], start=ri + 2):
        if all(v in (None, "") for v in row):
            continue
        total_rows += 1
        code, name = code_of(cell(row, cols["code"])), cell(row, cols["name"])
        typ = str(cell(row, cols.get("type")) or "FG").strip().upper()[:40]
        act = str(cell(row, cols.get("active")) or "Y").strip().upper()
        ok = True
        if not code or len(code) > 20:
            col.err(i, "Kode Gudang", "Kode gudang kosong atau melebihi 20 karakter."); ok = False
        if not name:
            col.err(i, "Nama Gudang", "Nama gudang kosong."); ok = False
        if code in seen_code:
            col.err(i, "Kode Gudang", f"Kode gudang '{code}' duplikat di file."); ok = False
        if ok:
            seen_code.add(code)
            parsed.append({"row": i, "code": code, "name": str(name)[:120], "type": typ,
                           "active": act not in ("N", "NO", "0", "FALSE")})
    return total_rows, parsed


def parse_locators(db, rows, col: Collector):
    ri, cols = find_header(rows, LOCATOR_SYNONYMS, {"wh", "code"})
    if ri is None:
        fail(422, "Kolom wajib tidak ditemukan. Dibutuhkan: Warehouse Code, Locator Code.")
    wh_map = {w.code: w for w in db.scalars(select(Warehouse))}
    seen_key, parsed, total_rows = set(), [], 0
    for i, row in enumerate(rows[ri + 1:], start=ri + 2):
        if all(v in (None, "") for v in row):
            continue
        total_rows += 1
        wh, code = code_of(cell(row, cols["wh"])), code_of(cell(row, cols["code"]))
        z = code_of(cell(row, cols.get("zone"))) or None
        r = code_of(cell(row, cols.get("rack"))) or None
        lv = code_of(cell(row, cols.get("level"))) or None
        act = str(cell(row, cols.get("active")) or "Y").strip().upper()
        ok = True
        if not wh or wh not in wh_map:
            col.err(i, "Warehouse", f"Gudang '{wh}' tidak ditemukan di sistem."); ok = False
        if not code or len(code) > 40:
            col.err(i, "Locator Code", "Kode locator kosong atau melebihi 40 karakter."); ok = False
        if (wh, code) in seen_key:
            col.err(i, "Locator Code", f"Locator '{code}' duplikat untuk gudang {wh} di file."); ok = False
        if ok:
            seen_key.add((wh, code))
            parsed.append({"row": i, "warehouse_id": wh_map[wh].id, "warehouse_code": wh,
                           "code": code, "zone": z[:20] if z else None, "rack": r[:20] if r else None,
                           "level": lv[:20] if lv else None, "active": act not in ("N", "NO", "0", "FALSE")})
    return total_rows, parsed


def parse_users(db, rows, col: Collector):
    ri, cols = find_header(rows, USER_SYNONYMS, {"username", "full_name", "roles"})
    if ri is None:
        fail(422, "Kolom wajib tidak ditemukan. Dibutuhkan: Username, Nama Lengkap, Roles.")
    existing_users = {u.username: u for u in db.scalars(select(User))}
    seen_user, parsed, total_rows = set(), [], 0
    for i, row in enumerate(rows[ri + 1:], start=ri + 2):
        if all(v in (None, "") for v in row):
            continue
        total_rows += 1
        uname = str(cell(row, cols["username"]) or "").strip().lower()
        full = cell(row, cols["full_name"])
        pwd = str(cell(row, cols.get("password")) or "").strip()
        raw_roles = str(cell(row, cols["roles"]) or "").strip().upper()
        roles_list = [x.strip() for x in re.split(r"[,;|/ ]+", raw_roles) if x.strip()]
        act = str(cell(row, cols.get("active")) or "Y").strip().upper()
        ok = True
        if not uname or len(uname) < 3 or len(uname) > 50 or not re.match(r"^[A-Za-z0-9_.-]+$", uname):
            col.err(i, "Username", "Username tidak valid (min 3 karakter alfanumerik / _.-)."); ok = False
        if not full:
            col.err(i, "Full Name", "Nama lengkap kosong."); ok = False
        if uname in seen_user:
            col.err(i, "Username", f"Username '{uname}' duplikat di file."); ok = False
        if not roles_list:
            col.err(i, "Roles", "Role kosong."); ok = False
        else:
            invalid_roles = [r for r in roles_list if r not in ROLES]
            if invalid_roles:
                col.err(i, "Roles", f"Role tidak dikenal: {', '.join(invalid_roles)}. Role yang valid: {', '.join(ROLES)}"); ok = False
        is_new = uname not in existing_users
        if is_new and (not pwd or len(pwd) < 6):
            col.err(i, "Password", "Password wajib diisi minimal 6 karakter untuk akun baru."); ok = False
        if ok:
            seen_user.add(uname)
            parsed.append({"row": i, "username": uname, "full_name": str(full)[:120],
                           "password": pwd if pwd else None, "roles": roles_list,
                           "active": act not in ("N", "NO", "0", "FALSE")})
    return total_rows, parsed


# ------------------------------------------------------------------ endpoints
def _summary(imp: ExcelImport):
    return {"id": imp.id, "kind": imp.kind, "filename": imp.filename, "sto_id": imp.sto_id, "status": imp.status,
            "total_rows": imp.total_rows, "valid_rows": imp.valid_rows, "warning_rows": imp.warning_rows,
            "error_rows": imp.error_rows, "created_at": imp.created_at.isoformat(),
            "committed_at": imp.committed_at.isoformat() if imp.committed_at else None}


@router.post("/upload")
async def upload(request: Request, kind: str = Form(...), file: UploadFile = File(...),
                 db: Session = Depends(get_db), me: User = IMPORTER):
    kind = kind.upper()
    if kind not in KINDS:
        fail(422, "Jenis import tidak valid.")
    raw = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    rows = read_sheet(raw, file.filename or "upload.xlsx")
    col = Collector()
    if kind == "WAREHOUSE":
        total, parsed = parse_warehouses(db, rows, col)
    elif kind == "LOCATOR":
        total, parsed = parse_locators(db, rows, col)
    elif kind == "USER":
        total, parsed = parse_users(db, rows, col)
    else:
        total, parsed = parse_items(db, rows, col)
    imp = ExcelImport(kind=kind, filename=(file.filename or "upload.xlsx")[:255], uploaded_by=me.id,
                      total_rows=total, valid_rows=len(parsed),
                      warning_rows=len(col.warn_rows - col.err_rows), error_rows=len(col.err_rows),
                      options={}, parsed=parsed)
    db.add(imp)
    db.flush()
    for r, sev, c, msg in col.errors[:5000]:
        db.add(ExcelImportError(import_id=imp.id, row_no=r, severity=sev, column_name=c, message=msg))
    audit(db, me, "IMPORT_EXCEL_UPLOAD", "excel_import", imp.id, None,
          {"kind": kind, "file": imp.filename, "rows": total, "errors": imp.error_rows}, request)
    db.commit()
    return _summary(imp)


@router.get("")
def history(kind: str = "", page: int = 1, size: int = 20, db: Session = Depends(get_db), _=IMPORTER):
    stmt = select(ExcelImport)
    if kind:
        stmt = stmt.where(ExcelImport.kind == kind.upper())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, lim = page_params(page, size)
    rows = db.scalars(stmt.order_by(ExcelImport.id.desc()).offset(off).limit(lim)).all()
    return {"items": [_summary(r) for r in rows], "total": total}


def _get(db, iid) -> ExcelImport:
    imp = db.get(ExcelImport, iid)
    if not imp:
        fail(404, "Data import tidak ditemukan.")
    return imp


@router.get("/template/{kind}")
def template(kind: str, _=IMPORTER):
    kind = kind.upper()
    if kind == "WAREHOUSE":
        h, r = ["Kode Gudang", "Nama Gudang", "Tipe", "Status"], [["L21", "PP2 WH FG", "FG", "Y"]]
    elif kind == "LOCATOR":
        h, r = ["Kode Gudang", "Kode Locator", "Zona", "Rak", "Level", "Status"], [["L21", "A-01-01", "ZONE-A", "R01", "L01", "Y"]]
    elif kind == "USER":
        h, r = ["Username", "Nama Lengkap", "Password", "Roles", "Status"], [["mh1", "Hitung 1", "Password123", "MH", "Y"]]
    elif kind == "ITEM":
        h, r = ["Item Code", "Item Name", "Group Code", "Group Name", "UOM", "QR Code", "Barcode", "Active"], \
               [["M10813-0910", "IC PTMI ANNIVERSARY DOLL", "500DM", "Inventory - Finished Goods", "PCS", "", "", "Y"]]
    else:
        fail(422, "Jenis template tidak valid.")
    return Response(make_xlsx(h, r, "Template"), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="template_{kind.lower()}.xlsx"'})


@router.get("/{iid}")
def get_import(iid: int, db: Session = Depends(get_db), _=IMPORTER):
    return _summary(_get(db, iid))


@router.get("/{iid}/errors")
def errors(iid: int, severity: str = "", page: int = 1, size: int = 50, db: Session = Depends(get_db), _=IMPORTER):
    _get(db, iid)
    stmt = select(ExcelImportError).where(ExcelImportError.import_id == iid)
    if severity:
        stmt = stmt.where(ExcelImportError.severity == severity.upper())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, lim = page_params(page, size)
    rows = db.scalars(stmt.order_by(ExcelImportError.row_no).offset(off).limit(lim)).all()
    return {"items": [{"row": e.row_no, "severity": e.severity, "column": e.column_name, "message": e.message}
                      for e in rows], "total": total}


@router.get("/{iid}/errors/export")
def errors_export(iid: int, fmt: str = "xlsx", db: Session = Depends(get_db), _=IMPORTER):
    imp = _get(db, iid)
    rows = db.scalars(select(ExcelImportError).where(ExcelImportError.import_id == iid)
                      .order_by(ExcelImportError.row_no)).all()
    return respond(fmt, f"import_errors_{iid}", f"Import Errors - {imp.filename}",
                   ["Row", "Severity", "Column", "Message"], [[e.row_no, e.severity, e.column_name, e.message] for e in rows])


@router.post("/{iid}/cancel")
def cancel(iid: int, request: Request, db: Session = Depends(get_db), me: User = IMPORTER):
    imp = _get(db, iid)
    if imp.status != "PREVIEW":
        fail(409, "Import sudah diproses.")
    imp.status, imp.parsed = "CANCELLED", None
    audit(db, me, "IMPORT_CANCEL", "excel_import", imp.id, None, None, request)
    db.commit()
    return _summary(imp)


@router.post("/{iid}/commit")
def commit(iid: int, request: Request, db: Session = Depends(get_db), me: User = IMPORTER):
    imp = _get(db, iid)
    if imp.status != "PREVIEW":
        fail(409, "Import sudah diproses atau dibatalkan.")
    if not imp.parsed:
        fail(422, "Tidak ada baris valid untuk diimport.")
    if imp.kind == "WAREHOUSE":
        _commit_warehouses(db, imp)
    elif imp.kind == "LOCATOR":
        _commit_locators(db, imp)
    elif imp.kind == "USER":
        _commit_users(db, imp)
    else:
        _commit_items(db, imp)
    imp.status, imp.committed_at = "COMMITTED", now()
    audit(db, me, "IMPORT_EXCEL", "excel_import", imp.id, None,
          {"kind": imp.kind, "rows": imp.valid_rows, "file": imp.filename}, request)
    imp.parsed = None
    db.commit()
    return _summary(imp)


def _commit_items(db: Session, imp: ExcelImport):
    existing = {(i.code, i.uom): i for i in db.scalars(select(Item)).unique()}
    for r in imp.parsed:
        i = existing.get((r["code"], r["uom"]))
        if not i:
            i = Item(code=r["code"], name=r["name"], uom=r["uom"])
            db.add(i)
        i.name, i.group_code, i.group_name = r["name"], r["group_code"], r["group_name"]
        i.qr_code, i.barcode, i.active = r["qr"], r["barcode"], r["active"]


def _commit_warehouses(db: Session, imp: ExcelImport):
    existing = {w.code.upper(): w for w in db.scalars(select(Warehouse)).all()}
    for r in imp.parsed:
        code = r["code"].upper()
        w = existing.get(code)
        if not w:
            w = Warehouse(code=code, name=r["name"], type=r.get("type", "FG"), active=r.get("active", True))
            db.add(w)
            existing[code] = w
        else:
            w.name = r["name"]
            w.type = r.get("type", w.type)
            w.active = r.get("active", w.active)


def _commit_locators(db: Session, imp: ExcelImport):
    wh_map = {w.code.upper(): w.id for w in db.scalars(select(Warehouse)).all()}
    existing = {(loc.warehouse_id, loc.code.upper()): loc for loc in db.scalars(select(Locator)).all()}
    for r in imp.parsed:
        wh_code = r["warehouse_code"].upper()
        wh_id = r.get("warehouse_id") or wh_map.get(wh_code)
        if not wh_id:
            continue
        code = r["code"].upper()
        key = (wh_id, code)
        loc = existing.get(key)
        if not loc:
            loc = Locator(warehouse_id=wh_id, code=code, zone=r.get("zone"),
                          rack=r.get("rack"), level=r.get("level"), active=r.get("active", True))
            db.add(loc)
            existing[key] = loc
        else:
            loc.zone = r.get("zone")
            loc.rack = r.get("rack")
            loc.level = r.get("level")
            loc.active = r.get("active", True)


def _commit_users(db: Session, imp: ExcelImport):
    all_roles = {r.code: r for r in db.scalars(select(Role)).all()}
    existing = {u.username.lower(): u for u in db.scalars(select(User)).all()}
    for r in imp.parsed:
        uname = r["username"].lower()
        u = existing.get(uname)
        if not u:
            pwd = r.get("password") or "sto12345"
            u = User(username=uname, full_name=r["full_name"], password_hash=hash_password(pwd),
                     active=r["active"], deleted=False)
            db.add(u)
            db.flush()
            existing[uname] = u
        else:
            u.full_name = r["full_name"]
            u.active = r["active"]
            u.deleted = False
            if r.get("password"):
                u.password_hash = hash_password(r["password"])
        if r.get("roles"):
            db.execute(delete(UserRole).where(UserRole.user_id == u.id))
            for role_name in r["roles"]:
                role_obj = all_roles.get(role_name.upper())
                if role_obj:
                    db.add(UserRole(user_id=u.id, role_id=role_obj.id))
