# Diagram Model — WMS Operasional (Fase 1 + Fase 2 + Fase 3)

> Pelengkap visual untuk `project.md` (SSOT). Semua diagram memakai **Mermaid**.
> Cara render: GitHub (otomatis), VS Code (ekstensi *Markdown Preview Mermaid Support*), Obsidian, atau tempel blok ke https://mermaid.live.

Daftar diagram:
1. [Use Case](#1-use-case-diagram)
2. [Arsitektur / Komponen](#2-arsitektur--komponen)
3. [ERD / Data Model](#3-erd--data-model)
4. [State Diagram — STO & StoLocator](#4-state-diagram--sto--stolocator)
5. [Sequence — Transaksi Barang (offline-first)](#5-sequence--transaksi-barang-offline-first)
6. [Sequence — Stock Opname end-to-end](#6-sequence--stock-opname-end-to-end)
7. [Sequence — Pesan Operator](#7-sequence--pesan-operator)
8. [Activity — Alur Scan MH terpadu](#8-activity--alur-scan-mh-terpadu)
9. [Activity — Sinkronisasi Offline](#9-activity--sinkronisasi-offline)
10. [Deployment (Docker)](#10-deployment-docker)

---

## 1. Use Case Diagram

```mermaid
flowchart LR
  admin((ADMIN))
  sup((SUPERVISOR))
  chk((CHECKER))
  mh((MH))

  subgraph SYS["Sistem WMS Operasional"]
    uc_login([Login / Logout])
    uc_master([Kelola Master<br/>Gudang, Lokator, Item, User])
    uc_import([Import Master Excel])
    uc_label([Cetak Label QR Lokator])
    uc_audit([Lihat Audit Log])
    uc_dash([Dashboard & Laporan])
    uc_koreksi([Riwayat Stok & Koreksi<br/>void / ADJUSTMENT])
    uc_problems([Tangani Transaksi Bermasalah])
    uc_sto_kelola([Kelola STO<br/>buat, penugasan, status])
    uc_sto_verify([Verifikasi STO &<br/>Selesaikan Selisih])
    uc_pesan_kirim([Kirim Pesan Operator])
    uc_scan([Transaksi Barang<br/>Masuk / Keluar / Pindah])
    uc_hitung([Hitung Fisik Lokator])
    uc_cekstok([Cek Stok])
    uc_pesan_baca([Baca Pesan])
    uc_sync([Sinkronisasi Offline])
  end

  admin --> uc_login
  admin --> uc_master
  admin --> uc_import
  admin --> uc_label
  admin --> uc_audit
  admin --> uc_sto_kelola
  admin --> uc_dash
  admin --> uc_pesan_kirim
  admin --> uc_koreksi

  sup --> uc_login
  sup --> uc_dash
  sup --> uc_sto_kelola
  sup --> uc_koreksi
  sup --> uc_pesan_kirim

  chk --> uc_login
  chk --> uc_koreksi
  chk --> uc_problems
  chk --> uc_sto_verify
  chk --> uc_pesan_kirim

  mh --> uc_login
  mh --> uc_scan
  mh --> uc_hitung
  mh --> uc_cekstok
  mh --> uc_pesan_baca
  mh --> uc_sync

  uc_scan -.->|include| uc_sync
  uc_hitung -.->|include| uc_sync
```

---

## 2. Arsitektur / Komponen

```mermaid
flowchart TB
  subgraph FE["Frontend (Vanilla JS, PWA)"]
    appjs["app.js<br/>router + login"]
    mobile["mobile.js<br/>MH: Beranda / Scan / Akun"]
    desktop["desktop.js<br/>console manajer"]
    store["store.js<br/>IndexedDB cache + antrean offline"]
    ui["ui.js<br/>komponen + ikon + badge"]
    api_js["api.js<br/>HTTP client"]
  end

  subgraph BE["Backend (FastAPI)"]
    routers["routers/<br/>auth, master, mobile, movements,<br/>imports, reports, sto, sto_mobile, messages"]
    services["services/<br/>stock.py, counting.py, recon.py, export.py"]
    core["core.py<br/>JWT, RBAC, audit, rate-limit"]
    models["models.py<br/>SQLAlchemy 2.0"]
  end

  DB[("SQLite / MySQL<br/>ledger stock_movements")]

  mobile --> appjs
  desktop --> appjs
  appjs --> api_js
  mobile --> store
  mobile --> ui
  desktop --> ui
  api_js -->|REST /api| routers
  routers --> services
  routers --> core
  services --> models
  core --> models
  models --> DB
```

---

## 3. ERD / Data Model

```mermaid
erDiagram
  ROLE ||--o{ USER_ROLE : "diberikan"
  USER ||--o{ USER_ROLE : "memiliki"
  USER ||--o{ STOCK_MOVEMENT : "membuat"
  USER ||--o{ AUDIT_LOG : "mencatat"
  USER ||--o{ SYNC_TRANSACTION : "mengirim"
  USER ||--o{ MESSAGE : "mengirim"
  USER ||--o{ MESSAGE_READ : "membaca"
  MESSAGE ||--o{ MESSAGE_READ : "dibaca"

  WAREHOUSE ||--o{ LOCATOR : "punya"
  WAREHOUSE ||--o{ ITEM_WAREHOUSE : "eligibilitas"
  ITEM ||--o{ ITEM_WAREHOUSE : "dipetakan"
  WAREHOUSE ||--o{ STOCK_MOVEMENT : "di"
  ITEM ||--o{ STOCK_MOVEMENT : "barang"
  LOCATOR ||--o{ STOCK_MOVEMENT : "dari"
  LOCATOR ||--o{ STOCK_MOVEMENT : "ke"

  WAREHOUSE ||--o{ STOCK_OPNAME : "untuk"
  STOCK_OPNAME ||--o{ STO_ASSIGNMENT : "penugasan"
  STOCK_OPNAME ||--o{ STO_LOCATOR : "daftar"
  LOCATOR ||--o{ STO_LOCATOR : "dihitung"
  STO_LOCATOR ||--o{ STOCK_COUNT : "putaran"
  STOCK_COUNT ||--o{ STOCK_COUNT_DETAIL : "baris"
  ITEM ||--o{ STOCK_COUNT_DETAIL : "item"
  STO_LOCATOR ||--o{ STOCK_RECOUNT : "riwayat"

  USER {
    int id PK
    string username
    string full_name
    string password_hash
    bool active
    bool deleted
  }
  ROLE {
    int id PK
    string code
    string name
  }
  USER_ROLE {
    int user_id FK
    int role_id FK
  }
  WAREHOUSE {
    int id PK
    string code
    string name
    string type
    bool sto_enabled
    bool active
  }
  LOCATOR {
    int id PK
    int warehouse_id FK
    string code
    string zone
    string rack
    string level
    string verification_status
  }
  ITEM {
    int id PK
    string code
    string name
    string uom
    string barcode
    string qr_code
    bool active
  }
  ITEM_WAREHOUSE {
    int item_id FK
    int warehouse_id FK
  }
  STOCK_MOVEMENT {
    int id PK
    string movement_no
    string movement_type
    int warehouse_id FK
    int item_id FK
    float qty
    int from_locator_id FK
    int to_locator_id FK
    string ref_type
    string ref_no
    string client_txn_id
    bool voided
    int corrects_movement_id FK
  }
  SYNC_TRANSACTION {
    int id PK
    string txn_id
    int user_id FK
    string txn_type
    string result
    string message
  }
  MESSAGE {
    int id PK
    int sender_id FK
    string title
    string body
    string level
    string target_role
    bool active
  }
  MESSAGE_READ {
    int message_id FK
    int user_id FK
    datetime read_at
  }
  STOCK_OPNAME {
    int id PK
    string sto_number
    date sto_date
    int warehouse_id FK
    string status
  }
  STO_ASSIGNMENT {
    int id PK
    int sto_id FK
    int counter_id FK
    int checker_id FK
  }
  STO_LOCATOR {
    int id PK
    int sto_id FK
    int locator_id FK
    int counter_id FK
    int checker_id FK
    string status
    int round
  }
  STOCK_COUNT {
    int id PK
    int sto_locator_id FK
    string status
  }
  STOCK_COUNT_DETAIL {
    int id PK
    int count_id FK
    int item_id FK
    float qty
  }
  STOCK_RECOUNT {
    int id PK
    int sto_locator_id FK
    string reason
    string note
  }
  AUDIT_LOG {
    int id PK
    int user_id FK
    string action
    string object_type
    string object_id
    string ip
  }
```

> Catatan: `STOCK_MOVEMENT` adalah **ledger** (append-only). Saldo = `SUM(masuk) − SUM(keluar)` di luar baris `voided`. Rekonsiliasi STO **tidak** disimpan sebagai tabel — dihitung *on-the-fly* dari ledger + hasil `STOCK_COUNT_DETAIL`.

---

## 4. State Diagram — STO & StoLocator

**Status Stock Opname (`STO_TRANSITIONS`):**

```mermaid
stateDiagram-v2
  [*] --> DRAFT
  DRAFT --> OPEN
  DRAFT --> CANCELLED
  OPEN --> COUNTING
  OPEN --> CANCELLED
  COUNTING --> CHECKING
  COUNTING --> CANCELLED
  CHECKING --> RECONCILIATION
  CHECKING --> COUNTING
  CHECKING --> CANCELLED
  RECONCILIATION --> COMPLETED
  RECONCILIATION --> CHECKING
  RECONCILIATION --> CANCELLED
  COMPLETED --> [*]
  CANCELLED --> [*]
```

> Gate `RECONCILIATION`/`COMPLETED`: semua lokator `ACCEPTED` dan `issues == 0` (kecuali `force`).

**Status Lokator (`StoLocator`):**

```mermaid
stateDiagram-v2
  [*] --> NOT_STARTED
  NOT_STARTED --> IN_PROGRESS : MH menambah baris hitung
  IN_PROGRESS --> IN_PROGRESS : MH menambah baris
  IN_PROGRESS --> WAITING_CHECK : MH selesai
  WAITING_CHECK --> ACCEPTED : Checker terima
  WAITING_CHECK --> RECOUNT : Checker minta hitung ulang
  RECOUNT --> IN_PROGRESS : MH hitung ulang
  ACCEPTED --> [*]
```

---

## 5. Sequence — Transaksi Barang (offline-first)

```mermaid
sequenceDiagram
  actor MH
  participant App as Mobile PWA
  participant IDB as IndexedDB
  participant API as FastAPI /api/m
  participant SVC as services/stock.py
  participant DB as DB

  MH->>App: Scan item, pilih lokator, isi qty
  alt Online
    App->>API: POST /api/m/{inbound|outbound|transfer}
    API->>SVC: create_movement(...)
    SVC->>DB: cek saldo + insert (satu transaksi)
    alt saldo cukup
      DB-->>SVC: ok
      SVC-->>API: movement
      API-->>App: movement_no
      App-->>MH: Sukses
    else akan minus
      SVC-->>API: 409 "saldo tersedia ..."
      API-->>App: error
      App-->>MH: Ditolak
    end
  else Offline
    App->>IDB: enqueue(client_txn_id, payload)
    App-->>MH: Tersimpan offline
    Note over App,IDB: Saat kembali online -> flush()
    App->>API: POST /api/m/sync [batch, urut timestamp]
    API->>DB: cek client_txn_id (idempoten)
    API-->>App: OK / DUPLICATE / REJECTED
  end
```

---

## 6. Sequence — Stock Opname end-to-end

```mermaid
sequenceDiagram
  actor SUP as Supervisor/Admin
  actor MH
  actor CHK as Checker
  participant API as FastAPI
  participant SVC as services/counting|recon
  participant DB as DB

  SUP->>API: POST /api/sto (assign counter + checker)
  SUP->>API: POST /api/sto/{id}/status OPEN
  SUP->>API: POST /api/sto/{id}/status COUNTING
  MH->>API: GET /api/m/sto/{id}
  MH->>API: POST /api/m/sto/locators/{slid}/lines (qty)
  API->>SVC: add_line (round-based)
  MH->>API: POST /api/m/sto/locators/{slid}/finish
  API->>DB: status WAITING_CHECK
  CHK->>API: POST .../accept  (atau .../recount)
  API->>DB: status ACCEPTED
  SUP->>API: POST /api/sto/{id}/status CHECKING
  SUP->>API: POST /api/sto/{id}/status RECONCILIATION
  SUP->>API: GET /api/sto/{id}/reconciliation
  API->>SVC: compare(fisik vs ledger) on-the-fly
  SVC-->>API: MATCH / VARIANCE / MISSING / UNEXPECTED
  CHK->>API: POST /api/sto/{id}/reconciliation/resolve
  API->>SVC: resolve -> create ADJUSTMENT
  SVC->>DB: insert STOCK_MOVEMENT (ADJUSTMENT)
  SUP->>API: POST /api/sto/{id}/status COMPLETED
```

---

## 7. Sequence — Pesan Operator

```mermaid
sequenceDiagram
  actor MGR as Admin/Supervisor/Checker
  actor MH
  participant API as FastAPI
  participant DB as DB

  MGR->>API: POST /api/messages (target_role, level, body)
  API->>DB: insert MESSAGE
  API-->>MGR: ok
  MH->>API: GET /api/m/home
  API->>DB: inbox(user) + tasks
  API-->>MH: messages + unread + tasks
  MH->>API: POST /api/m/messages/{id}/read
  API->>DB: insert MESSAGE_READ
  API-->>MH: ok (unread berkurang)
```

---

## 8. Activity — Alur Scan MH terpadu

```mermaid
flowchart TD
  start([Mulai]) --> tab{Pilih jenis transaksi}
  tab -->|Masuk| scan
  tab -->|Keluar| scan
  tab -->|Pindah| scan
  scan[Scan / cari Barang] --> loc{Pilih lokator}
  loc -->|Masuk| loc_to[Lokator tujuan]
  loc -->|Keluar| loc_from[Lokator asal]
  loc -->|Pindah| loc_both[Lokator asal + tujuan]
  loc_to --> qty
  loc_from --> qty
  loc_both --> qty
  qty[Input qty keypad] --> ref[Pilih ref type/no + catatan]
  ref --> submit[Simpan]
  submit --> online{Online?}
  online -->|Ya| api[POST /api/m/...]
  api --> ok{Valid?}
  ok -->|Ya| done([Sukses + movement_no])
  ok -->|Tidak| err[Tolak: saldo tersedia]
  err --> qty
  online -->|Tidak| queue[Enqueue IndexedDB]
  queue --> done2([Tersimpan offline])
```

---

## 9. Activity — Sinkronisasi Offline

```mermaid
flowchart TD
  start([flush]) --> loop{Ada antrean?}
  loop -->|Tidak| end([Selesai])
  loop -->|Ya| send[POST /api/m/sync atau /api/m/sto/sync]
  send --> res{Hasil per txn}
  res -->|OK| del[Hapus dari antrean]
  res -->|DUPLICATE| del
  res -->|REJECTED| keep[Tandai ditolak + pesan]
  del --> loop
  keep --> loop
  end --> retry{Ada yang ditolak?}
  retry -->|Ya| menu([Retry / Discard oleh MH])
  retry -->|Tidak| selesai([Selesai])
```

---

## 10. Deployment (Docker)

```mermaid
flowchart TB
  subgraph Client["Perangkat Pengguna"]
    B1["Browser Mobile<br/>(MH / PWA)"]
    B2["Browser Desktop<br/>(Admin/Supervisor/Checker)"]
  end

  subgraph Host["Docker Host"]
    subgraph C["Container: sto-pp2-app-new"]
      UVI["Uvicorn + FastAPI<br/>:8000"]
      STAT["StaticFiles<br/>/app/frontend"]
    end
    VOL[("Volume sto-pp2-data<br/>/app/backend/data<br/>sto.db + log")]
    HC["Healthcheck<br/>GET /api/health"]
  end

  B1 -->|HTTP :APP_PORT| UVI
  B2 -->|HTTP :APP_PORT| UVI
  UVI --> STAT
  UVI --> VOL
  HC -.-> UVI
```
