# WMS Operasional — Warehouse Management System (Fase 1 + Fase 2)

Aplikasi **Warehouse Management System** operasional harian: **Barang Masuk (Inbound)**, **Barang Keluar (Outbound)**, **Transfer antar Lokator**, dan **Stock Opname (hitung fisik vs ledger)** — online maupun offline. Mobile-first PWA untuk Material Handling (MH), desktop console untuk Admin/Supervisor/Checker.

Prinsip utama:
> **"Saldo stok selalu dihitung dari ledger pergerakan (`stock_movements`), bukan disimpan statis. Stok tidak boleh minus."**

> **Fase 1** = WMS murni tanpa ERP. **Fase 2** = modul **Stock Opname** diaktifkan sebagai cek fisik dibanding **saldo ledger** (MH menghitung, Checker memverifikasi, selisih diselesaikan via ADJUSTMENT).

---

## 1. Struktur Aplikasi

```
Prototype WMS/
├── backend/
│   ├── app/
│   │   ├── config.py             # Environment + APP_NAME / APP_SUBTITLE
│   │   ├── database.py           # Engine, SessionLocal, auto-migration
│   │   ├── models.py             # ROLES(4), MOVEMENT_TYPES, StockMovement (+ STO Fase 2)
│   │   ├── core.py               # JWT, bcrypt, RBAC, audit, rate limit
│   │   ├── seed.py               # 4 role, 5 user, gudang, lokator, item, movement contoh
│   │   ├── main.py               # FastAPI, security headers, error handling, static frontend
│   │   ├── services/
│   │   │   ├── stock.py          # SERVICE TUNGGAL saldo & validasi (create_movement, void_movement)
│   │   │   ├── export.py         # XLSX / CSV / PDF
│   │   │   ├── counting.py       # STO counting round-based (Fase 2)
│   │   │   └── recon.py          # Rekonsiliasi fisik vs ledger + resolve ADJUSTMENT (Fase 2)
│   │   └── routers/
│   │       ├── auth.py           # /api/auth (config, login, logout, me, change-password)
│   │       ├── master.py         # /api/warehouses|locators|items|users (ADMIN)
│   │       ├── mobile.py         # /api/m (home, bundle, stock, inbound, outbound, transfer, sync)
│   │       ├── movements.py      # /api/movements, /api/stock, /api/sync-transactions, /api/dashboard
│   │       ├── imports.py        # /api/imports (ITEM/WAREHOUSE/LOCATOR/USER)
│   │       ├── reports.py        # /api/reports (7 laporan), /api/audit/actions
│   │       ├── sto.py            # /api/sto: STO lifecycle + rekonsiliasi (Fase 2)
│   │       ├── sto_mobile.py     # /api/m/sto: counting MH + sync offline (Fase 2)
│   │       └── messages.py       # /api/messages (manajer) + /api/m/messages (inbox operator)
│   ├── tests/
│   │   └── test_flow.py          # E2E test suite
│   └── requirements.txt
├── frontend/
│   ├── css/app.css               # Design system (mobile-first)
│   ├── js/
│   │   ├── api.js                # Fetch wrapper, bearer auth, download
│   │   ├── ui.js                 # Toast, sheet, keypad qty, DataTable, badge
│   │   ├── store.js              # IndexedDB cache + antrean offline (movement + counting STO)
│   │   ├── scanner.js            # QR scanner (BarcodeDetector / jsQR)
│   │   ├── mobile.js             # Layar MH (3 tab): Beranda (pesan+tugas), Scan (masuk/keluar/pindah), Akun
│   │   ├── desktop.js            # Console: dashboard, movements, stok, STO, pesan, koreksi, problems, master, import, laporan, audit
│   │   └── app.js                # Router hash, login, deteksi role & perangkat
│   ├── vendor/
│   │   ├── jsQR.js               # QR decoder (fallback)
│   │   └── qrcode.js             # QR encoder (label lokator)
│   ├── index.html                # PWA shell
│   ├── labels.html               # Cetak label QR lokator
│   ├── manifest.webmanifest
│   └── sw.js                     # Service Worker (cache app shell)
└── README.md
```

---

## 2. Skema Database (Ledger-Centric)

Saldo **tidak** disimpan statis. Saldo per (gudang, item, lokator) = `SUM(masuk) − SUM(keluar)` dari `stock_movements` di luar baris `voided`.

- `roles`: `ADMIN`, `SUPERVISOR`, `CHECKER`, `MH`.
- `users`, `user_roles`: kredensial (bcrypt), aktif, soft-delete, multi-role.
- `warehouses`: gudang dinamis (tanpa hardcode).
- `locators`: `code`, `zone`, `rack`, `level` per gudang (untuk QR label).
- `items`: unik pada (`code`, `uom`).
- `item_warehouses`: eligibilitas item per gudang (kosong = semua gudang).
- `stock_movements` (**ledger**): `movement_no` (`MV-YYYY-000001`), `movement_type` (`INBOUND`/`OUTBOUND`/`TRANSFER`/`ADJUSTMENT`), `qty` (selalu positif), `from_locator_id`, `to_locator_id`, `ref_type` (`PO`/`SURAT_JALAN`/`DO`/`LAINNYA`), `ref_no`, `notes`, `created_by`, `device_id`, `client_txn_id` (**UNIQUE**, idempotensi), `voided`, `voided_by`, `voided_at`, `void_reason`, `corrects_movement_id`.
- `sync_transactions`: jurnal sync offline (`result`: `OK`/`DUPLICATE`/`REJECTED`).
- `audit_logs`: seluruh aktivitas penting.
- **Pesan (messages)**: `messages` (`sender_id`, `title`, `body`, `level` `INFO`/`WARN`/`URGENT`, `target_role` `MH`/`CHECKER`/`SUPERVISOR`/`ALL`, `active`) + `message_reads` (tanda sudah dibaca per pengguna).
- **Stock Opname (Fase 2)**: `stock_opnames`, `sto_assignments`, `sto_locators`, `stock_counts`, `stock_count_details`, `stock_recounts`. Rekonsiliasi **tidak** disimpan — dihitung on-the-fly dari ledger.

---

## 3. Aturan Bisnis Saldo

- `INBOUND` menambah (`to_locator`), `OUTBOUND` mengurangi (`from_locator`), `TRANSFER` memindah (`from` → `to`, harus berbeda & satu gudang), `ADJUSTMENT` arah dari ada/tidaknya lokator.
- **Stok tidak boleh minus**: Outbound/Transfer (dan **void** yang menambah stok) ditolak **409** bila membuat saldo negatif; pesan menyebut **saldo tersedia**.
- Cek saldo + insert dalam **satu transaksi DB** dengan penguncian baris.
- Lokator harus milik gudang yang sama & aktif; item harus eligible.
- **Koreksi**: `void` (wajib alasan) atau `ADJUSTMENT`. Baris ledger **tidak pernah dihapus**; semua tercatat di `audit_logs`.

---

## 4. Role & Hak Akses

| Role | Hak Akses |
| :--- | :--- |
| **ADMIN** | Penuh: user, gudang, lokator + generator + label QR, master item, import, audit log, kelola STO |
| **SUPERVISOR** | Dashboard read-only, daftar movement/stok, laporan, **kelola STO** (buat, penugasan, transisi status) |
| **CHECKER** | Semua akses Supervisor + detail/filter + **koreksi** (void/adjust; wajib alasan, tercatat audit) + **verifikasi STO & selesaikan selisih** |
| **MH** | Antarmuka **mobile** saja (3 tab: Beranda/Scan/Akun): masuk, keluar, pindah, cek stok, **hitung fisik opname**, baca pesan, sync |

---

## 5. Alur Utama

### A. Barang Masuk / Keluar / Transfer (MH, mobile)
1. Login di ponsel → otomatis masuk **Beranda** (`#/m`) dengan navigasi 3 tab: **Beranda / Scan / Akun**.
2. Beranda menampilkan **pesan** dari manajer + **tugas** (STO) + statistik hari ini.
3. Buka tab **Scan** → pilih **Masuk / Keluar / Pindah**.
4. **MASUK**: pilih item → lokator tujuan → qty → ref.
5. **KELUAR**: pilih item → lokator asal (tampil saldo) → qty → ref.
6. **PINDAH**: pilih item → lokator asal & tujuan (berbeda) → qty.
7. Bila offline, transaksi masuk antrean IndexedDB; saat online otomatis tersinkron (`/api/m/sync`), idempoten via `client_txn_id`.

### A2. Pesan Operator
1. **Manajer** (Admin/Supervisor/Checker) membuka **Pesan Operator** (`#/d/messages`) di desktop → **Tulis Pesan** (penerima + level + isi).
2. **MH** melihat pesan di **Beranda**; belum dibaca disorot. Ketuk untuk membaca → ditandai `read` (`POST /api/m/messages/{id}/read`).

### B. Koreksi (Checker, desktop)
1. Buka **Movements** atau **Corrections**.
2. **Void** movement salah (wajib alasan) atau buat **ADJUSTMENT**.
3. Tercatat di **Audit Log**.

### C. Admin (desktop)
1. Tambah/ubah gudang → **generate lokator** → cetak **label QR**.
2. Import master (ITEM/WAREHOUSE/LOCATOR/USER) atau CRUD manual.
3. Kelola user & peran.

### D. Stock Opname (Fase 2)
1. **Supervisor/Admin**: buat STO (`#/d/sto`) → tugaskan rentang lokator ke MH (counter) + Checker → **Buka** (OPEN).
2. **MH** (mobile `#/m/opname`): pilih STO → lokator → hitung fisik per item → **Selesai** (kirim ke Checker).
3. **Checker**: **Terima** (ACCEPTED) atau **Hitung Ulang** (recount) di mobile/desktop.
4. **Checker**: buka tab **Rekonsiliasi vs Ledger**, selesaikan selisih via **ADJUSTMENT** (wajib alasan).
5. **Supervisor/Admin**: transisi ke **COMPLETED** setelah semua lokator diterima & tidak ada selisih.

---

## 6. Instalasi & Menjalankan

### Prasyarat
- Python 3.11+
- pip

### Opsi A: Docker (disarankan)
```powershell
docker compose up -d --build
```
Jika port bentrok, ubah `APP_PORT` di `.env` lalu `docker compose up -d`.

### Opsi B: Python langsung
```powershell
pip install -r backend/requirements.txt
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Akses
- Web App: `http://localhost:8000/`
- API Docs: `http://localhost:8000/api/docs`
- Label QR: `http://localhost:8000/labels.html?warehouse_id=1`

---

## 7. Konfigurasi Environment

| Variable | Default | Deskripsi |
| :--- | :--- | :--- |
| `APP_PORT` | `8000` | Port host (docker-compose). |
| `DATABASE_URL` | `sqlite:///backend/sto.db` | Koneksi DB. MySQL: `mysql+pymysql://user:pass@host:3306/sto`. |
| `SECRET_KEY` | *(dev)* | Kunci JWT (32+ karakter untuk produksi). |
| `TOKEN_HOURS` | `12` | Masa berlaku token. |
| `MAX_UPLOAD_MB` | `10` | Batas unggah Excel. |
| `SEED_DEMO` | `1` | Seed data demo pada DB kosong. |
| `APP_NAME` | `WMS` | Nama aplikasi (UI/judul/ekspor). |
| `APP_SUBTITLE` | `Warehouse Management System` | Subjudul aplikasi. |

---

## 8. Kredensial Demo

Kata sandi: **`demo1234`**

| Username | Role | Nama |
| :--- | :--- | :--- |
| `admin` | `ADMIN` | Administrator |
| `supervisor01` | `SUPERVISOR` | Sari Supervisor |
| `checker01` | `CHECKER` | Citra Checker |
| `mh01` | `MH` | Budi Material Handling |
| `mh02` | `MH` | Dewi Material Handling |

---

## 9. Skenario Uji (Otomatis)

`backend/tests/test_flow.py` (jalankan: `cd backend` lalu `..\.venv\Scripts\python.exe -m pytest -q`) memverifikasi:
1. **Auth & RBAC**: login salah 401; proteksi rute per role.
2. **Saldo seed**: saldo awal gudang L21 sesuai.
3. **Inbound** + idempotensi (`client_txn_id` duplikat tidak menggandakan).
4. **Outbound** melebihi saldo → 409; outbound valid mengurangi saldo.
5. **Transfer** antar lokator & tolak lokator sama (422).
6. **Void**: tanpa alasan → 422; dengan alasan OK; void ulang → 409; void oleh MH → 403; void yang membuat minus → 409.
7. **Adjustment** ADD/REMOVE + tolak minus.
8. **Sync offline** batch `[OK, REJECTED]`, resubmit → `DUPLICATE`, filter transaksi bermasalah.
9. **Laporan**: 6 laporan untuk Supervisor; `audit_log` hanya Admin; ekspor XLSX/CSV/PDF.
10. **Master**: gudang, generator lokator, import master.
11. **Stock Opname (Fase 2)**: MH tidak boleh buat STO (403); alur OPEN→COUNTING; hitung MATCH + VARIANCE; idempotensi baris hitung; finish→accept; MH resolve selisih → 403; Checker resolve → ADJUSTMENT (saldo selaras, issues 0); transisi RECONCILIATION→COMPLETED.
12. **Pesan**: MH tidak boleh kirim (403); level tak dikenal → 422; kirim oleh Supervisor OK; muncul di inbox `/api/m/messages` + `/api/m/home` (unread); tandai baca menurunkan unread; daftar manajer menghitung `reads`; hapus → hilang dari inbox.

---

## 10. Batasan & Catatan

- **Fase 1**: tanpa integrasi ERP.
- **Fase 2**: Stock Opname aktif — cek fisik dibanding **saldo ledger** (bukan ERP). Counter = **MH**; selisih diselesaikan **Checker** via **ADJUSTMENT**.
- **Fase 3 (UI mobile)**: antarmuka MH disederhanakan jadi 3 tab (**Beranda / Scan / Akun**) + modul **Pesan Operator** (manajer → operator lapangan).
- **Kamera QR**: butuh secure context (`https://` atau `localhost`). Di LAN HTTP gunakan pencarian manual / scanner Bluetooth.
- **Backend relasional**: SQLite (default) untuk zero-setup; gunakan MySQL untuk deployment besar.
