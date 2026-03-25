import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTGOING_DIR = BASE_DIR / "outgoing"
PARTIAL_DIR = BASE_DIR / "partials"
CERT_DIR = BASE_DIR / "certs"
DB_PATH = DATA_DIR / "app.db"

for d in (DATA_DIR, UPLOAD_DIR, OUTGOING_DIR, PARTIAL_DIR, CERT_DIR):
    d.mkdir(exist_ok=True)

APP_SECRET = os.environ.get("APP_SECRET", "change-me-in-production")
FERNET_KEY = os.environ.get("FERNET_KEY", "")
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", "5000"))
APP_PUBLIC_HOST = os.environ.get("APP_PUBLIC_HOST", "")
MAX_CONTENT_LENGTH = 8 * 1024 * 1024 * 1024
PAIR_CODE_TTL_MINUTES = 10
DOWNLOAD_TOKEN_TTL_MINUTES = 24 * 60
DEFAULT_CHUNK_SIZE = 1024 * 1024
TLS_MODE = os.environ.get("TLS_MODE", "adhoc")   # adhoc | files
TLS_CERT_FILE = os.environ.get("TLS_CERT_FILE", "")
TLS_KEY_FILE = os.environ.get("TLS_KEY_FILE", "")