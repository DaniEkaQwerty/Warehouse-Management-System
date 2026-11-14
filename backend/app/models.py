"""Normalized schema. Totals are always derived (SUM of stock_count_details), never stored."""
from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ROLES = ["ADMIN", "SUPERVISOR", "CHECKER", "MH"]
MOVEMENT_TYPES = ["INBOUND", "OUTBOUND", "TRANSFER", "ADJUSTMENT"]
REF_TYPES = ["PO", "SURAT_JALAN", "DO", "LAINNYA"]
STO_STATUSES = ["DRAFT", "OPEN", "COUNTING", "CHECKING", "RECONCILIATION", "COMPLETED", "CANCELLED"]
STO_TRANSITIONS = {
    "DRAFT": ["OPEN", "CANCELLED"],
    "OPEN": ["COUNTING", "CANCELLED"],
    "COUNTING": ["CHECKING", "CANCELLED"],
    "CHECKING": ["RECONCILIATION", "COUNTING", "CANCELLED"],
    "RECONCILIATION": ["COMPLETED", "CHECKING", "CANCELLED"],
    "COMPLETED": [],
    "CANCELLED": [],
}
LOCATOR_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "WAITING_CHECK", "ACCEPTED", "RECOUNT"]
COUNT_STATUSES = ["DRAFT", "SUBMITTED", "VERIFIED", "RECOUNT", "FINAL"]
VERIFICATION_STATUSES = ["APPROVED", "PENDING", "REJECTED"]


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------------------------------------------------------- users / roles
class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)  # soft delete
    user_roles: Mapped[list["UserRole"]] = relationship(cascade="all, delete-orphan", lazy="selectin")

    @property
    def roles(self):
        return sorted(ur.role.code for ur in self.user_roles)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    role: Mapped[Role] = relationship(lazy="joined")


# ---------------------------------------------------------------- master data
class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(40), default="FG")
    sto_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Locator(Base, TimestampMixin):
    __tablename__ = "locators"
    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_locator_wh_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    zone: Mapped[str | None] = mapped_column(String(20))
    rack: Mapped[str | None] = mapped_column(String(20))
    level: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verification_status: Mapped[str] = mapped_column(String(15), default="APPROVED", index=True)  # APPROVED | PENDING | REJECTED
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verification_note: Mapped[str | None] = mapped_column(String(255))
    warehouse: Mapped[Warehouse] = relationship(lazy="joined")


class Item(Base, TimestampMixin):
    """One row per item code + UOM. The same code may exist in several UOMs (e.g. PCS and SHT)."""
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("code", "uom", name="uq_item_code_uom"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    group_code: Mapped[str | None] = mapped_column(String(30))
    group_name: Mapped[str | None] = mapped_column(String(120))
    uom: Mapped[str] = mapped_column(String(15))
    qr_code: Mapped[str | None] = mapped_column(String(120), unique=True)  # optional
    barcode: Mapped[str | None] = mapped_column(String(60), index=True)  # optional
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verification_status: Mapped[str] = mapped_column(String(15), default="APPROVED", index=True)  # APPROVED | PENDING | REJECTED
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verification_note: Mapped[str | None] = mapped_column(String(255))
    warehouses: Mapped[list["ItemWarehouse"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class ItemWarehouse(Base):
    """Warehouse eligibility. No rows for an item = eligible for every warehouse."""
    __tablename__ = "item_warehouses"
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), primary_key=True)


# ---------------------------------------------------------------- STO
class StockOpname(Base, TimestampMixin):
    __tablename__ = "stock_opnames"
    id: Mapped[int] = mapped_column(primary_key=True)
    sto_number: Mapped[str] = mapped_column(String(40), unique=True)
    sto_date: Mapped[date] = mapped_column(Date)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    description: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    warehouse: Mapped[Warehouse] = relationship(lazy="joined")
    assignments: Mapped[list["StoAssignment"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class StoAssignment(Base, TimestampMixin):
    """Team + locator range. Expanded into sto_locators (one active counter per locator)."""
    __tablename__ = "sto_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    sto_id: Mapped[int] = mapped_column(ForeignKey("stock_opnames.id", ondelete="CASCADE"), index=True)
    locator_from: Mapped[str] = mapped_column(String(40))
    locator_to: Mapped[str] = mapped_column(String(40))
    captain_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    checker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class StoLocator(Base, TimestampMixin):
    __tablename__ = "sto_locators"
    __table_args__ = (UniqueConstraint("sto_id", "locator_id", name="uq_sto_locator"),
                      Index("ix_stoloc_counter", "sto_id", "counter_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    sto_id: Mapped[int] = mapped_column(ForeignKey("stock_opnames.id", ondelete="CASCADE"), index=True)
    locator_id: Mapped[int] = mapped_column(ForeignKey("locators.id"))
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("sto_assignments.id", ondelete="SET NULL"))
    captain_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    checker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="NOT_STARTED", index=True)
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    recount_reason: Mapped[str | None] = mapped_column(String(60))
    recount_note: Mapped[str | None] = mapped_column(String(255))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    locator: Mapped[Locator] = relationship(lazy="joined")


# ---------------------------------------------------------------- counting
class StockCount(Base, TimestampMixin):
    """One physical count round for a locator. round_no 1 = original, 2+ = recounts. Never overwritten."""
    __tablename__ = "stock_counts"
    __table_args__ = (UniqueConstraint("sto_locator_id", "round_no", name="uq_count_round"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sto_locator_id: Mapped[int] = mapped_column(ForeignKey("sto_locators.id", ondelete="CASCADE"), index=True)
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(15), default="DRAFT")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(10), default="MOBILE")  # MOBILE | EXCEL
    details: Mapped[list["StockCountDetail"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class StockCountDetail(Base):
    __tablename__ = "stock_count_details"
    __table_args__ = (UniqueConstraint("stock_count_id", "item_id", "sheet_no", name="uq_detail_sheet"),
                      Index("ix_detail_item", "item_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_count_id: Mapped[int] = mapped_column(ForeignKey("stock_counts.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    sheet_no: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[float] = mapped_column(Numeric(16, 3))
    client_txn_id: Mapped[str | None] = mapped_column(String(64), unique=True)  # idempotency
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    item: Mapped[Item] = relationship(lazy="joined")


class StockRecount(Base):
    __tablename__ = "stock_recounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    sto_locator_id: Mapped[int] = mapped_column(ForeignKey("sto_locators.id", ondelete="CASCADE"), index=True)
    original_count_id: Mapped[int] = mapped_column(ForeignKey("stock_counts.id"))
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(String(255))
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    new_round_no: Mapped[int] = mapped_column(Integer)


# ---------------------------------------------------------------- stock ledger
class StockMovement(Base):
    """Append-only ledger. Stock balances are always derived from this table, never stored.

    inbound:  to_locator_id set, from_locator_id NULL
    outbound: from_locator_id set, to_locator_id NULL
    transfer: both set
    adjustment: one of the two set (positive = to, negative = from)
    """
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_movement_stock", "warehouse_id", "item_id"),
                      Index("ix_movement_created", "created_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    movement_no: Mapped[str] = mapped_column(String(30), unique=True)
    movement_type: Mapped[str] = mapped_column(String(15), index=True)  # INBOUND | OUTBOUND | TRANSFER | ADJUSTMENT
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    qty: Mapped[float] = mapped_column(Numeric(16, 3))  # always positive
    from_locator_id: Mapped[int | None] = mapped_column(ForeignKey("locators.id"))
    to_locator_id: Mapped[int | None] = mapped_column(ForeignKey("locators.id"))
    ref_type: Mapped[str | None] = mapped_column(String(15))  # PO | SURAT_JALAN | DO | LAINNYA
    ref_no: Mapped[str | None] = mapped_column(String(60))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    device_id: Mapped[str | None] = mapped_column(String(64))
    client_txn_id: Mapped[str | None] = mapped_column(String(64), unique=True)  # idempotency
    voided: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    void_reason: Mapped[str | None] = mapped_column(String(255))
    corrects_movement_id: Mapped[int | None] = mapped_column(ForeignKey("stock_movements.id"))
    warehouse: Mapped[Warehouse] = relationship(lazy="joined")
    item: Mapped[Item] = relationship(lazy="joined")
    from_locator: Mapped["Locator | None"] = relationship(foreign_keys=[from_locator_id], lazy="joined")
    to_locator: Mapped["Locator | None"] = relationship(foreign_keys=[to_locator_id], lazy="joined")
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by], lazy="joined")


# ---------------------------------------------------------------- excel import
class ExcelImport(Base):
    __tablename__ = "excel_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(15))  # ITEM | LOCATOR | WAREHOUSE | USER
    filename: Mapped[str] = mapped_column(String(255))
    sto_id: Mapped[int | None] = mapped_column(ForeignKey("stock_opnames.id"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(12), default="PREVIEW")  # PREVIEW | COMMITTED | CANCELLED
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    warning_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    options: Mapped[dict | None] = mapped_column(JSON)
    parsed: Mapped[list | None] = mapped_column(JSON)  # normalized valid rows awaiting commit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime)


class ExcelImportError(Base):
    __tablename__ = "excel_import_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("excel_imports.id", ondelete="CASCADE"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(8))  # ERROR | WARNING
    column_name: Mapped[str | None] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(String(300))


# ---------------------------------------------------------------- audit / sync
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    username: Mapped[str | None] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(40), index=True)
    object_type: Mapped[str | None] = mapped_column(String(40))
    object_id: Mapped[str | None] = mapped_column(String(60))
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class SyncTransaction(Base):
    """Server-side record of processed offline transactions (idempotency / duplicate prevention)."""
    __tablename__ = "sync_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    txn_id: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[str | None] = mapped_column(String(64))
    txn_type: Mapped[str] = mapped_column(String(30))
    client_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    payload: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[str] = mapped_column(String(10))  # OK | REJECTED
    message: Mapped[str | None] = mapped_column(String(300))
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=now)
