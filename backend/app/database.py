from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):  # enforce foreign keys on SQLite
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def ensure_schema_migrations(eng=engine):
    """Idempotent schema migration helper to add new columns to existing databases."""
    insp = inspect(eng)
    table_names = set(insp.get_table_names())
    migrations = {
        "locators": [
            ("verification_status", "VARCHAR(15) NOT NULL DEFAULT 'APPROVED'"),
            ("created_by", "INTEGER NULL"),
            ("verified_by", "INTEGER NULL"),
            ("verified_at", "DATETIME NULL"),
            ("verification_note", "VARCHAR(255) NULL"),
        ],
        "items": [
            ("verification_status", "VARCHAR(15) NOT NULL DEFAULT 'APPROVED'"),
            ("created_by", "INTEGER NULL"),
            ("verified_by", "INTEGER NULL"),
            ("verified_at", "DATETIME NULL"),
            ("verification_note", "VARCHAR(255) NULL"),
        ],
    }
    with eng.begin() as conn:
        for table, cols in migrations.items():
            if table not in table_names:
                continue
            existing_cols = {c["name"] for c in insp.get_columns(table)}
            for col_name, col_def in cols:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
