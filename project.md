# PROJECT CONTEXT SPECIFICATION: WMS OPERASIONAL (FASE 1 + FASE 2 + FASE 3)
> **Warehouse Management System (WMS) Operasional Harian**
> **Prinsip Utama**: *"Saldo stok selalu dihitung dari ledger pergerakan, bukan disimpan statis."*
> **Fokus**: Barang Masuk (Inbound), Barang Keluar (Outbound), Transfer antar Lokator, **Stock Opname (hitung fisik vs ledger)**, dan **Pesan Operator** — online maupun offline. Tanpa integrasi ERP.

Dokumen ini adalah **Single Source of Truth (SSOT)** arsitektur, skema database, aturan bisnis, endpoint API, dan desain teknis proyek. File ini dapat langsung diunggah/ditempel ke AI lain sebagai konteks lengkap tanpa mengunggah seluruh kode sumber.

> Catatan Fase: Proyek ini pernah berupa aplikasi *Stock Opname (STO) + rekonsiliasi ERP*. **Fase 1** mengubahnya menjadi WMS operasional harian murni. **Fase 2** mengaktifkan kembali modul STO sebagai **cek fisik dibanding saldo ledger** (bukan ERP): MH (counter) menghitung di mobile, CHECKER memverifikasi, selisih diselesaikan lewat pergerakan ADJUSTMENT. **Fase 3** menyederhanakan UI mobile MH menjadi **3 halaman (Beranda / Scan / Akun)** dan menambahkan modul **Pesan Operator**. Lihat §12, §12b, dan §14 (Changelog & Guardrails).

---

## 1. Executive Summary & Visi Sistem

Aplikasi ini adalah **WMS operasional harian** berbasis web, dioptimalkan untuk perangkat mobile (*mobile-first PWA* untuk Material Handling / MH) dan desktop (*console* untuk Admin, Supervisor, Checker).

### Tujuan:
1. **Ledger sebagai sumber kebenaran tunggal**: Semua saldo diturunkan dari tabel `stock_movements`. Tidak ada kolom saldo statis. Menghapus risiko saldo "kadaluarsa".
2. **Stok tidak boleh minus**: Setiap Outbound/Transfer (dan pembatalan/void) divalidasi terhadap saldo tersedia, dihitung dalam satu transaksi DB dengan penguncian baris.
3. **Operasi lapangan tahan sinyal (Offline-First)**: MH dapat mencatat pergerakan saat offline (IndexedDB), lalu sinkron otomatis. Setiap transaksi ber-`client_txn_id` unik sehingga **idempoten** (tidak dobel saat dikirim ulang).
4. **Audit & koreksi terkendali**: Baris ledger **tidak pernah dihapus**. Koreksi dilakukan dengan **void (wajib alasan)** atau **ADJUSTMENT**, semuanya tercatat di `audit_logs`.
5. **Gudang fleksibel tanpa ubah kode**: Gudang, lokator, item, dan pengguna dikelola via UI. Lokator memiliki **QR** dan dapat dicetak (halaman label).
6. **Tanpa ERP**: Semua jejak integrasi/snapshot/rekonsiliasi ERP dihapus.

---

## 2. Tech Stack & Arsitektur

### Backend
- **Framework**: Python 3.11+ / FastAPI (`title` dari `APP_NAME`)
- **Web Server**: Uvicorn ASGI
- **ORM / DB**: SQLAlchemy 2.0 — SQLite default (`backend/sto.db`), MySQL via PyMySQL (opsional)
- **Keamanan**: JWT (HS256), bcrypt, rate-limit login in-process, OWASP middleware (CSP, `nosniff`, `DENY` framing, GZip, batas ukuran body, HSTS bila HTTPS)
- **Berkas & Ekspor**: `openpyxl` (XLSX), `reportlab` (PDF), CSV
- **Testing**: `pytest` + `TestClient` (E2E)

### Frontend
- **Vanilla Modern JS** (ES6+), tanpa framework berat; desain *Industrial SaaS* responsif mobile-first.
- **PWA**: `manifest.webmanifest` + Service Worker (`sw.js`) untuk cache app shell.
- **Scanner QR**: kamera HTML5 (`BarcodeDetector` bila tersedia, fallback `vendor/jsQR.js`).
- **QR Encoder**: `vendor/qrcode.js` (qrcode-generator, MIT) untuk mencetak label lokator.
- **Offline**: IndexedDB (`store.js`) untuk cache bundle master + antrean transaksi.

### Deployment
- **Docker** multi-stage + **docker-compose** (port host via `APP_PORT`, default `8000`).
- `container_name` = **`sto-pp2-app-new`** (diubah dari `sto-pp2-app` agar tidak bentrok dengan container versi lama yang mungkin masih berjalan di host yang sama).
- DB SQLite + log persisten di volume Docker `sto-pp2-data` (`/app/backend/data`). Seed demo aktif bila `SEED_DEMO=1`.

---

## 3. Struktur Direktori

```
Prototype WMS/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
├── project.md                       # SSOT (file ini)
├── diagrams.md                      # Diagram Mermaid: use case, ERD, sequence, state, activity, deployment
├── diagrams.puml                    # Diagram PlantUML (padanan diagrams.md)
├── backend/
│   ├── requirements.txt
│   ├── tests/
│   │   └── test_flow.py             # E2E: auth, RBAC, saldo, void, koreksi, sync, laporan, import
│   └── app/
│       ├── config.py                # env + APP_NAME / APP_SUBTITLE
│       ├── database.py              # engine, SessionLocal, auto-migration
│       ├── models.py                # ROLES(4), MOVEMENT_TYPES, REF_TYPES, StockMovement (+ STO models, Fase 2)
│       ├── core.py                  # JWT, bcrypt, RBAC require(), audit, rate limit, helpers
│       ├── main.py                  # FastAPI, middleware, error handler, router, static frontend
│       ├── seed.py                  # 4 role, 5 user, gudang L21/L22/L25, lokator, item, 8 movement contoh
│       ├── data/items_l21.csv       # Master item (25.000+ baris)
│       ├── routers/
│       │   ├── auth.py              # /api/auth: config, login, logout, me, change-password
│       │   ├── master.py            # /api/warehouses|locators|items|users (ADMIN)
│       │   ├── mobile.py            # /api/m: home, bundle, stock, inbound, outbound, transfer, sync
│       │   ├── movements.py         # /api/movements, /api/stock, /api/sync-transactions, /api/dashboard
│       │   ├── imports.py           # /api/imports: import master (ITEM/WAREHOUSE/LOCATOR/USER)
│       │   ├── reports.py           # /api/reports/{7 laporan}, /api/audit/actions
│       │   ├── sto.py               # /api/sto: STO lifecycle + rekonsiliasi (Fase 2)
│       │   ├── sto_mobile.py        # /api/m/sto: counting MH + sync offline (Fase 2)
│       │   └── messages.py          # /api/messages (manajer) + /api/m/messages (inbox operator)
│       └── services/
│           ├── stock.py             # SERVICE TUNGGAL: saldo, validasi, create_movement, void_movement
│           ├── export.py            # generator XLSX/CSV/PDF (memakai config.APP_NAME)
│           ├── counting.py          # logika counting STO (round-based) — dipakai (Fase 2)
│           └── recon.py             # rekonsiliasi fisik vs ledger + resolve via ADJUSTMENT (Fase 2)
├── frontend/
│   ├── index.html                   # PWA shell
│   ├── labels.html                  # Cetak label QR lokator (vendor/qrcode.js)
│   ├── manifest.webmanifest
│   ├── sw.js                        # Service Worker (cache app shell)
│   ├── css/app.css                  # Design system mobile & desktop
│   ├── vendor/
│   │   ├── jsQR.js                  # QR decoder (fallback)
│   │   └── qrcode.js                # QR encoder (label)
│   └── js/
│       ├── api.js                   # HTTP client, token, error, download
│       ├── ui.js                    # komponen: toast, sheet, confirm, keypad qty, DataTable, badge
│       ├── store.js                 # IndexedDB: bundle cache + antrean offline (movement + counting STO)
│       ├── scanner.js               # scanner QR
│       ├── mobile.js                # layar MH (3 tab): Beranda (pesan+tugas), Scan (masuk/keluar/pindah), Akun (+hitung opname)
│       ├── desktop.js               # console: dashboard, movements, stok, STO, pesan, koreksi, problems, master, import, laporan, audit
│       └── app.js                   # router hash, login, deteksi role & perangkat
```

---

## 4. Skema Database (Ledger-Centric)

Prinsip: **saldo tidak pernah disimpan.** Saldo per `(gudang, item, lokator)` = `SUM(masuk) − SUM(keluar)` dari `stock_movements` di luar baris `voided`.

```mermaid
erDiagram
    Warehouse ||--o{ Locator : has
    Warehouse ||--o{ StockMovement : records
    Item ||--o{ StockMovement : moves
    Item ||--o{ ItemWarehouse : eligible
    Warehouse ||--o{ ItemWarehouse : allows
    Locator ||--o{ StockMovement : from
    Locator ||--o{ StockMovement : to
    User ||--o{ StockMovement : created_by
    User ||--o{ SyncTransaction : sends
    User ||--o{ AuditLog : acts
```

### Tabel Utama
1. **`roles`, `users`, `user_roles`**: `users.password_hash` (bcrypt), `active`, soft-delete. Multi-role.
2. **`warehouses`**: `code`, `name`, `type` (FG/RM/…), `active`. Ditambah/diubah via UI tanpa ubah kode.
3. **`locators`**: `warehouse_id`, `code` (mis. `A-01-02`), `zone`, `rack`, `level`, `active`. Unik per gudang.
4. **`items`**: unik pada (`code`, `uom`). `name`, `group_code`, `group_name`, `barcode`, `qr_code`, `active`.
5. **`item_warehouses`**: eligibilitas item per gudang. Kosong = eligible di semua gudang.
6. **`stock_movements`** (LEDGER):
   - `id`, `movement_no` (unik, `MV-YYYY-000001`; max+1 per tahun)
   - `movement_type` ∈ {`INBOUND`, `OUTBOUND`, `TRANSFER`, `ADJUSTMENT`}
   - `warehouse_id`, `item_id`, `qty` (**selalu positif**)
   - `from_locator_id`, `to_locator_id`
   - `ref_type` ∈ {`PO`, `SURAT_JALAN`, `DO`, `LAINNYA`}, `ref_no`, `notes`
   - `created_by`, `created_at`, `device_id`
   - `client_txn_id` **UNIQUE** (idempotensi offline)
   - `voided`, `voided_by`, `voided_at`, `void_reason`, `corrects_movement_id`
7. **`sync_transactions`**: jurnal sinkronisasi offline (`txn_id`, `user_id`, `device_id`, `txn_type`, `payload`, `result` ∈ {`OK`, `DUPLICATE`, `REJECTED`}, `message`).
8. **`audit_logs`**: `action`, `object_type`, `object_id`, `old_value`, `new_value`, `username`, `ip`, `device`, `created_at`.
9. **`messages`** + **`message_reads`** (Pesan operator): pengumuman/instruksi dari manajer ke operator lapangan.
   - `messages`: `sender_id`, `title` (opsional), `body`, `level` ∈ {`INFO`, `WARN`, `URGENT`}, `target_role` ∈ {`MH`, `CHECKER`, `SUPERVISOR`, `ALL`}, `active`, `created_at`.
   - `message_reads`: `message_id`, `user_id` (PK gabungan), `read_at` — tanda "sudah dibaca" per pengguna.

### Aktif di Fase 2 (Stock Opname)
`stock_opnames`, `sto_assignments`, `sto_locators`, `stock_counts`, `stock_count_details`, `stock_recounts` + `services/counting.py` + `services/recon.py` + `routers/sto.py` + `routers/sto_mobile.py` (kedua router di-register di `main.py`).

### Dihapus
`erp_imports`, `erp_snapshots`, `erp_snapshot_details`, `reconciliations`, `reconciliation_lines`, `variances`, `routers/recon.py`, dan bagian ERP/COUNT pada importer.

---

## 5. Aturan Bisnis Saldo (Service `services/stock.py`)

Semua operasi stok melewati **satu service** agar aturan konsisten:

- **`balance(db, warehouse_id, item_id, locator_id)`** — saldo per lokator.
- **`stock_rows(...)`** — daftar saldo per (gudang, lokator, item) untuk UI/laporan.
- **Arah pergerakan**:
  - `INBOUND`: `to_locator` (+), `from_locator` null.
  - `OUTBOUND`: `from_locator` (−), `to_locator` null.
  - `TRANSFER`: `from_locator` (−) dan `to_locator` (+), keduanya wajib dan **berbeda**.
  - `ADJUSTMENT`: arah ditentukan ada/tidaknya `from_locator` / `to_locator`.
- **Stok tidak boleh minus**: Untuk setiap efek keluar (Outbound, sisi keluar Transfer, dan **void** dari movement yang menambah stok), sistem menghitung saldo tersedia. Jika hasilnya negatif → **ditolak (HTTP 409)** dengan pesan yang menyebut **saldo tersedia**.
- **Konsistensi & locking**: cek saldo + insert dilakukan dalam **satu transaksi DB**. Helper `_lock_item(...)` memakai `SELECT ... FOR UPDATE` (SQLite mengandalkan transaksi serial) untuk mencegah balapan.
- **Validasi master**:
  - Item harus `active` dan **eligible** di gudang (via `item_warehouses`; jika item tidak punya pemetaan gudang → eligible di mana saja).
  - Lokator harus milik **gudang yang sama** dan `active`.
- **`movement_no`**: `MV-YYYY-000001`, dihitung max+1 per tahun (dalam transaksi).
- **`create_movement(...)`**: membuat baris ledger + audit. **Tidak commit** (commit dilakukan pemanggil) — supaya bisa dipakai di dalam `sync` batch dengan `begin_nested`.
- **`void_movement(...)`**: menandai `voided`, `voided_by`, `voided_at`, `void_reason` (wajib). Tidak menghapus baris. Bila void menyebabkan saldo minus → **409**.
- **Tidak ada proses approval.**

### Koreksi (Checker)
- **Void** movement yang salah (wajib alasan), lalu buat movement baru atau **ADJUSTMENT**.
- Semua tercatat di `audit_logs`; baris ledger asli tetap ada.

---

## 6. Role-Based Access Control (RBAC)

4 peran:

| Peran | Tanggung Jawab | Akses |
| :--- | :--- | :--- |
| **ADMIN** | Konfigurasi & master | Penuh: user, gudang, lokator + generator + label QR, master item, import, audit log, kelola STO |
| **SUPERVISOR** | Pengawasan | Dashboard read-only simpel, daftar movement/stok, laporan, **kelola STO** (buat, penugasan, transisi status) |
| **CHECKER** | Verifikasi & koreksi | Semua akses Supervisor + detail/filter + **koreksi** (void/adjust; wajib alasan, tercatat audit) + **verifikasi STO & selesaikan selisih** |
| **MH** | Kerja lapangan | **Antarmuka mobile saja**: masuk, keluar, pindah, stok, **hitung fisik opname**, sync |

- `require(*roles)` = dependency RBAC. `ADMIN` diperlakukan sebagai superuser oleh `Session.has(...)`, sedangkan `Session.hasExact(...)` untuk pemeriksaan ketat di frontend.
- MH boleh mengakses **semua gudang aktif**.

---

## 7. API Contracts (FastAPI)

### Autentikasi (`/api/auth`)
- `GET /api/auth/config` → `{demo_mode, app_name, app_subtitle}` (tanpa auth; dipakai login page).
- `POST /api/auth/login` → JWT (rate-limited). `POST /api/auth/logout`. `GET /api/auth/me`. `POST /api/auth/change-password`.

### Mobile MH (`/api/m`) — `FIELD = require("MH","CHECKER","SUPERVISOR")`
- `GET /api/m/home` — kartu ringkas (counts + movement terbaru + **pesan terbaru + jumlah belum dibaca** + **tugas Stock Opname aktif**).
- `GET /api/m/bundle?warehouse_id=` — bundle offline (gudang, lokator, item gudang terkait).
- `GET /api/m/stock?warehouse_id=&q=` — daftar saldo.
- `POST /api/m/inbound` / `/outbound` / `/transfer` — catat movement. Body memuat `client_txn_id` untuk idempotensi.
- `POST /api/m/sync` — batch transaksi offline (diurutkan by timestamp), idempoten; yang gagal → `sync_transactions.result = REJECTED` + alasan.

### Pesan (`/api`) — kirim = `MANAGER = require("SUPERVISOR")`, inbox = pengguna terautentikasi
- `GET /api/m/messages` — inbox operator (pesan yang `target_role` cocok dengan role user atau `ALL`) + `unread`.
- `POST /api/m/messages/{id}/read` — tandai pesan sudah dibaca.
- `POST /api/messages` (**manajer**) — kirim pesan (body `title`, `body`, `level`, `target_role`).
- `GET /api/messages?target_role=&page=&size=` (**manajer**) — daftar pesan terkirim + jumlah dibaca.
- `DELETE /api/messages/{id}` (**manajer**) — non-aktifkan pesan (soft).

### Stock Opname Mobile (`/api/m/sto`) — `FIELD = require("MH","CHECKER","SUPERVISOR")`
- `GET /api/m/sto` — STO aktif untuk user (`my_locators`, `my_todo`).
- `GET /api/m/sto/{sto_id}` — detail + daftar lokator tugas.
- `GET /api/m/sto/locators/{slid}` — detail lokator + hasil hitung + riwayat putaran.
- `POST /api/m/sto/locators/{slid}/lines` — simpan hasil hitung (body `item_id`, `qty`, `txn_id` untuk idempotensi).
- `DELETE /api/m/sto/locators/{slid}/lines/{line_id}` — hapus satu baris hitung.
- `POST /api/m/sto/locators/{slid}/finish` — kirim lokator ke Checker (`WAITING_CHECK`).
- `POST /api/m/sto/locators/{slid}/accept` (**CHECKER**) — setujui hasil (`ACCEPTED`).
- `POST /api/m/sto/locators/{slid}/recount` (**CHECKER**) — minta hitung ulang (body `reason`, `note`).
- `POST /api/m/sto/sync` — batch offline (`STO_COUNT`, `STO_FINISH`), idempoten seperti `/api/m/sync`.

### Stock Opname (`/api/sto`) — `MANAGER = require("SUPERVISOR")`, resolve = `require("CHECKER")`
- `GET /api/sto` (list + filter status/q), `GET /api/sto/{id}` (detail + penugasan + progres).
- `POST /api/sto` — buat STO (+ penugasan awal). `POST /{id}/assignments`, `DELETE /{id}/assignments/{aid}`.
- `POST /{id}/status` — transisi status (`force` opsional untuk lewati gate). `DELETE /{id}`, `POST /{id}/reset-counts`.
- `GET /{id}/locators`, `GET /{id}/locators/{slid}`, `PUT /{id}/locators/{slid}/reassign`.
- `GET /{id}/reconciliation` — matriks fisik vs ledger + ringkasan.
- `POST /{id}/reconciliation/resolve` (**CHECKER**) — selesaikan selisih via ADJUSTMENT (body `sto_locator_id`, `item_id`, `reason`).

### Movements / Stok / Dashboard (`/api`) — `WIDE = require("SUPERVISOR","CHECKER")`, `CORRECT = require("CHECKER")`
- `GET /api/movements`, `GET /api/movements/export`, `GET /api/movements/{id}`.
- `POST /api/movements/{id}/void` (**Checker**) — wajib `reason`.
- `POST /api/movements/adjust` (**Checker**) — buat ADJUSTMENT.
- `GET /api/stock`, `GET /api/stock/export`.
- `GET /api/sync-transactions?result=REJECTED` — "transaksi bermasalah".
- `GET /api/dashboard` — KPI + chart 7 hari + filter gudang/tanggal.

### Master (`/api`) — `require("ADMIN")`
- `/api/warehouses` (CRUD + export), `/api/locators` (CRUD + `/generate` + export), `/api/items` (CRUD + `/lookup` + export), `/api/users` (CRUD + export + options).
- `/api/locators/generate` — generator terstruktur (Zone-Rack-Level).

### Import Master (`/api/imports`) — `require("ADMIN")`
- `POST /api/imports/upload` — preview (jenis: `ITEM`/`WAREHOUSE`/`LOCATOR`/`USER`).
- `GET /api/imports`, `/api/imports/{id}`, `/api/imports/{id}/errors`, `/api/imports/template/{kind}`.
- `POST /api/imports/{id}/commit` — eksekusi baris valid. `POST /api/imports/{id}/cancel`.

### Laporan (`/api/reports`) — `WIDE`, kecuali `audit_log` = `ADMIN`
7 laporan, format JSON / XLSX / CSV / PDF:
1. `stock_balance` — Saldo Stok per gudang/lokator/item.
2. `movement_history` — Riwayat pergerakan.
3. `inbound` — Barang Masuk.
4. `outbound` — Barang Keluar.
5. `transfer` — Transfer antar lokator.
6. `corrections` — Koreksi & pembatalan (void/ADJUSTMENT).
7. `audit_log` — Audit Log Aktivitas (**hanya ADMIN**).
- `GET /api/audit/actions` — daftar aksi untuk filter.

### Health
- `GET /api/health`.

---

## 8. Alur Pengalaman Pengguna (UX)

> **UI Mobile MH disederhanakan menjadi 3 tab**: **Beranda** (`#/m`), **Scan** (`#/m/scan`), **Akun** (`#/m/me`).
> Beranda = **pesan dari Admin/Supervisor/Checker + tugas** (Stock Opname aktif, ketuk untuk menghitung). Scan = satu alur transaksi dengan pemilih **Masuk / Keluar / Pindah**.

### Alur 0: Beranda & Pesan (MH)
1. MH login di ponsel → otomatis diarahkan ke **Beranda** (`#/m`).
2. Beranda menampilkan banner sinkronisasi, pemilih gudang, **Pesan** (belum dibaca disorot; ketuk untuk baca → `POST /api/m/messages/{id}/read`), **Tugas Saya** (STO aktif → ketuk untuk hitung), statistik hari ini, aksi cepat, dan pergerakan terakhir.
3. Manajer mengirim pesan dari desktop **Pesan Operator** (`#/d/messages`).

### Alur 1: Barang Masuk (MH)
1. MH login di ponsel → otomatis diarahkan ke **Beranda** (`#/m`).
2. Pilih gudang → buka **Scan** (`#/m/scan`) → tab **Masuk**.
3. Scan/ cari **item** → pilih **lokator tujuan** → input **qty** (keypad besar) → pilih **ref type/no** → catat.
4. Bila offline: transaksi masuk **antrean** IndexedDB; banner menandai jumlah pending. Saat online → `POST /api/m/sync` otomatis.
5. Saldo tersedia ditampilkan agar MH sadar konteks.

### Alur 2: Barang Keluar (MH)
1. Buka **Scan** → tab **Keluar** → pilih item → **lokator asal** (menampilkan saldo tersedia) → qty → ref.
2. Jika qty > saldo → ditolak dengan pesan saldo tersedia.

### Alur 3: Transfer antar Lokator (MH)
1. Buka **Scan** → tab **Pindah** → pilih item → **lokator asal** & **lokator tujuan** (wajib berbeda) → qty → catat.
2. Validasi saldo asal; kedua lokator harus di gudang yang sama.

### Alur 4: Koreksi (Checker)
1. Buka **Movements** / **Corrections** di desktop.
2. **Void** movement salah (wajib alasan) atau buat **ADJUSTMENT**.
3. Tercatat di **Audit Log**.

### Alur 5: Admin Master & Label
1. Tambah/ubah **gudang** → generate **lokator** → cetak **label QR** (`labels.html?warehouse_id=`) → tempel di rak.
2. Import master (ITEM/WAREHOUSE/LOCATOR/USER) via Excel, atau CRUD manual.
3. Kelola **user** & peran (ADMIN/SUPERVISOR/CHECKER/MH).

---

## 9. Sinkronisasi Offline (Idempotensi)

- Setiap transaksi mobile punya `client_txn_id` (UUID) yang di-`enqueue` di IndexedDB.
- `POST /api/m/sync` menerima **batch** (diurutkan by timestamp). Setiap item:
  - `OK` — dibuat.
  - `DUPLICATE` — `client_txn_id` sudah ada (dikirim ulang) → tidak digandakan.
  - `REJECTED` — gagal validasi (mis. stok minus) → disimpan di `sync_transactions` dengan `message`, ditampilkan ke MH dan dashboard Checker sebagai **"transaksi bermasalah"**.
- Frontend: `flush()` mengirim antrean, menghapus `OK`/`DUPLICATE`, menandai `REJECTED` (dengan opsi retry/discard).

---

## 10. Fitur Non-Fungsional

1. **Ledger append-only**: baris tidak pernah dihapus; koreksi via void/adjustment.
2. **Integritas saldo**: cek + insert satu transaksi, `FOR UPDATE`, anti-minus termasuk pada void & sync.
3. **Idempotensi offline**: `client_txn_id` UNIQUE.
4. **Keamanan**: CSP ketat, `nosniff`, anti-framing, GZip, batas ukuran body, HSTS bila HTTPS, rate limit login, audit log.
5. **Config identitas**: nama aplikasi dari `APP_NAME`/`APP_SUBTITLE` (tidak di-hardcode).

---

## 11. Kredensial Demo

Kata sandi default: **`demo1234`**

| Username | Role | Nama | Penggunaan |
| :--- | :--- | :--- | :--- |
| `admin` | `ADMIN` | Administrator | Master data, user, gudang/lokator/label, import, audit |
| `supervisor01` | `SUPERVISOR` | Sari Supervisor | Dashboard & laporan (read-only) |
| `checker01` | `CHECKER` | Citra Checker | Verifikasi & koreksi (void/adjustment) |
| `mh01` | `MH` | Budi Material Handling | Mobile: masuk/keluar/pindah/sync |
| `mh02` | `MH` | Dewi Material Handling | Mobile: masuk/keluar/pindah/sync |

Gudang seed: **L21 (PP2 WH FG)**, **L22 (FG Hasbro)**, **L25 (Raw Material)** + lokator contoh + 8 movement contoh (inbound/transfer/outbound) + **2 pesan contoh** (satu `target_role=ALL` level `INFO` dari admin, satu `target_role=MH` level `WARN` dari supervisor01).

---

## 12. Fase 2: Stock Opname vs Ledger (AKTIF)

Stock Opname = **cek fisik dibanding saldo ledger** (bukan ERP). Rekonsiliasi dihitung *on-the-fly* dari ledger; tidak ada tabel rekonsiliasi tersimpan.

- **Peran**: `MH` = counter (hitung fisik, mobile); `CHECKER` = verifikasi lokator + selesaikan selisih; `SUPERVISOR`/`ADMIN` = kelola STO (buat, penugasan, transisi status).
- **Alur status STO** (`STO_TRANSITIONS`): `DRAFT → OPEN → COUNTING → CHECKING → RECONCILIATION → COMPLETED` (+ `CANCELLED`). Gate `RECONCILIATION`/`COMPLETED`: semua lokator `ACCEPTED` dan `issues == 0` (kecuali `force`).
- **Status lokator** (`sto_locators`): `NOT_STARTED → IN_PROGRESS → WAITING_CHECK → ACCEPTED` (atau `RECOUNT`). Counting *round-based*: hasil lama tak pernah ditimpa, disimpan sebagai riwayat putaran (`stock_recounts`).
- **Rekonsiliasi** (`services/recon.py`): *expected* = saldo ledger per `(gudang, item, lokator)`; *physical* = hasil `StockCount` berstatus `FINAL` per lokator. Baris berstatus `MATCH` / `VARIANCE` / `UNEXPECTED` / `MISSING`.
- **Resolusi selisih** (`resolve`): Checker membuat pergerakan **ADJUSTMENT** agar ledger = fisik (`to_locator` bila diff > 0, `from_locator` bila diff < 0; `ref_type = LAINNYA`). Setelah itu baris menjadi `MATCH` (terdeteksi otomatis).
- **API**: `/api/sto` (kelola, monitor lokator, `reconciliation`, `reconciliation/resolve`) + `/api/m/sto` (counting MH + `sync` offline). Lihat §8.
- **UI**: Mobile `#/m/opname` (daftar STO → lokator → layar hitung dengan keypad + scan/cari, finish/accept/recount); juga dijangkau dari **Tugas Saya** di Beranda. Desktop `#/d/sto` (daftar + buat STO, monitor lokator, tab rekonsiliasi + tombol "Selesaikan" selisih).

---

## 12b. UI Mobile 3 Halaman + Pesan Operator (FASE 3, AKTIF)

- **Navigasi MH dipangkas jadi 3 tab**: **Beranda** (`#/m`), **Scan** (`#/m/scan`), **Akun** (`#/m/me`). Layar lain (hitung opname, cek stok, sync) diakses dari Beranda, bukan tab.
- **Beranda** = pusat informasi: banner sinkronisasi, gudang aktif, **Pesan** (dari Admin/Supervisor/Checker, level `INFO`/`WARN`/`URGENT`, tandai baca), **Tugas Saya** (STO aktif), statistik hari ini, aksi cepat, pergerakan terakhir.
- **Scan** = satu alur transaksi dengan pemilih **Masuk / Keluar / Pindah** (segmented control) memakai form movement yang sama; logika saldo/validasi identik dengan Fase 1.
- **Pesan**: model `messages` + `message_reads`; router `messages.py` (kirim/list/hapus oleh `SUPERVISOR`; inbox + tandai-baca oleh operator). Manajer mengirim dari desktop **Pesan Operator** (`#/d/messages`). Seed menyertakan 2 pesan contoh.

---

## 13. Panduan Prompt untuk AI Penerima

```text
Halo AI, saya melampirkan dokumen arsitektur & spesifikasi teknis proyek "WMS Operasional (Fase 1 + Fase 2 + Fase 3)" dalam Markdown di atas.

Pahami arsitektur, skema database ledger-centric, aturan bisnis saldo, RBAC 4 peran, alur mobile offline, modul Stock Opname (fisik vs ledger), UI mobile 3 halaman (Beranda/Scan/Akun), modul Pesan Operator, dan kontrak API. Saya ingin berdiskusi/meminta pengembangan fitur berdasarkan konteks ini.

Konfirmasikan pemahaman Anda dengan ringkasan 3 pilar:
1. Ledger `stock_movements` sebagai sumber tunggal saldo (anti-minus, append-only, koreksi via void/adjustment).
2. Alur mobile offline idempoten (`client_txn_id` + `/api/m/sync`, `/api/m/sto/sync`) untuk MH (masuk/keluar/pindah + hitung opname).
3. RBAC 4 peran (ADMIN/SUPERVISOR/CHECKER/MH) + Stock Opname sebagai cek fisik vs ledger (selisih diselesaikan via ADJUSTMENT) + Pesan Operator (manajer → operator lapangan).

PENTING: Baca §14 (Changelog & Guardrails). Jangan mengubah konsep inti (ledger-centric, anti-minus, append-only, RBAC 4 peran, offline-first idempoten). Fase 3 hanya menyederhanakan UI mobile + menambah pesan; tidak mengubah aturan bisnis saldo/STO.
```

---

## 14. Changelog & Guardrails (FASE 3 — Perubahan Terakhir)

> Bagian ini mencatat perubahan terakhir agar AI penerima **tidak melenceng dari konsep awal**. Konsep inti Fase 1 & Fase 2 tetap tidak berubah.

### 14.1 Ringkasan Perubahan Fase 3 (yang baru dikerjakan)
**Backend**
- `models.py`: tambah `Message` (`sender_id`, `title`, `body`, `level` ∈ {`INFO`,`WARN`,`URGENT`}, `target_role` ∈ {`MH`,`CHECKER`,`SUPERVISOR`,`ALL`}, `active`, `created_at`) + `MessageRead` (`message_id`, `user_id` PK gabungan, `read_at`) + konstanta `MESSAGE_LEVELS`/`MESSAGE_TARGETS`.
- `routers/messages.py` (BARU): `POST /api/messages`, `GET /api/messages`, `DELETE /api/messages/{id}` (manajer `SUPERVISOR`); `GET /api/m/messages`, `POST /api/m/messages/{id}/read` (operator). Helper `inbox(db, user)`.
- `routers/mobile.py`: `GET /api/m/home` kini juga mengembalikan `messages`, `unread`, dan `tasks` (tugas STO aktif).
- `routers/sto_mobile.py`: ekstrak helper `my_sto_tasks(db, user)` (dipakai `GET /api/m/sto` dan `/api/m/home`).
- `main.py`: register router `messages`.
- `seed.py`: tambah 2 pesan contoh.
- `tests/test_flow.py`: blok uji pesan + asersi `home["tasks"]`.

**Frontend**
- `mobile.js`: nav MH dipangkas jadi **3 tab** (Beranda/Scan/Akun). `renderHome` baru = banner sinkron + gudang + **Pesan** (tandai baca) + **Tugas** + statistik + aksi cepat + pergerakan terakhir. `renderScan` BARU (segmented **Masuk/Keluar/Pindah**) memakai `movementForm(...)` hasil refactor dari `renderMovement`. Layar opname/stok/sync tetap ada (diakses dari Beranda).
- `desktop.js`: nav + halaman **Pesan Operator** (`#/d/messages`): tulis/list/hapus; `renderMessages`, `messageForm`, `deleteMessage`.
- `app.js`: route baru `#/m/scan`, `#/d/messages`.
- `ui.js`: ikon `bell`/`send`, `MESSAGE_LEVELS`, `MESSAGE_TARGETS`, `msgLevel`, `msgBadge`.
- `app.css`: `.seg` (segmented control), `.card.msg` (+`.unread`).
- Cache PWA dinaikkan ke **v29** (`index.html` `?v=29`, `sw.js` `CACHE_NAME="wms-shell-v29"`).

**Docker**
- `docker-compose.yml`: `container_name` diubah menjadi **`sto-pp2-app-new`** (menghindari bentrok nama dengan container versi lama). Port host via `APP_PORT` (contoh lokal: `8010`).

**Dokumentasi**: `README.md` + `project.md` diperbarui (Fase 3, UI 3 halaman, modul Pesan, skema `messages`/`message_reads`, endpoint, skenario uji #12).

### 14.2 Hal yang TIDAK berubah (jangan diubah tanpa diminta)
- **Ledger-centric**: saldo tetap dihitung dari `stock_movements`; tidak boleh menambah kolom saldo statis.
- **Anti-minus & append-only**: aturan saldo, void, dan ADJUSTMENT tetap; koreksi tetap lewat void/adjustment (wajib alasan, tercatat audit).
- **Idempotensi offline**: `client_txn_id` UNIQUE + `/api/m/sync` & `/api/m/sto/sync` tetap.
- **RBAC 4 peran**: ADMIN/SUPERVISOR/CHECKER/MH tetap; `require()` (ADMIN = superuser) & `Session.hasExact()` tetap.
- **STO**: alur status & rekonsiliasi on-the-fly (tanpa tabel rekonsiliasi tersimpan) tetap.
- **Kontrak API Fase 1/2**: endpoint lama tidak dihapus; perubahan bersifat **aditif** (menambah field `messages`/`unread`/`tasks` pada `/api/m/home`, menambah route baru).

### 14.3 Konvensi & Guardrail untuk AI berikutnya
1. **Aditif, bukan destruktif**: pertahankan endpoint & perilaku lama; tambah fitur tanpa menghapus kontrak yang sudah ada.
2. **Satu sumber kebenaran**: semua mutasi stok melalui `services/stock.py`; counting STO melalui `services/counting.py`; rekonsiliasi melalui `services/recon.py`.
3. **Commit di pemanggil**: `create_movement`/service tidak `commit`; router yang `commit` (mendukung batch sync `begin_nested`).
4. **UI Bahasa Indonesia**, tanpa hardcode nama perusahaan (pakai `APP_NAME`/`APP_SUBTITLE`).
5. **MH = mobile saja**; manajer (Admin/Supervisor/Checker) = desktop console. Jangan pindahkan fitur manajerial ke mobile.
6. **Tema mobile = 3 tab**; fitur kerja lapangan lain diakses dari **Beranda**, bukan menambah tab baru.
7. **Bump cache PWA** (`?v=` di `index.html` + `CACHE_NAME` di `sw.js`) setiap mengubah file frontend.
8. **Sertakan uji**: perubahan backend wajib menambah/menjaga `tests/test_flow.py` hijau; frontend lewat `node --check`.
9. **Koreksi & audit**: jangan menambah penghapusan permanen baris ledger; gunakan void/adjustment.
10. **Offline-first**: transaksi MH harus tetap bisa di-`enqueue` dan idempoten.

### 14.4 Status Verifikasi Terakhir
- `pytest -q` → **1 passed** (E2E: auth/RBAC, saldo, void, koreksi, sync, laporan, import, STO Fase 2, pesan Fase 3, tugas di `/api/m/home`).
- `node --check` semua JS frontend → **OK**.
- Smoke HTTP (Docker, port 8010) → `/api/health` `{"status":"ok"}`, `/api/auth/config` mengembalikan `app_name`; container **healthy**.
