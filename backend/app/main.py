from contextlib import asynccontextmanager
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, OperationalError

from . import config
from .database import Base, SessionLocal, engine, ensure_schema_migrations
from .routers import auth, imports, master, mobile, movements, reports, sto, sto_mobile
from .seed import seed

# technical errors go to a log file for administrators, never to the end user
_h = RotatingFileHandler(config.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.getLogger("sto").addHandler(_h)
logging.getLogger("sto").setLevel(logging.INFO)
log = logging.getLogger("sto")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    ensure_schema_migrations(engine)
    if config.SEED_DEMO:
        with SessionLocal() as db:
            seed(db)
    yield


app = FastAPI(title=config.APP_NAME, version="2.0.0", docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)

MAX_BODY_SIZE = (config.MAX_UPLOAD_MB + 5) * 1024 * 1024


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # 1. Reject path traversal or hidden/dot file access attempts early
    p = request.url.path
    if "/." in p or "\\." in p or ".." in p:
        return JSONResponse({"detail": "Akses ditolak."}, status_code=403)

    # 2. Enforce max request payload size to protect against memory exhaustion DoS
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_SIZE:
                return JSONResponse({"detail": "Ukuran data melebihi batas maksimal."}, status_code=413)
        except ValueError:
            pass

    resp = await call_next(request)

    # 3. Security Headers (OWASP recommendations)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    resp.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")

    # Content-Security-Policy
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "media-src 'self' blob:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none';"
    )
    resp.headers.setdefault("Content-Security-Policy", csp)

    # HSTS if accessed via HTTPS or behind SSL termination proxy
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if proto == "https":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    # Cache controls
    if p.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    elif p.endswith(("sw.js", ".html")) or p == "/":
        resp.headers["Cache-Control"] = "no-cache"

    return resp


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    fields = ", ".join(sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")}))
    return JSONResponse({"detail": f"Data tidak valid ({fields}). Periksa kembali isian Anda."}, status_code=422)


@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError):
    log.error("IntegrityError %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse({"detail": "Data gagal disimpan karena duplikat atau masih terhubung dengan data lain."},
                        status_code=409)


@app.exception_handler(OperationalError)
async def db_handler(request: Request, exc: OperationalError):
    log.error("OperationalError %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse({"detail": "Server sedang sibuk. Silakan coba lagi."}, status_code=503)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Data gagal diproses. Silakan coba lagi."}, status_code=500)


for r in (auth.router, master.router, mobile.router, movements.router, imports.router, reports.router,
          sto.router, sto_mobile.router):
    app.include_router(r)


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}


FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
