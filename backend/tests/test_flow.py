"""End-to-end API test for the daily WMS flow (inbound / outbound / transfer).
Run:  cd backend && python -m pytest -q   (or: python tests/test_flow.py)
Uses a throw-away SQLite database.
"""
import io
import os
import sys
import tempfile
import uuid
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["LOG_FILE"] = str(Path(_tmp) / "err.log")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import Workbook  # noqa: E402

from app.main import app  # noqa: E402


def login(c, user):
    r = c.post("/api/auth/login", json={"username": user, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def balance(c, hdr, wh_id, loc_id, item_id):
    r = c.get(f"/api/m/stock?warehouse_id={wh_id}&locator_id={loc_id}&item_id={item_id}", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["items"][0]["qty"] if r.json()["items"] else 0


def test_full_flow():
    with TestClient(app) as c:
        # bad login + RBAC
        assert c.post("/api/auth/login", json={"username": "mh01", "password": "x"}).status_code == 401
        mh, chk, sup, adm = login(c, "mh01"), login(c, "checker01"), login(c, "supervisor01"), login(c, "admin")
        assert c.get("/api/users", headers=mh).status_code == 403
        assert c.get("/api/movements", headers=mh).status_code == 403
        assert c.get("/api/movements", headers=sup).status_code == 200
        assert c.post("/api/warehouses", json={"code": "ZZ"}, headers=sup).status_code == 403

        cfg = c.get("/api/auth/config").json()
        assert cfg["app_name"] and "demo_mode" in cfg

        # bundle: warehouses, locators, items
        whs = c.get("/api/warehouses", headers=mh).json()["items"]
        wh = {w["code"]: w for w in whs}["L21"]
        bundle = c.get(f"/api/m/bundle?warehouse_id={wh['id']}&include_items=false", headers=mh).json()
        assert bundle["locators"]
        locs = {l["code"]: l for l in bundle["locators"]}
        a1, a2 = locs["A-01-01"], locs["A-01-02"]

        fg0 = c.get("/api/items/lookup?code=M10813-0910", headers=mh).json()
        fg1 = c.get("/api/items/lookup?code=M10813-0980", headers=mh).json()
        assert c.get("/api/items/lookup?code=NOPE", headers=mh).status_code == 404
        assert c.get("/api/items?size=1", headers=adm).json()["total"] > 20000

        # seeded balances
        assert balance(c, mh, wh["id"], a1["id"], fg0["id"]) == 90
        assert balance(c, mh, wh["id"], a1["id"], fg1["id"]) == 25

        # inbound + idempotency
        t1 = uuid.uuid4().hex
        r = c.post("/api/m/inbound", json={"warehouse_id": wh["id"], "item_id": fg0["id"], "qty": 10,
                                           "to_locator_id": a1["id"], "ref_type": "PO", "ref_no": "PO-1",
                                           "txn_id": t1}, headers=mh)
        assert r.status_code == 200, r.text
        assert balance(c, mh, wh["id"], a1["id"], fg0["id"]) == 100
        r = c.post("/api/m/inbound", json={"warehouse_id": wh["id"], "item_id": fg0["id"], "qty": 10,
                                           "to_locator_id": a1["id"], "txn_id": t1}, headers=mh)
        assert r.json()["duplicate"] and balance(c, mh, wh["id"], a1["id"], fg0["id"]) == 100

        # outbound insufficient -> rejected
        assert c.post("/api/m/outbound", json={"warehouse_id": wh["id"], "item_id": fg1["id"], "qty": 999,
                                               "from_locator_id": a1["id"]}, headers=mh).status_code == 409
        # outbound ok
        assert c.post("/api/m/outbound", json={"warehouse_id": wh["id"], "item_id": fg1["id"], "qty": 5,
                                               "from_locator_id": a1["id"]}, headers=mh).status_code == 200
        assert balance(c, mh, wh["id"], a1["id"], fg1["id"]) == 20

        # transfer
        assert c.post("/api/m/transfer", json={"warehouse_id": wh["id"], "item_id": fg0["id"], "qty": 5,
                                               "from_locator_id": a1["id"], "to_locator_id": a2["id"]}, headers=mh).status_code == 200
        assert balance(c, mh, wh["id"], a1["id"], fg0["id"]) == 95
        assert balance(c, mh, wh["id"], a2["id"], fg0["id"]) == 35
        # same locator transfer invalid
        assert c.post("/api/m/transfer", json={"warehouse_id": wh["id"], "item_id": fg0["id"], "qty": 1,
                                               "from_locator_id": a1["id"], "to_locator_id": a1["id"]}, headers=mh).status_code == 422

        # movement history + void (correction)
        mv = c.get(f"/api/movements?warehouse_id={wh['id']}&movement_type=INBOUND", headers=chk).json()
        assert mv["total"] >= 1
        first = mv["items"][0]
        assert c.post(f"/api/movements/{first['id']}/void", json={"reason": "x"}, headers=chk).status_code == 422
        assert c.post(f"/api/movements/{first['id']}/void", json={"reason": "Salah input"}, headers=chk).json()["voided"] is True
        assert c.post(f"/api/movements/{first['id']}/void", json={"reason": "lagi"}, headers=chk).status_code == 409
        # mh cannot void
        assert c.post(f"/api/movements/{first['id']}/void", json={"reason": "nope"}, headers=mh).status_code == 403

        # void that would make balance negative is rejected (seed inbound 120 of fg0)
        all_mv = c.get(f"/api/movements?warehouse_id={wh['id']}&movement_type=INBOUND&size=100", headers=chk).json()["items"]
        seed_in = [m for m in all_mv if m["code"] == "M10813-0910" and m["qty"] == 120 and not m["voided"]]
        if seed_in:
            assert c.post(f"/api/movements/{seed_in[0]['id']}/void", json={"reason": "coba"}, headers=chk).status_code == 409

        # adjustment (add / remove)
        before = balance(c, mh, wh["id"], a1["id"], fg0["id"])
        r = c.post("/api/movements/adjust", json={"warehouse_id": wh["id"], "item_id": fg0["id"], "locator_id": a1["id"],
                                                  "qty": 7, "direction": "ADD", "reason": "Koreksi opname"}, headers=chk)
        assert r.status_code == 200 and r.json()["movement_type"] == "ADJUSTMENT"
        assert balance(c, mh, wh["id"], a1["id"], fg0["id"]) == before + 7
        assert c.post("/api/movements/adjust", json={"warehouse_id": wh["id"], "item_id": fg0["id"], "locator_id": a1["id"],
                                                     "qty": 9999, "direction": "REMOVE", "reason": "Terlalu banyak"}, headers=chk).status_code == 409

        # offline sync: idempotent + rejected handling
        good = {"txn_id": uuid.uuid4().hex, "txn_type": "INBOUND", "device_id": "dev1", "timestamp": "2026-10-08T01:00:00Z",
                "payload": {"warehouse_id": wh["id"], "item_id": fg1["id"], "qty": 3, "to_locator_id": a2["id"]}}
        bad = {"txn_id": uuid.uuid4().hex, "txn_type": "OUTBOUND", "timestamp": "2026-10-08T02:00:00Z",
               "payload": {"warehouse_id": wh["id"], "item_id": fg1["id"], "qty": 99999, "from_locator_id": a2["id"]}}
        r = c.post("/api/m/sync", json={"transactions": [good, bad]}, headers=mh).json()
        assert [x["result"] for x in r["results"]] == ["OK", "REJECTED"]
        r = c.post("/api/m/sync", json={"transactions": [good]}, headers=mh).json()
        assert r["results"][0]["result"] == "DUPLICATE"
        problems = c.get("/api/sync-transactions?result=REJECTED", headers=chk).json()
        assert problems["total"] >= 1

        # stock list + export
        st = c.get(f"/api/stock?warehouse_id={wh['id']}", headers=sup).json()
        assert st["total"] >= 1
        assert c.get(f"/api/stock/export?fmt=xlsx&warehouse_id={wh['id']}", headers=sup).headers["content-type"].startswith("application/vnd")

        # dashboard
        dash = c.get(f"/api/dashboard?warehouse_id={wh['id']}", headers=sup).json()
        assert "inbound_period" in dash["cards"] and len(dash["chart"]) == 7 and dash["warehouses"]

        # reports (supervisor); audit_log admin only
        for name in ("stock_balance", "movement_history", "inbound", "outbound", "transfer", "corrections"):
            assert c.get(f"/api/reports/{name}", headers=sup).status_code == 200, name
        assert c.get("/api/reports/audit_log", headers=sup).status_code == 403
        assert c.get("/api/reports/audit_log", headers=adm).status_code == 200
        assert c.get("/api/reports/stock_balance?fmt=xlsx", headers=sup).headers["content-type"].startswith("application/vnd")
        assert c.get("/api/reports/movement_history?fmt=pdf", headers=sup).headers["content-type"] == "application/pdf"

        # master: admin creates warehouse + generate locators; duplicate rejected
        r = c.post("/api/warehouses", json={"code": "L99", "name": "Gudang Uji"}, headers=adm)
        assert r.status_code == 200 and r.json()["code"] == "L99"
        assert c.post("/api/warehouses", json={"code": "L99", "name": "Dup"}, headers=adm).status_code == 409
        wid = r.json()["id"]
        gen = c.post("/api/locators/generate", json={"warehouse_id": wid, "zones": ["A"], "racks": 2, "levels": 3}, headers=adm)
        assert gen.status_code == 200 and gen.json()["created"] == 6

        # master import: admin only
        item_rows = [["Item Code", "Item Name", "Group Code", "Group Name", "UOM", "QR Code", "Barcode", "Active"],
                     ["TEST-IMPORT-1", "Barang Uji", "G1", "Grup", "PCS", "", "", "Y"]]
        files = {"file": ("items.xlsx", xlsx(item_rows), "application/octet-stream")}
        assert c.post("/api/imports/upload", data={"kind": "ITEM"}, files=files, headers=sup).status_code == 403
        r = c.post("/api/imports/upload", data={"kind": "ITEM"}, files=files, headers=adm)
        assert r.status_code == 200, r.text
        imp = r.json()
        assert (imp["valid_rows"], imp["error_rows"]) == (1, 0)
        assert c.post(f"/api/imports/{imp['id']}/commit", headers=adm).status_code == 200
        assert c.get("/api/items/lookup?code=TEST-IMPORT-1", headers=adm).json()["code"] == "TEST-IMPORT-1"

        # --- Stock Opname (Fase 2): physical count vs ledger ---
        users = {u["username"]: u["id"] for u in c.get("/api/users?size=100", headers=adm).json()["items"]}
        assert c.post("/api/sto", json={"sto_number": "STO-DENY", "sto_date": "2026-01-15",
                                        "warehouse_id": wh["id"], "assignments": []}, headers=mh).status_code == 403

        bal0 = balance(c, mh, wh["id"], a1["id"], fg0["id"])
        bal1 = balance(c, mh, wh["id"], a1["id"], fg1["id"])
        assert bal0 > 0 and bal1 > 0

        r = c.post("/api/sto", json={"sto_number": "STO-TEST-1", "sto_date": "2026-01-15", "warehouse_id": wh["id"],
                                     "description": "Uji opname", "assignments": [
                                         {"locator_from": "A-01-01", "locator_to": "A-01-01",
                                          "counter_id": users["mh01"], "checker_id": users["checker01"]}]}, headers=sup)
        assert r.status_code == 200, r.text
        sto_id = r.json()["id"]
        assert r.json()["progress"]["total"] == 1
        assert c.post(f"/api/sto/{sto_id}/status", json={"status": "OPEN"}, headers=sup).status_code == 200
        assert c.post(f"/api/sto/{sto_id}/status", json={"status": "COUNTING"}, headers=sup).status_code == 200

        det = c.get(f"/api/m/sto/{sto_id}", headers=mh).json()
        assert len(det["locators"]) == 1
        slid = det["locators"][0]["id"]

        # MH counts: exact on fg0 (MATCH), +3 on fg1 (VARIANCE). Duplicate txn is idempotent.
        tx0 = "sto-" + uuid.uuid4().hex
        r = c.post(f"/api/m/sto/locators/{slid}/lines", json={"item_id": fg0["id"], "qty": bal0, "txn_id": tx0}, headers=mh)
        assert r.status_code == 200 and r.json()["ok"]
        dup = c.post(f"/api/m/sto/locators/{slid}/lines", json={"item_id": fg0["id"], "qty": bal0, "txn_id": tx0}, headers=mh)
        assert dup.json()["duplicate"] is True
        assert c.post(f"/api/m/sto/locators/{slid}/lines",
                      json={"item_id": fg1["id"], "qty": bal1 + 3, "txn_id": "sto-" + uuid.uuid4().hex},
                      headers=mh).status_code == 200
        assert c.post(f"/api/m/sto/locators/{slid}/finish", headers=mh).status_code == 200
        assert c.post(f"/api/m/sto/locators/{slid}/accept", headers=chk).status_code == 200

        rec = c.get(f"/api/sto/{sto_id}/reconciliation", headers=sup).json()
        assert rec["summary"]["MATCH"] >= 1 and rec["summary"]["VARIANCE"] >= 1
        assert c.post(f"/api/sto/{sto_id}/reconciliation/resolve",
                      json={"sto_locator_id": slid, "item_id": fg1["id"], "reason": "Fisik lebih"}, headers=mh).status_code == 403
        rv = c.post(f"/api/sto/{sto_id}/reconciliation/resolve",
                    json={"sto_locator_id": slid, "item_id": fg1["id"], "reason": "Hasil hitung fisik"}, headers=chk)
        assert rv.status_code == 200 and rv.json()["movement_type"] == "ADJUSTMENT", rv.text
        assert balance(c, mh, wh["id"], a1["id"], fg1["id"]) == bal1 + 3
        assert c.get(f"/api/sto/{sto_id}/reconciliation", headers=sup).json()["summary"]["issues"] == 0

        assert c.post(f"/api/sto/{sto_id}/status", json={"status": "CHECKING"}, headers=sup).status_code == 200
        assert c.post(f"/api/sto/{sto_id}/status", json={"status": "RECONCILIATION"}, headers=sup).status_code == 200
        assert c.post(f"/api/sto/{sto_id}/status", json={"status": "COMPLETED"}, headers=sup).status_code == 200
        assert c.get("/api/sto", headers=sup).json()["total"] >= 1


if __name__ == "__main__":
    test_full_flow()
    print("OK")
