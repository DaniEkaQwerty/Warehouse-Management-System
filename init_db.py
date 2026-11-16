import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.database import engine, Base, SessionLocal, ensure_schema_migrations
from app.seed import seed
from app import config

print("Creating tables in database:", config.DATABASE_URL)
Base.metadata.create_all(engine)
ensure_schema_migrations(engine)

print("Seeding initial data (roles, users, warehouses, locators, items)...")
with SessionLocal() as db:
    seed(db)

print("SUCCESS! Database initialized at:", config.DATABASE_URL)
