"""Demo / initial data. Safe to call repeatedly (only seeds an empty database)."""
import csv
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from .core import hash_password
from .models import ROLES, Item, Locator, Message, Role, User, UserRole, Warehouse
from .services import stock as svc

DEMO_PASSWORD = "demo1234"
ROLE_NAMES = {"ADMIN": "Administrator", "SUPERVISOR": "Supervisor", "CHECKER": "Checker", "MH": "Material Handling"}

USERS = [  # username, full name, roles
    ("admin", "Administrator", ["ADMIN"]),
    ("supervisor01", "Sari Supervisor", ["SUPERVISOR"]),
    ("checker01", "Citra Checker", ["CHECKER"]),
    ("mh01", "Budi Material Handling", ["MH"]),
    ("mh02", "Dewi Material Handling", ["MH"]),
]

# Real item master for warehouse L21 (source: "L21 STO.xlsx"). Columns: wh, code, name, group_code, group_name, uom.
# One item code may appear with several UOMs (e.g. MCBX50-0910 as PCS and SHT) -> one Item row per code+UOM.
ITEMS_CSV = Path(__file__).resolve().parent / "data" / "items_l21.csv"


def load_items(db: Session) -> dict:
    """Bulk insert the item master from ITEMS_CSV. Returns {(code, uom): item_id}."""
    rows, seen = [], set()
    with open(ITEMS_CSV, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            code, uom = r["code"].strip().upper(), r["uom"].strip().upper()
            if not code or not uom or (code, uom) in seen:
                continue
            seen.add((code, uom))
            rows.append({"code": code[:60], "name": (r["name"].strip() or code)[:200], "uom": uom[:15],
                         "group_code": r["group_code"].strip()[:30] or None,
                         "group_name": r["group_name"].strip()[:120] or None, "active": True})
    for n in range(0, len(rows), 2000):
        db.execute(insert(Item), rows[n:n + 2000])
    db.flush()
    return {(c, u): i for i, c, u in db.execute(select(Item.id, Item.code, Item.uom))}


def seed(db: Session):
    if db.scalar(select(Role).limit(1)):
        return
    roles = {c: Role(code=c, name=ROLE_NAMES[c]) for c in ROLES}
    db.add_all(roles.values())
    db.flush()
    users = {}
    for uname, full, rs in USERS:
        u = User(username=uname, full_name=full, password_hash=hash_password(DEMO_PASSWORD))
        db.add(u)
        db.flush()
        for r in rs:
            u.user_roles.append(UserRole(role=roles[r]))
        users[uname] = u

    whs = {}
    for code, name, typ in [("L21", "PP2 WH FG", "FG"), ("L22", "FG Hasbro", "FG"), ("L25", "Raw Material", "RM")]:
        w = Warehouse(code=code, name=name, type=typ)
        db.add(w)
        db.flush()
        whs[code] = w

    def make_locs(wh, zones, racks, levels):
        out = []
        for z in zones:
            for r in range(1, racks + 1):
                for lv in range(1, levels + 1):
                    l = Locator(warehouse_id=wh.id, code=f"{z}-{r:02d}-{lv:02d}", zone=z, rack=f"{r:02d}", level=f"{lv:02d}")
                    db.add(l)
                    out.append(l)
        db.flush()
        return out

    locs = {"L21": make_locs(whs["L21"], "A", 5, 20), "L22": make_locs(whs["L22"], "A", 2, 10),
            "L25": make_locs(whs["L25"], "A", 1, 10)}

    items = load_items(db)  # {(code, uom): item_id}; no warehouse restriction -> eligible everywhere

    # Demo stock: a few inbound / transfer / outbound movements so balances exist from the start.
    FG = ["M10813-0910", "M10813-0980", "M10814-0910", "M10814-0980"]
    MAT = ["M11009-59910", "MCHY01-09BD1"]

    def code_key(code):
        return items.get((code, "PCS")) or items.get((code, "SHT"))

    def move(mtype, wh_code, code, qty, from_loc=None, to_loc=None, ref_type=None, ref_no=None):
        item_id = code_key(code)
        if not item_id:
            return
        svc.create_movement(db, users["admin"], movement_type=mtype, warehouse_id=whs[wh_code].id, item_id=item_id,
                            qty=qty, from_locator_id=from_loc.id if from_loc else None,
                            to_locator_id=to_loc.id if to_loc else None, ref_type=ref_type, ref_no=ref_no)

    l21 = locs["L21"]
    move("INBOUND", "L21", FG[0], 120, to_loc=l21[0], ref_type="PO", ref_no="PO-2026-0001")
    move("INBOUND", "L21", FG[1], 45, to_loc=l21[0], ref_type="PO", ref_no="PO-2026-0001")
    move("INBOUND", "L21", FG[2], 80, to_loc=l21[1], ref_type="PO", ref_no="PO-2026-0002")
    move("INBOUND", "L21", FG[3], 60, to_loc=l21[2], ref_type="SURAT_JALAN", ref_no="SJ-2026-0007")
    move("TRANSFER", "L21", FG[0], 30, from_loc=l21[0], to_loc=l21[1])
    move("OUTBOUND", "L21", FG[1], 20, from_loc=l21[0], ref_type="DO", ref_no="DO-2026-0011")
    move("INBOUND", "L25", MAT[0], 200, to_loc=locs["L25"][0], ref_type="PO", ref_no="PO-2026-0003")
    move("INBOUND", "L25", MAT[1], 150, to_loc=locs["L25"][1], ref_type="PO", ref_no="PO-2026-0003")

    # Demo announcements so the operator dashboard has messages from the start.
    for title, body, level, target, sender in [
        ("Selamat datang", "Gunakan menu Scan untuk transaksi barang masuk, keluar, dan pindah. "
         "Pastikan lokator dan jumlah sesuai sebelum disimpan.", "INFO", "ALL", "admin"),
        ("Ingat cek lokator", "Cocokkan kode lokator dengan label fisik sebelum menyimpan transaksi.", "WARN", "MH", "supervisor01"),
    ]:
        db.add(Message(sender_id=users[sender].id, title=title, body=body, level=level, target_role=target))
    db.commit()
