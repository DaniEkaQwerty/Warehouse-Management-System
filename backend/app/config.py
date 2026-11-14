"""Application configuration (environment variables, with safe dev defaults)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

# Optional .env support without extra dependency (checks backend/.env then root/.env)
for _env_path in (BASE_DIR / ".env", ROOT_DIR / ".env"):
    try:
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass

# Production: mysql+pymysql://sto:password@127.0.0.1:3306/sto?charset=utf8mb4
_raw_db_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'sto.db'}")
if os.name == "nt" and _raw_db_url.startswith("sqlite:////app/"):
    # Running directly on Windows host where Docker's /app/backend/data mount path is not present
    _raw_db_url = f"sqlite:///{BASE_DIR / 'sto.db'}"

DATABASE_URL = _raw_db_url
APP_NAME = os.getenv("APP_NAME", "WMS")
APP_SUBTITLE = os.getenv("APP_SUBTITLE", "Warehouse Management System")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-please-use-32+chars")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "300"))
SEED_DEMO = os.getenv("SEED_DEMO", "1") == "1"

_raw_log_file = os.getenv("LOG_FILE", str(BASE_DIR / "app_errors.log"))
if os.name == "nt" and _raw_log_file.startswith("/app/"):
    _raw_log_file = str(BASE_DIR / "app_errors.log")
LOG_FILE = _raw_log_file
