# PROJECT CONTEXT SPECIFICATION: WMS OPERASIONAL PT XYZ

> **Warehouse Management System (WMS) Operasional Harian**
> **Prinsip Utama**: *"Saldo stok selalu dihitung dari ledger pergerakan (`stock_movements`), bukan disimpan statis. Stok tidak boleh minus."*
> **Fokus**: Barang Masuk (Inbound), Barang Keluar (Outbound), Transfer antar Lokator, **Stock Opname (hitung fisik vs ledger)**, dan **Pesan Operator** — online maupun offline. Tanpa integrasi ERP.

Dokumen ini adalah **Single Source of Truth (SSOT)** arsitektur, skema database, aturan bisnis, endpoint API, alur pengguna, dan desain teknis proyek. File ini dapat langsung diunggah/ditempel ke AI lain sebagai konteks lengkap tanpa mengunggah seluruh kode sumber.

> **Catatan Fase**: Proyek ini berkembang dalam 3 fase.
> - **Fase 1**: WMS operasional harian murni (Inbound, Outbound, Transfer) tanpa ERP.
> - **Fase 2**: Modul Stock Opname (STO) sebagai **cek fisik dibanding saldo ledger** — MH menghitung di mobile, Checker memverifikasi, selisih diselesaikan via pergerakan ADJUSTMENT.
> - **Fase 3**: UI mobile MH disederhanakan menjadi **3 halaman (Beranda / Scan / Akun)** dan ditambahkan modul **Pesan Operator**.

---

## 1. Executive Summary & Visi Sistem

Aplikasi ini adalah **WMS operasional harian** berbasis web, dioptimalkan untuk perangkat mobile (*mobile-first PWA* untuk Material Handling / MH) dan desktop (*console* untuk Admin, Supervisor, Checker).

### Latar Belakang (Konteks PT XYZ)

Sebelum sistem ini dibangun, PT XYZ menggunakan Microsoft Access, Microsoft Excel dengan macro, dan dokumen kertas (ID Tag) untuk mencatat pergerakan barang. Proses tersebut menghasilkan:
- **Ketidakkonsistensian data** antara kertas, scanner barcode, dan sistem Access.
- **Delay pencatatan** hingga berhari-hari karena proses manual.
- **Tidak ada visibilitas** saldo stok real-time atau ketersediaan lokasi rak.
- **Tidak ada pembatasan akses** berbasis peran pengguna.

### Tujuan Sistem

1. **Ledger sebagai sumber kebenaran tunggal**: Semua saldo diturunkan dari tabel `stock_movements`. Tidak ada kolom saldo statis. Menghapus risiko saldo "kadaluarsa".
2. **Stok tidak boleh minus**: Setiap Outbound/Transfer (dan pembatalan/void) divalidasi terhadap saldo tersedia, dihitung dalam satu transaksi DB dengan penguncian baris.
3. **Operasi lapangan tahan sinyal (Offline-First PWA)**: MH dapat mencatat pergerakan saat offline (IndexedDB + Service Worker), lalu sinkron otomatis. Setiap transaksi ber-`client_txn_id` unik sehingga **idempoten** (tidak dobel saat dikirim ulang).
4. **Audit & koreksi terkendali**: Baris ledger **tidak pernah dihapus**. Koreksi dilakukan dengan **void (wajib alasan)** atau **ADJUSTMENT**, semuanya tercatat di `audit_logs`.
5. **Gudang fleksibel tanpa ubah kode**: Gudang, lokator, item, dan pengguna dikelola via UI. Lokator memiliki **QR** dan dapat dicetak (halaman label).
6. **Tanpa ERP**: Semua jejak integrasi/snapshot/rekonsiliasi ERP dihapus.

---

## 2. Tech Stack & Arsitektur

### Backend
- **Framework**: Python 3.11+ / FastAPI (`title` dari `APP_NAME`)
- **Web Server**: Uvicorn ASGI
- **ORM / DB**: SQLAlchemy 2.0 — SQLite default (`backend/sto.db`), MySQL via PyMySQL (opsional, konfigurasi di `.env`)
- **Keamanan**: JWT (HS256), bcrypt, rate-limit login in-process, OWASP middleware (CSP, `nosniff`, `DENY` framing, GZip, batas ukuran body, HSTS bila HTTPS)
- **File & Ekspor**: `openpyxl` (XLSX), `reportlab` (PDF), CSV
- **Testing**: `pytest` + `TestClient` (E2E, `backend/tests/test_flow.py`)

### Frontend
- **Vanilla Modern JS** (ES6+), tanpa framework berat; desain *Industrial SaaS* responsif mobile-first.
- **PWA**: `manifest.webmanifest` + Service Worker (`sw.js`) untuk cache app shell (offline loading).
- **Scanner QR**: kamera HTML5 (`BarcodeDetector` bila tersedia, fallback `vendor/jsQR.js`).
- **QR Encoder**: `vendor/qrcode.js` (qrcode-generator, MIT) untuk mencetak label lokator.
- **Offline**: IndexedDB (`store.js`) untuk cache bundle master + antrean transaksi (movement & counting STO).

### Deployment
- **Docker** multi-stage + **docker-compose** (port host via `APP_PORT`, default `8000`).
- `container_name` = **`wms-prototype`**.
- DB SQLite + log persisten di volume Docker `sto-pp2-data` (`/app/backend/data`). Seed demo aktif bila `SEED_DEMO=1`.

---

## 3. Struktur Direktori

```
Prototype WMS/
├── Dockerfile
├── docker-compose.yml
├── .env                             # Konfigurasi runtime (port, DB, secret, seed)
├── .env.example
├── init_db.py                       # Skrip inisialisasi DB lokal (tanpa Docker)
├── README.md
├── project.md                       # SSOT (file ini)
├── diagrams.md                      # Diagram Mermaid: use case, ERD, sequence, state, activity, deployment
├── diagrams.puml                    # Diagram PlantUML (padanan diagrams.md)
├── backend/
│   ├── sto.db                       # SQLite database (auto-dibuat saat startup / init_db.py)
│   ├── requirements.txt
│   ├── tests/
│   │   └── test_flow.py             # E2E: auth, RBAC, saldo, void, koreksi, sync, laporan, import
│   └── app/
│       ├── config.py                # env + APP_NAME / APP_SUBTITLE
│       ├── database.py              # engine, SessionLocal, auto-migration
│       ├── models.py                # ROLES(4), MOVEMENT_TYPES, REF_TYPES, StockMovement (+ STO models)
│       ├── core.py                  # JWT, bcrypt, RBAC require(), audit, rate limit, helpers
│       ├── main.py                  # FastAPI, middleware, error handler, router, static frontend
│       ├── seed.py                  # 4 role, 5 user, gudang L21/L22/L25, lokator, item, 8 movement, 2 pesan
│       ├── data/items_l21.csv       # Master item awal (seed only — 25.000+ baris)
│       ├── routers/
│       │   ├── auth.py              # /api/auth: config, login, logout, me, change-password
│       │   ├── master.py            # /api/warehouses|locators|items|users (ADMIN)
│       │   ├── mobile.py            # /api/m: home, bundle, stock, inbound, outbound, transfer, sync
│       │   ├── movements.py         # /api/movements, /api/stock, /api/sync-transactions, /api/dashboard
│       │   ├── imports.py           # /api/imports: import master Excel (ITEM/WAREHOUSE/LOCATOR/USER)
│       │   ├── reports.py           # /api/reports/{7 laporan}, /api/audit/actions
│       │   ├── sto.py               # /api/sto: STO lifecycle + rekonsiliasi
│       │   ├── sto_mobile.py        # /api/m/sto: counting MH + sync offline
│       │   └── messages.py          # /api/messages (manajer) + /api/m/messages (inbox operator)
│       └── services/
│           ├── stock.py             # SERVICE TUNGGAL: saldo, validasi, create_movement, void_movement
│           ├── export.py            # generator XLSX/CSV/PDF
│           ├── counting.py          # logika counting STO round-based
│           └── recon.py             # rekonsiliasi fisik vs ledger + resolve via ADJUSTMENT
├── frontend/
│   ├── index.html                   # PWA shell
│   ├── labels.html                  # Cetak label QR lokator (vendor/qrcode.js)
│   ├── manifest.webmanifest
│   ├── sw.js                        # Service Worker (cache app shell, offline loading)
│   ├── css/app.css                  # Design system mobile & desktop
│   ├── vendor/
│   │   ├── jsQR.js                  # QR decoder (fallback BarcodeDetector)
│   │   └── qrcode.js                # QR encoder (label)
│   └── js/
│       ├── api.js                   # HTTP client, bearer token, error handler, download
│       ├── ui.js                    # komponen: toast, sheet, confirm, keypad qty, DataTable, badge
│       ├── store.js                 # IndexedDB: bundle cache + antrean offline (movement + counting STO)
│       ├── scanner.js               # QR/barcode scanner (BarcodeDetector / jsQR)
│       ├── mobile.js                # Layar MH (3 tab): Beranda, Scan, Akun + layar opname, stok, sync
│       ├── desktop.js               # Console: dashboard, movements, stok, STO, pesan, koreksi, problems, master, import, laporan, audit
│       └── app.js                   # Router hash, login, deteksi role & perangkat, SW registration
```

---

## 4. Pengguna Sistem (Aktor / User Persona)

Sistem ini memiliki **4 peran** dengan perangkat dan tanggung jawab yang berbeda:

### 4.1 MH — Material Handling (Operator Lapangan)
- **Perangkat**: Smartphone (browser mobile) atau handheld scanner dengan browser.
- **Antarmuka**: Mobile PWA — 3 tab utama: **Beranda**, **Scan**, **Akun**.
- **Konteks pekerjaan**: Petugas fisik gudang yang mengangkat, memindahkan, dan mencatat pergerakan barang langsung di lokasi rak. Sering berada di area dengan sinyal Wi-Fi tidak stabil.
- **Hak akses**:
  - Login dan ganti password.
  - Mencatat **Barang Masuk** (Inbound), **Barang Keluar** (Outbound), **Transfer** antar lokator.
  - Melihat **Saldo Stok** per lokator.
  - Menerima dan membaca **Pesan** dari Admin/Supervisor/Checker.
  - Melaksanakan **Hitung Fisik** (Stock Opname) di lokator yang ditugaskan.
  - Sinkronisasi transaksi offline.
- **Penting**: MH **tidak** dapat mengakses antarmuka desktop (dashboard, laporan, koreksi, master data).

### 4.2 CHECKER — Verifikator & Pengendali Kualitas
- **Perangkat**: PC / Laptop (browser desktop).
- **Antarmuka**: Desktop Console — sidebar navigasi lengkap.
- **Konteks pekerjaan**: Petugas yang memverifikasi keabsahan transaksi, menangani kesalahan, dan bertanggung jawab atas integritas data gudang.
- **Hak akses** (semua hak Supervisor, ditambah):
  - Login, ganti password.
  - Lihat Dashboard, Riwayat Stok, Saldo Stok, Laporan.
  - **Koreksi transaksi**: Void (batalkan) movement yang salah (wajib alasan), buat ADJUSTMENT.
  - **Tangani Transaksi Bermasalah**: Tinjau transaksi offline yang ditolak server (saldo tidak cukup, dsb).
  - **Verifikasi Stock Opname**: Setujui (`ACCEPT`) atau minta hitung ulang (`RECOUNT`) hasil hitung MH.
  - **Selesaikan Selisih STO**: Buat transaksi ADJUSTMENT otomatis untuk selisih fisik vs ledger.
  - Kirim **Pesan Operator** ke MH/Supervisor.

### 4.3 SUPERVISOR — Pengawas Operasional
- **Perangkat**: PC / Laptop (browser desktop).
- **Antarmuka**: Desktop Console — sidebar navigasi lengkap.
- **Konteks pekerjaan**: Manajer operasional yang memantau kinerja gudang, merencanakan jadwal Stock Opname, dan mengirim instruksi ke tim lapangan.
- **Hak akses**:
  - Login, ganti password.
  - Dashboard KPI + chart 7 hari, filter gudang/tanggal.
  - Lihat Riwayat Stok, Saldo Stok, 7 Jenis Laporan (read).
  - **Kelola Stock Opname**: Buat STO, tugaskan lokator ke MH, transisi status STO.
  - Kirim **Pesan Operator** ke MH/Checker (level: INFO, WARN, URGENT).

### 4.4 ADMIN — Konfigurator Sistem
- **Perangkat**: PC / Laptop (browser desktop).
- **Antarmuka**: Desktop Console — sidebar navigasi penuh (semua menu).
- **Konteks pekerjaan**: Administrator sistem yang bertanggung jawab atas konfigurasi, master data, dan keamanan.
- **Hak akses** (penuh — superuser):
  - Semua hak akses Supervisor dan Checker.
  - **Kelola Master Data**: Gudang (CRUD), Lokator (CRUD + generator Zone-Rack-Level), Item (CRUD + lookup), User (CRUD + atur role).
  - **Import Master Excel**: Upload file XLSX untuk ITEM, WAREHOUSE, LOCATOR, USER dengan validasi baris dan preview sebelum commit.
  - **Cetak Label QR Lokator**: Buka `labels.html?warehouse_id=X` untuk mencetak label QR siap tempel di rak.
  - Lihat **Audit Log** seluruh aktivitas sistem.
  - Kirim Pesan Operator.

---

## 5. Skema Database (Ledger-Centric)

Prinsip: **saldo tidak pernah disimpan.** Saldo per `(gudang, item, lokator)` = `SUM(masuk) − SUM(keluar)` dari `stock_movements` di luar baris `voided`.

### Tabel Utama

1. **`roles`, `users`, `user_roles`**: `users.password_hash` (bcrypt), `active`, soft-delete. Multi-role.
2. **`warehouses`**: `code`, `name`, `type` (FG/RM/…), `sto_enabled`, `active`. Ditambah/diubah via UI tanpa ubah kode.
3. **`locators`**: `warehouse_id`, `code` (mis. `A-01-02`), `zone`, `rack`, `level`, `active`, `verification_status` (APPROVED/PENDING/REJECTED). Unik per gudang.
4. **`items`**: unik pada (`code`, `uom`). `name`, `group_code`, `group_name`, `barcode`, `qr_code`, `active`, `verification_status`.
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
9. **`messages`** + **`message_reads`** (Pesan Operator):
   - `messages`: `sender_id`, `title`, `body`, `level` ∈ {`INFO`, `WARN`, `URGENT`}, `target_role` ∈ {`MH`, `CHECKER`, `SUPERVISOR`, `ALL`}, `active`, `created_at`.
   - `message_reads`: `message_id`, `user_id` (PK gabungan), `read_at`.
10. **`excel_imports`, `excel_import_errors`**: riwayat import Excel + baris yang gagal validasi.

### Tabel Stock Opname (Fase 2)

`stock_opnames`, `sto_assignments`, `sto_locators`, `stock_counts`, `stock_count_details`, `stock_recounts` + `services/counting.py` + `services/recon.py` + `routers/sto.py` + `routers/sto_mobile.py`.

---

## 6. Aturan Bisnis Saldo (Service `services/stock.py`)

Semua operasi stok melewati **satu service** agar aturan konsisten:

- **Arah pergerakan**:
  - `INBOUND`: `to_locator` (+), `from_locator` null.
  - `OUTBOUND`: `from_locator` (−), `to_locator` null.
  - `TRANSFER`: `from_locator` (−) dan `to_locator` (+), keduanya wajib dan **berbeda**, satu gudang.
  - `ADJUSTMENT`: arah ditentukan ada/tidaknya `from_locator` / `to_locator`.
- **Stok tidak boleh minus**: Untuk setiap efek keluar (Outbound, sisi keluar Transfer, **void** dari movement yang menambah stok), sistem cek saldo tersedia. Jika negatif → **ditolak (HTTP 409)** dengan pesan yang menyebut saldo tersedia.
- **Konsistensi & locking**: cek saldo + insert dalam **satu transaksi DB**. `_lock_item(...)` memakai `SELECT ... FOR UPDATE` (SQLite: transaksi serial) untuk mencegah race condition.
- **Validasi master**: Item harus `active` dan eligible di gudang; Lokator harus milik gudang yang sama dan `active`.
- **`movement_no`**: `MV-YYYY-000001`, dihitung max+1 per tahun (dalam transaksi).
- **`create_movement(...)`**: membuat baris ledger + audit. **Tidak commit** (commit dilakukan pemanggil).
- **`void_movement(...)`**: menandai `voided`, `voided_by`, `voided_at`, `void_reason` (wajib). Tidak menghapus baris. Bila void menyebabkan saldo minus → **409**.
- **Tidak ada proses approval** untuk transaksi harian.

---

## 7. Role-Based Access Control (RBAC)

| Peran | Antarmuka | Hak Akses |
| :--- | :--- | :--- |
| **ADMIN** | Desktop Console (semua menu) | Penuh: user, gudang, lokator + generator + label QR, master item, import Excel, audit log, kelola STO, semua laporan |
| **SUPERVISOR** | Desktop Console | Dashboard, riwayat stok, laporan, **kelola STO** (buat, penugasan, transisi status), kirim pesan |
| **CHECKER** | Desktop Console | Semua Supervisor + **koreksi** (void/adjust; wajib alasan) + **verifikasi STO & selesaikan selisih** + tangani transaksi bermasalah |
| **MH** | Mobile PWA (3 tab) | Scan transaksi (masuk/keluar/pindah), cek stok, hitung fisik opname, baca pesan, sync offline |

- `require(*roles)` = dependency RBAC FastAPI. `ADMIN` diperlakukan sebagai superuser.
- `Session.hasExact(...)` di frontend untuk pemeriksaan ketat routing desktop vs mobile.
- MH yang login di perangkat desktop akan diarahkan ke tampilan mobile.

---

## 8. Alur Pengalaman Pengguna (User Flow)

### Alur 0: Pertama Kali Login

```
Buka browser → Halaman Login (username + password)
  ↓
  [MH]           → Diarahkan otomatis ke Mobile PWA (#/m)
  [Admin/Sup/Chk] → Diarahkan otomatis ke Desktop Dashboard (#/d/dashboard)
  [Perangkat Mobile siapapun] → Diarahkan ke Mobile PWA
```

**Offline Loading**: Service Worker sudah mengunduh seluruh App Shell (HTML/CSS/JS) di kunjungan pertama. Kunjungan berikutnya akan langsung terbuka dalam hitungan milidetik meskipun tanpa internet.

---

### Alur 1: MH — Barang Masuk (Inbound)

```
Login → Beranda (#/m)
  │  Pilih Gudang Aktif (dropdown)
  ↓
Ketuk tab SCAN (#/m/scan)
  │  Pilih jenis: [Masuk]
  ↓
Scan QR / cari Barang (kamera atau ketik kode/nama)
  │  Sistem menampilkan nama barang, UOM, kode
  ↓
Pilih Lokator Tujuan (dari daftar rak yang tersedia)
  ↓
Input Qty (keypad besar, mobile-friendly)
  ↓
Pilih Ref Type (PO / SURAT_JALAN / LAINNYA) + isi No. Referensi
  ↓
Ketuk SIMPAN
  ├── [Online]  → POST /api/m/inbound → Validasi → Sukses: tampil Movement No.
  └── [Offline] → Disimpan ke antrean IndexedDB → Banner "X transaksi menunggu sync"
                   → Saat online kembali: auto-flush → POST /api/m/sync
                   → OK: antrean dihapus | REJECTED: tampil di Beranda sebagai bermasalah
```

---

### Alur 2: MH — Barang Keluar (Outbound)

```
Scan (#/m/scan) → Pilih jenis: [Keluar]
  ↓
Scan / cari Barang → Sistem tampil saldo tersedia per lokator
  ↓
Pilih Lokator Asal (menampilkan saldo tersedia)
  ↓
Input Qty
  │  Jika Qty > saldo → Ditolak real-time (HTTP 409) + pesan saldo tersedia
  ↓
Pilih Ref Type (DO / SURAT_JALAN / LAINNYA) + isi No. Referensi → SIMPAN
```

---

### Alur 3: MH — Transfer antar Lokator

```
Scan (#/m/scan) → Pilih jenis: [Pindah]
  ↓
Scan / cari Barang
  ↓
Pilih Lokator ASAL (menampilkan saldo tersedia) → Pilih Lokator TUJUAN (wajib berbeda, satu gudang)
  ↓
Input Qty → SIMPAN → Validasi saldo asal → Sukses
```

---

### Alur 4: MH — Membaca Pesan Operator

```
Beranda (#/m)
  │  Badge merah "X baru" tampil di header Pesan
  ↓
Ketuk kartu pesan (INFO / WARN / URGENT)
  │  Pesan terbuka → POST /api/m/messages/{id}/read otomatis
  └── Badge unread berkurang
```

---

### Alur 5: MH — Hitung Fisik Stock Opname

```
Beranda (#/m) → Bagian "Tugas Saya"
  │  Kartu STO aktif ditampilkan (sto_number, gudang, lokator saya, belum selesai)
  ↓
Ketuk kartu STO → Daftar Lokator Tugas (#/m/opname/{sto_id})
  ↓
Pilih satu Lokator → Layar Hitung (#/m/opname/count/{slid})
  │  Scan / cari item → Input Qty fisik → Tambah baris
  │  Ulangi untuk setiap item di rak
  ↓
Ketuk SELESAI → Lokator berubah status WAITING_CHECK
  │  [Offline] → Disimpan antrean → auto-sync saat online
  ↓
Checker di desktop: ACCEPT atau RECOUNT
  └── RECOUNT → Lokator kembali ke IN_PROGRESS → MH hitung ulang (putaran baru)
```

---

### Alur 6: Supervisor — Membuat & Memantau Stock Opname

```
Login → Desktop Dashboard (#/d/dashboard)
  ↓
Menu Stock Opname (#/d/sto)
  │  Daftar STO (filter status/gudang)
  ↓
Tombol "Buat STO Baru"
  │  Isi: nama STO, gudang, tanggal, pilih lokator, penugasan MH → Simpan
  │  Status: DRAFT
  ↓
Transisi Status: DRAFT → OPEN → COUNTING
  │  MH menerima tugas di Beranda
  ↓
(setelah MH selesai hitung) → Transisi: COUNTING → CHECKING
  ↓
(setelah Checker verifikasi) → Transisi: CHECKING → RECONCILIATION
  │  Tab Rekonsiliasi: tampil matriks MATCH / VARIANCE / MISSING / UNEXPECTED
  ↓
Transisi: RECONCILIATION → COMPLETED
  │  Gate: semua lokator ACCEPTED dan issues == 0 (atau gunakan flag `force`)
```

---

### Alur 7: Checker — Koreksi Transaksi

```
Login → Desktop Console
  ↓
Menu Koreksi (#/d/corrections)
  │  Cari movement yang salah (filter gudang, jenis, tanggal, keyword)
  ↓
  [Void] → Isi alasan wajib → Konfirmasi → Baris ledger ditandai voided
  │          Buat movement baru yang benar
  │
  [ADJUSTMENT] → Pilih item, lokator, qty, arah → Simpan
  └── Semua tercatat di audit_logs; baris ledger lama tidak dihapus
```

---

### Alur 8: Checker — Tangani Transaksi Bermasalah

```
Menu Transaksi Bermasalah (#/d/problems)
  │  Daftar sync_transactions dengan result=REJECTED
  │  Tampil: device, user, payload, alasan penolakan (mis. stok minus)
  ↓
Tinjau manual → Coordinator (Supervisor) putuskan:
  ├── Lakukan ADJUSTMENT lebih dulu (tambah stok) → MH retry sync
  └── Discard (MH hapus dari antrean di #/m/sync)
```

---

### Alur 9: Admin — Setup Gudang & Lokator Baru

```
Login → Desktop Console
  ↓
Menu Gudang (#/d/warehouses) → Tambah Gudang (kode, nama, tipe)
  ↓
Menu Locator (#/d/locators) → "Generate Lokator"
  │  Isi: Zone (mis. A, B), Jumlah Rak, Jumlah Level → Generate
  │  Sistem membuat lokator A-01-01, A-01-02, ... dst.
  ↓
Buka labels.html?warehouse_id=X → Cetak label QR lokator → Tempel di rak fisik
```

---

### Alur 10: Admin — Import Master Item dari Excel

```
Menu Import Excel (#/d/imports)
  ↓
Download Template XLSX (tombol "Unduh Template ITEM")
  │  Isi data item di Excel (kolom: code, name, group_code, group_name, uom, barcode)
  ↓
Upload file → Sistem validasi baris (100.000 baris maks)
  │  Preview: tampil baris valid & baris error beserta alasannya
  ↓
Ketuk COMMIT → Data valid di-INSERT ke tabel `items` database
  │  Baris error dilewati dan dicatat di excel_import_errors
  └── Riwayat import tersimpan di menu Import (audit)
```

---

### Alur 11: Supervisor — Kirim Pesan ke Tim Lapangan

```
Menu Pesan Operator (#/d/messages)
  ↓
Tombol "Tulis Pesan" → Isi:
  │  Target: MH / CHECKER / SUPERVISOR / ALL
  │  Level: INFO (biru) / WARN (kuning) / URGENT (merah)
  │  Judul (opsional) + Isi pesan
  ↓
Kirim → POST /api/messages → tersimpan di DB
  └── MH yang sesuai target_role akan melihat pesan di Beranda dengan badge unread
```

---

## 9. API Contracts (FastAPI)

### Autentikasi (`/api/auth`)
- `GET /api/auth/config` → `{demo_mode, app_name, app_subtitle}` (tanpa auth).
- `POST /api/auth/login` → JWT (rate-limited 5x/5 menit). Body: `{username, password}`.
- `POST /api/auth/logout`. `GET /api/auth/me`. `POST /api/auth/change-password`.

### Mobile MH (`/api/m`) — `FIELD = require("MH","CHECKER","SUPERVISOR")`
- `GET /api/m/home` — ringkasan hari ini + **pesan** + **tugas STO** + gudang.
- `GET /api/m/bundle?warehouse_id=` — bundle offline (gudang, lokator APPROVED, item aktif).
- `GET /api/m/stock?warehouse_id=&q=` — daftar saldo.
- `POST /api/m/inbound` / `/outbound` / `/transfer` — catat movement. Body memuat `txn_id` untuk idempotensi.
- `POST /api/m/sync` — batch transaksi offline (diurutkan by timestamp), idempoten.

### Pesan (`/api/messages`) — kirim = `require("SUPERVISOR")`, inbox = pengguna terautentikasi
- `GET /api/m/messages` — inbox operator (pesan yang `target_role` cocok atau `ALL`) + `unread`.
- `POST /api/m/messages/{id}/read` — tandai sudah dibaca.
- `POST /api/messages` — kirim pesan baru (body `title`, `body`, `level`, `target_role`).
- `GET /api/messages?target_role=&page=&size=` — daftar pesan terkirim + jumlah dibaca.
- `DELETE /api/messages/{id}` — non-aktifkan pesan (soft delete).

### Stock Opname Mobile (`/api/m/sto`) — `FIELD = require("MH","CHECKER","SUPERVISOR")`
- `GET /api/m/sto` — STO aktif untuk user (`my_locators`, `my_todo`).
- `GET /api/m/sto/{sto_id}` — detail + daftar lokator tugas.
- `GET /api/m/sto/locators/{slid}` — detail lokator + hasil hitung + riwayat putaran.
- `POST /api/m/sto/locators/{slid}/lines` — simpan hasil hitung (body `item_id`, `qty`, `txn_id`).
- `DELETE /api/m/sto/locators/{slid}/lines/{line_id}` — hapus satu baris hitung.
- `POST /api/m/sto/locators/{slid}/finish` — kirim lokator ke Checker (`WAITING_CHECK`).
- `POST /api/m/sto/locators/{slid}/accept` (**CHECKER**) — setujui (`ACCEPTED`).
- `POST /api/m/sto/locators/{slid}/recount` (**CHECKER**) — minta hitung ulang.
- `POST /api/m/sto/sync` — batch offline STO, idempoten.

### Stock Opname (`/api/sto`) — `MANAGER = require("SUPERVISOR")`, resolve = `require("CHECKER")`
- `GET /api/sto` (list + filter). `GET /api/sto/{id}` (detail + penugasan + progres).
- `POST /api/sto` — buat STO. `POST /{id}/assignments`, `DELETE /{id}/assignments/{aid}`.
- `POST /{id}/status` — transisi status (`force` opsional). `DELETE /{id}`, `POST /{id}/reset-counts`.
- `GET /{id}/locators`, `GET /{id}/locators/{slid}`, `PUT /{id}/locators/{slid}/reassign`.
- `GET /{id}/reconciliation` — matriks fisik vs ledger + ringkasan.
- `POST /{id}/reconciliation/resolve` (**CHECKER**) — selesaikan selisih via ADJUSTMENT.

### Movements / Stok / Dashboard (`/api`) — `WIDE = require("SUPERVISOR","CHECKER")`
- `GET /api/movements`, `GET /api/movements/export`, `GET /api/movements/{id}`.
- `POST /api/movements/{id}/void` (**Checker**) — wajib `reason`.
- `POST /api/movements/adjust` (**Checker**) — buat ADJUSTMENT.
- `GET /api/stock`, `GET /api/stock/export`.
- `GET /api/sync-transactions?result=REJECTED` — transaksi bermasalah.
- `GET /api/dashboard` — KPI + chart 7 hari + filter gudang/tanggal.

### Master (`/api`) — `require("ADMIN")`
- `/api/warehouses` (CRUD + export), `/api/locators` (CRUD + `/generate` + export), `/api/items` (CRUD + `/lookup` + export), `/api/users` (CRUD + export + options).

### Import Master (`/api/imports`) — `require("ADMIN")`
- `POST /api/imports/upload` — preview (jenis: `ITEM`/`WAREHOUSE`/`LOCATOR`/`USER`).
- `GET /api/imports`, `/api/imports/{id}`, `/api/imports/{id}/errors`, `/api/imports/template/{kind}`.
- `POST /api/imports/{id}/commit` — eksekusi baris valid. `POST /api/imports/{id}/cancel`.

### Laporan (`/api/reports`) — `WIDE`, kecuali `audit_log` = `ADMIN`
7 laporan, format JSON / XLSX / CSV / PDF:
1. `stock_balance` — Saldo Stok per gudang/lokator/item.
2. `movement_history` — Riwayat pergerakan lengkap.
3. `inbound` — Barang Masuk.
4. `outbound` — Barang Keluar.
5. `transfer` — Transfer antar lokator.
6. `corrections` — Koreksi & pembatalan (void/ADJUSTMENT).
7. `audit_log` — Audit Log Aktivitas (**hanya ADMIN**).

### Health
- `GET /api/health` → `{"status": "ok"}`.

---

## 10. Sinkronisasi Offline (Idempotensi)

Mekanisme ini memastikan operasi gudang **tidak terhenti** meskipun sinyal hilang di area rak:

1. Setiap transaksi mobile punya `client_txn_id` (UUID v4) di-enqueue ke IndexedDB HP.
2. App Shell (HTML/CSS/JS/scanner library) di-cache oleh Service Worker → aplikasi tetap terbuka dan fungsional tanpa internet.
3. Data master (gudang, lokator, item) di-cache ke IndexedDB saat `loadBundle()` → MH tetap bisa scan dan cari barang offline.
4. `POST /api/m/sync` menerima **batch** (diurutkan by timestamp). Per item:
   - `OK` — dibuat di ledger.
   - `DUPLICATE` — `client_txn_id` sudah ada → tidak digandakan.
   - `REJECTED` — gagal validasi (mis. stok minus) → disimpan di `sync_transactions` dengan `message`.
5. Frontend: `flush()` mengirim antrean, menghapus `OK`/`DUPLICATE`, menandai `REJECTED` (MH bisa retry/discard di #/m/sync).
6. Checker melihat semua transaksi `REJECTED` di menu **Transaksi Bermasalah**.

---

## 11. Fitur Non-Fungsional

1. **Ledger append-only**: baris tidak pernah dihapus; koreksi via void/adjustment.
2. **Integritas saldo**: cek + insert satu transaksi, row lock, anti-minus pada void & sync.
3. **Idempotensi offline**: `client_txn_id` UNIQUE constraint di DB.
4. **Offline-First PWA**: Service Worker cache App Shell (~<2MB) + IndexedDB antrean ringan (~500 Byte/transaksi, auto-purge setelah sync).
5. **Scanner ringan**: `BarcodeDetector` API (hardware-accelerated), fallback `jsQR.js`. Kamera mati otomatis setelah scan berhasil.
6. **Keamanan**: CSP ketat, `nosniff`, anti-framing, GZip, batas ukuran body, HSTS bila HTTPS, rate limit login (5x/5 menit), audit log.
7. **Config identitas**: nama aplikasi dari `APP_NAME`/`APP_SUBTITLE` env var (tidak di-hardcode).

---

## 12. Kredensial Demo

Kata sandi default: **`demo1234`**

| Username | Role | Nama | Penggunaan |
| :--- | :--- | :--- | :--- |
| `admin` | `ADMIN` | Administrator | Master data, user, gudang/lokator/label, import, audit |
| `supervisor01` | `SUPERVISOR` | Sari Supervisor | Dashboard, laporan, kelola STO, kirim pesan |
| `checker01` | `CHECKER` | Citra Checker | Verifikasi, koreksi (void/adjustment), selesaikan selisih STO |
| `mh01` | `MH` | Budi Material Handling | Mobile: masuk/keluar/pindah/sync/opname |
| `mh02` | `MH` | Dewi Material Handling | Mobile: masuk/keluar/pindah/sync/opname |

**Seed data**: Gudang **L21 (PP2 WH FG)**, **L22 (FG Hasbro)**, **L25 (Raw Material)** + lokator contoh + 25.000+ item dari `items_l21.csv` + 8 movement contoh + 2 pesan contoh (satu `ALL` level `INFO`, satu `MH` level `WARN`).

---

## 13. Modul Stock Opname (Fase 2 — AKTIF)

Stock Opname = **cek fisik dibanding saldo ledger**. Rekonsiliasi dihitung *on-the-fly*; tidak ada tabel rekonsiliasi tersimpan.

- **Alur status STO** (`STO_TRANSITIONS`): `DRAFT → OPEN → COUNTING → CHECKING → RECONCILIATION → COMPLETED` (+ `CANCELLED`).
- **Status lokator** (`sto_locators`): `NOT_STARTED → IN_PROGRESS → WAITING_CHECK → ACCEPTED` (atau `RECOUNT`). Counting *round-based*: hasil lama tersimpan sebagai riwayat putaran (`stock_recounts`).
- **Rekonsiliasi** (`services/recon.py`): *expected* = saldo ledger per lokator; *physical* = hasil `StockCount` FINAL. Baris: `MATCH` / `VARIANCE` / `UNEXPECTED` / `MISSING`.
- **Resolusi selisih**: Checker membuat ADJUSTMENT otomatis (`to_locator` bila diff > 0, `from_locator` bila diff < 0). Setelah itu baris menjadi `MATCH`.

---

## 14. Panduan Prompt untuk AI Penerima

```text
Halo AI, saya melampirkan dokumen arsitektur & spesifikasi teknis proyek
"WMS Operasional PT XYZ (Fase 1 + Fase 2 + Fase 3)" dalam Markdown di atas.

Pahami arsitektur, skema database ledger-centric, aturan bisnis saldo,
RBAC 4 peran, alur mobile offline-first, modul Stock Opname, UI mobile
3 halaman (Beranda/Scan/Akun), modul Pesan Operator, dan kontrak API.

Konfirmasikan pemahaman Anda dengan ringkasan 3 pilar:
1. Ledger `stock_movements` sebagai sumber tunggal saldo (anti-minus, append-only, koreksi via void/adjustment).
2. Alur mobile offline idempoten (`client_txn_id` + `/api/m/sync`, Service Worker PWA).
3. RBAC 4 peran (ADMIN/SUPERVISOR/CHECKER/MH) + Stock Opname fisik vs ledger + Pesan Operator.

PENTING: Jangan mengubah konsep inti (ledger-centric, anti-minus, append-only,
RBAC 4 peran, offline-first idempoten). Perubahan bersifat ADITIF.
```

---

## 15. Guardrails — Hal yang TIDAK Boleh Diubah

1. **Ledger-centric**: saldo tetap dihitung dari `stock_movements`; tidak boleh menambah kolom saldo statis.
2. **Anti-minus & append-only**: aturan saldo, void, dan ADJUSTMENT tetap; tidak ada penghapusan permanen baris ledger.
3. **Idempotensi offline**: `client_txn_id` UNIQUE + `/api/m/sync` & `/api/m/sto/sync` tetap.
4. **RBAC 4 peran**: ADMIN/SUPERVISOR/CHECKER/MH tetap; `require()` (ADMIN = superuser) & `Session.hasExact()` tetap.
5. **STO**: alur status & rekonsiliasi on-the-fly (tanpa tabel rekonsiliasi tersimpan) tetap.
6. **Kontrak API Fase 1/2/3**: endpoint lama tidak dihapus; perubahan bersifat **aditif**.
7. **Aditif, bukan destruktif**: pertahankan endpoint & perilaku lama.
8. **Satu sumber kebenaran**: semua mutasi stok melalui `services/stock.py`.
9. **UI Bahasa Indonesia**, tanpa hardcode nama perusahaan (pakai `APP_NAME`/`APP_SUBTITLE`).
10. **MH = mobile saja**; manajer (Admin/Supervisor/Checker) = desktop console.
11. **Tema mobile = 3 tab**; fitur kerja lapangan lain diakses dari Beranda, bukan menambah tab baru.
12. **Bump cache PWA** (`?v=` di `index.html` + `CACHE_NAME` di `sw.js`) setiap mengubah file frontend.
13. **Offline-first**: transaksi MH harus tetap bisa di-enqueue dan idempoten.

---

## 16. Status Verifikasi Terakhir

- `pytest -q` (backend/tests/test_flow.py) → **1 passed** (E2E: auth/RBAC, saldo, void, koreksi, sync, laporan, import, STO Fase 2, pesan Fase 3, tugas di `/api/m/home`).
- `node --check` semua JS frontend → **OK**.
- Database SQLite `backend/sto.db` → dibuat otomatis saat startup / via `init_db.py` (menggunakan `SQLAlchemy create_all`).
- Smoke HTTP (Docker, port 8010 / lokal 8000) → `/api/health` `{"status":"ok"}`, `/api/auth/config` mengembalikan `app_name`.
