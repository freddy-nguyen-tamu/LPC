import os
import io
import sqlite3
import uuid
import socket
import secrets
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    send_from_directory,
    abort,
)
import qrcode

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTGOING_DIR = BASE_DIR / "outgoing"
DB_PATH = DATA_DIR / "app.db"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
OUTGOING_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4 GB
app.config["SECRET_KEY"] = os.environ.get("APP_SECRET", secrets.token_hex(32))

PAIR_CODE_TTL_MINUTES = 10
DOWNLOAD_TOKEN_TTL_MINUTES = 60
PHONE_POLL_SECONDS = 4


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pair_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_token TEXT NOT NULL UNIQUE,
            device_name TEXT NOT NULL,
            platform TEXT,
            last_seen_at TEXT,
            created_at TEXT NOT NULL,
            linked_at TEXT NOT NULL,
            pair_session_id INTEGER,
            FOREIGN KEY(pair_session_id) REFERENCES pair_sessions(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL,
            filename TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mime_type TEXT,
            device_id INTEGER,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            download_token TEXT,
            download_expires_at TEXT,
            downloaded_at TEXT,
            FOREIGN KEY(device_id) REFERENCES devices(id)
        )
        """
    )

    conn.commit()
    conn.close()


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def iso_in_future(minutes: int):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def parse_iso(value: str):
    return datetime.fromisoformat(value)


def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        sock.close()
    return ip


def build_base_url():
    host = os.environ.get("APP_HOST", get_local_ip())
    port = int(os.environ.get("APP_PORT", 5000))
    return f"http://{host}:{port}"


def create_pair_session():
    pair_code = secrets.token_urlsafe(24)
    created_at = utc_now_iso()
    expires_at = iso_in_future(PAIR_CODE_TTL_MINUTES)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO pair_sessions (pair_code, created_at, expires_at)
        VALUES (?, ?, ?)
        """,
        (pair_code, created_at, expires_at),
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id, pair_code


def get_active_pair_session(pair_code: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM pair_sessions
        WHERE pair_code = ?
        """,
        (pair_code,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    if row["consumed_at"] is not None:
        return None

    if parse_iso(row["expires_at"]) < datetime.now(timezone.utc):
        return None

    return row


def upsert_device(device_name: str, platform: str, pair_session_id: int):
    device_token = secrets.token_urlsafe(32)
    now = utc_now_iso()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO devices (
            device_token, device_name, platform, last_seen_at, created_at, linked_at, pair_session_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (device_token, device_name, platform, now, now, now, pair_session_id),
    )
    device_id = cur.lastrowid

    cur.execute(
        "UPDATE pair_sessions SET consumed_at = ? WHERE id = ?",
        (now, pair_session_id),
    )

    conn.commit()
    conn.close()
    return device_id, device_token


def get_device_by_token(device_token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM devices WHERE device_token = ?", (device_token,))
    row = cur.fetchone()
    conn.close()
    return row


def touch_device(device_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE devices SET last_seen_at = ? WHERE id = ?",
        (utc_now_iso(), device_id),
    )
    conn.commit()
    conn.close()


def allowed_file(filename: str):
    return bool(filename and filename.strip())


def unique_stored_name(filename: str):
    safe = secure_filename(filename)
    if not safe:
        safe = f"file_{uuid.uuid4().hex}"
    return f"{uuid.uuid4().hex}_{safe}"


def create_transfer_record(direction, filename, stored_name, size_bytes, mime_type, device_id, status):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transfers (
            direction, filename, stored_name, size_bytes, mime_type, device_id,
            status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            direction,
            filename,
            stored_name,
            size_bytes,
            mime_type,
            device_id,
            status,
            utc_now_iso(),
        ),
    )
    transfer_id = cur.lastrowid
    conn.commit()
    conn.close()
    return transfer_id


def mark_transfer_completed(transfer_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE transfers SET status = ?, completed_at = ? WHERE id = ?",
        ("completed", utc_now_iso(), transfer_id),
    )
    conn.commit()
    conn.close()


def create_download_job(device_id: int, filename: str, saved_path: Path):
    size_bytes = saved_path.stat().st_size
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    stored_name = saved_path.name
    download_token = secrets.token_urlsafe(32)
    expires_at = iso_in_future(DOWNLOAD_TOKEN_TTL_MINUTES)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transfers (
            direction, filename, stored_name, size_bytes, mime_type, device_id,
            status, created_at, download_token, download_expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "pc_to_phone",
            filename,
            stored_name,
            size_bytes,
            mime_type,
            device_id,
            "queued",
            utc_now_iso(),
            download_token,
            expires_at,
        ),
    )
    transfer_id = cur.lastrowid
    conn.commit()
    conn.close()
    return transfer_id, download_token


def list_devices():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.*, (
            SELECT COUNT(*) FROM transfers t WHERE t.device_id = d.id
        ) AS transfer_count
        FROM devices d
        ORDER BY d.last_seen_at DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_recent_transfers(limit=20):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT t.*, d.device_name
        FROM transfers t
        LEFT JOIN devices d ON d.id = t.device_id
        ORDER BY t.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


@app.route("/")
def laptop_dashboard():
    base_url = build_base_url()
    session_id, pair_code = create_pair_session()
    phone_url = f"{base_url}/phone?pair={pair_code}"
    devices = list_devices()
    transfers = list_recent_transfers()
    return render_template(
        "laptop.html",
        phone_url=phone_url,
        pair_code=pair_code,
        devices=devices,
        transfers=transfers,
        poll_seconds=PHONE_POLL_SECONDS,
    )


@app.route("/qr")
def qr_image():
    phone_url = request.args.get("url", "")
    if not phone_url:
        abort(400, "Missing url")

    img = qrcode.make(phone_url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@app.route("/phone")
def phone_page():
    pair_code = request.args.get("pair", "")
    return render_template("phone.html", pair_code=pair_code, poll_seconds=PHONE_POLL_SECONDS)


@app.post("/api/pair")
def api_pair():
    payload = request.get_json(force=True)
    pair_code = payload.get("pair_code", "").strip()
    device_name = payload.get("device_name", "Phone").strip() or "Phone"
    platform = payload.get("platform", "unknown").strip()

    session_row = get_active_pair_session(pair_code)
    if not session_row:
        return jsonify({"ok": False, "error": "Pair code is invalid or expired."}), 400

    device_id, device_token = upsert_device(device_name, platform, session_row["id"])
    return jsonify(
        {
            "ok": True,
            "device_token": device_token,
            "device_id": device_id,
            "message": "Phone linked successfully.",
        }
    )


@app.post("/api/phone/upload")
def api_phone_upload():
    device_token = request.form.get("device_token", "")
    device = get_device_by_token(device_token)
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file found in request."}), 400

    file = request.files["file"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"ok": False, "error": "Invalid file name."}), 400

    stored_name = unique_stored_name(file.filename)
    save_path = UPLOAD_DIR / stored_name
    file.save(save_path)
    size_bytes = save_path.stat().st_size
    mime_type = file.mimetype or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

    transfer_id = create_transfer_record(
        direction="phone_to_pc",
        filename=file.filename,
        stored_name=stored_name,
        size_bytes=size_bytes,
        mime_type=mime_type,
        device_id=device["id"],
        status="completed",
    )
    mark_transfer_completed(transfer_id)
    touch_device(device["id"])

    return jsonify(
        {
            "ok": True,
            "message": "Upload complete.",
            "filename": file.filename,
            "size_bytes": size_bytes,
        }
    )


@app.get("/api/laptop/devices")
def api_laptop_devices():
    rows = list_devices()
    result = []
    for row in rows:
        result.append(
            {
                "id": row["id"],
                "device_name": row["device_name"],
                "platform": row["platform"],
                "last_seen_at": row["last_seen_at"],
                "linked_at": row["linked_at"],
                "transfer_count": row["transfer_count"],
            }
        )
    return jsonify({"ok": True, "devices": result})


@app.get("/api/laptop/transfers")
def api_laptop_transfers():
    rows = list_recent_transfers()
    result = []
    for row in rows:
        result.append(
            {
                "id": row["id"],
                "direction": row["direction"],
                "filename": row["filename"],
                "size_bytes": row["size_bytes"],
                "status": row["status"],
                "device_name": row["device_name"],
                "created_at": row["created_at"],
            }
        )
    return jsonify({"ok": True, "transfers": result})


@app.post("/api/laptop/send")
def api_laptop_send():
    device_id = request.form.get("device_id", type=int)
    upload = request.files.get("file")

    if not device_id:
        return jsonify({"ok": False, "error": "Missing device id."}), 400

    if not upload or upload.filename == "":
        return jsonify({"ok": False, "error": "No file selected."}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
    device = cur.fetchone()
    conn.close()

    if not device:
        return jsonify({"ok": False, "error": "Device not found."}), 404

    stored_name = unique_stored_name(upload.filename)
    save_path = OUTGOING_DIR / stored_name
    upload.save(save_path)

    transfer_id, download_token = create_download_job(device_id, upload.filename, save_path)
    touch_device(device_id)

    return jsonify(
        {
            "ok": True,
            "message": "File queued for phone download.",
            "transfer_id": transfer_id,
            "download_token": download_token,
        }
    )


@app.get("/api/phone/pending")
def api_phone_pending():
    device_token = request.args.get("device_token", "")
    device = get_device_by_token(device_token)
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, filename, size_bytes, mime_type, created_at, download_token
        FROM transfers
        WHERE device_id = ?
          AND direction = 'pc_to_phone'
          AND status = 'queued'
          AND download_expires_at IS NOT NULL
          AND download_expires_at > ?
        ORDER BY id DESC
        """,
        (device["id"], utc_now_iso()),
    )
    rows = cur.fetchall()
    conn.close()

    touch_device(device["id"])

    jobs = []
    for row in rows:
        jobs.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "size_bytes": row["size_bytes"],
                "mime_type": row["mime_type"],
                "created_at": row["created_at"],
                "download_url": f"/api/phone/download/{row['download_token']}",
            }
        )

    return jsonify({"ok": True, "jobs": jobs})


@app.get("/api/phone/download/<download_token>")
def api_phone_download(download_token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM transfers WHERE download_token = ?",
        (download_token,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        abort(404)

    if row["status"] not in {"queued", "completed"}:
        conn.close()
        abort(404)

    if row["download_expires_at"] is None or parse_iso(row["download_expires_at"]) < datetime.now(timezone.utc):
        conn.close()
        abort(410)

    file_path = OUTGOING_DIR / row["stored_name"]
    if not file_path.exists():
        conn.close()
        abort(404)

    cur.execute(
        """
        UPDATE transfers
        SET status = ?, downloaded_at = ?, completed_at = ?
        WHERE id = ?
        """,
        ("completed", utc_now_iso(), utc_now_iso(), row["id"]),
    )
    conn.commit()
    conn.close()

    return send_from_directory(
        OUTGOING_DIR,
        row["stored_name"],
        as_attachment=True,
        download_name=row["filename"],
        mimetype=row["mime_type"] or "application/octet-stream",
    )


@app.get("/api/phone/me")
def api_phone_me():
    device_token = request.args.get("device_token", "")
    device = get_device_by_token(device_token)
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    touch_device(device["id"])
    return jsonify(
        {
            "ok": True,
            "device": {
                "id": device["id"],
                "device_name": device["device_name"],
                "platform": device["platform"],
                "linked_at": device["linked_at"],
                "last_seen_at": device["last_seen_at"],
            },
        }
    )


if __name__ == "__main__":
    init_db()
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("APP_PORT", 5000))
    app.run(host=host, port=port, debug=True)