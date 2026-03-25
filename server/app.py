import base64
import io
import math
import mimetypes
import secrets
import socket
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import qrcode
from flask import Flask, abort, jsonify, render_template, request, send_file
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

from config import (
    APP_HOST,
    APP_PORT,
    APP_PUBLIC_HOST,
    APP_SECRET,
    DEFAULT_CHUNK_SIZE,
    DOWNLOAD_TOKEN_TTL_MINUTES,
    MAX_CONTENT_LENGTH,
    OUTGOING_DIR,
    PAIR_CODE_TTL_MINUTES,
    PARTIAL_DIR,
    TLS_CERT_FILE,
    TLS_KEY_FILE,
    TLS_MODE,
    UPLOAD_DIR,
)
from crypto_utils import decrypt_payload, encrypt_payload
from db import execute, init_db, query_all, query_one, utc_now_iso
from hash_utils import sha256_bytes, sha256_file

app = Flask(__name__)
app.config["SECRET_KEY"] = APP_SECRET
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")


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


def build_base_url() -> str:
    host = APP_PUBLIC_HOST or get_local_ip()
    return f"https://{host}:{APP_PORT}"


def build_ssl_context():
    if TLS_MODE == "adhoc":
        return "adhoc"
    if TLS_MODE == "files":
        if not TLS_CERT_FILE or not TLS_KEY_FILE:
            raise RuntimeError("TLS_MODE=files requires TLS_CERT_FILE and TLS_KEY_FILE")
        return (TLS_CERT_FILE, TLS_KEY_FILE)
    raise RuntimeError("Unsupported TLS_MODE")


def make_safe_name(filename: str) -> str:
    safe = secure_filename(filename)
    return safe or f"file_{uuid.uuid4().hex}"


def partial_dir_for_transfer(transfer_id: int) -> Path:
    d = PARTIAL_DIR / str(transfer_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def emit_dashboard_update():
    devices = [dict(x) for x in query_all("SELECT * FROM devices ORDER BY last_seen_at DESC")]
    transfers = [
        dict(x)
        for x in query_all(
            """
            SELECT t.*, d.device_name
            FROM transfers t
            LEFT JOIN devices d ON d.id = t.device_id
            ORDER BY t.id DESC
            LIMIT 50
            """
        )
    ]
    socketio.emit("dashboard_update", {"devices": devices, "transfers": transfers})


def create_pair_session():
    created_at = utc_now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=PAIR_CODE_TTL_MINUTES)).isoformat()
    payload = {
        "nonce": secrets.token_urlsafe(16),
        "created_at": created_at,
        "expires_at": expires_at,
    }
    encrypted_token = encrypt_payload(payload)
    pair_session_id = execute(
        "INSERT INTO pair_sessions (encrypted_token, created_at, expires_at) VALUES (?, ?, ?)",
        (encrypted_token, created_at, expires_at),
    )
    return pair_session_id, encrypted_token


def validate_pair_token(encrypted_token: str):
    row = query_one("SELECT * FROM pair_sessions WHERE encrypted_token = ?", (encrypted_token,))
    if not row or row["consumed_at"]:
        return None
    try:
        payload = decrypt_payload(encrypted_token)
    except ValueError:
        return None
    if parse_iso(payload["expires_at"]) < datetime.now(timezone.utc):
        return None
    return row


def create_device(device_name: str, platform: str, pair_session_id: int):
    now = utc_now_iso()
    device_token = secrets.token_urlsafe(32)
    device_id = execute(
        """
        INSERT INTO devices (device_token, device_name, platform, created_at, linked_at, last_seen_at, pair_session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (device_token, device_name, platform, now, now, now, pair_session_id),
    )
    execute("UPDATE pair_sessions SET consumed_at = ? WHERE id = ?", (now, pair_session_id))
    emit_dashboard_update()
    return device_id, device_token


def get_device_by_token(device_token: str):
    return query_one("SELECT * FROM devices WHERE device_token = ?", (device_token,))


def touch_device(device_id: int):
    execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (utc_now_iso(), device_id))


def register_transfer(
    direction: str,
    filename: str,
    stored_name: str,
    mime_type: str,
    size_bytes: int,
    chunk_size: int,
    total_chunks: int,
    device_id: int,
    status: str,
    file_sha256=None,
    download_token=None,
    download_expires_at=None,
):
    return execute(
        """
        INSERT INTO transfers (
            direction, filename, stored_name, mime_type, size_bytes, chunk_size, total_chunks,
            uploaded_chunks, file_sha256, status, device_id, created_at, updated_at, download_token, download_expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            direction,
            filename,
            stored_name,
            mime_type,
            size_bytes,
            chunk_size,
            total_chunks,
            file_sha256,
            status,
            device_id,
            utc_now_iso(),
            utc_now_iso(),
            download_token,
            download_expires_at,
        ),
    )


def get_transfer_chunk_count(transfer_id: int) -> int:
    row = query_one("SELECT COUNT(*) AS c FROM transfer_chunks WHERE transfer_id = ?", (transfer_id,))
    return int(row["c"] if row else 0)


def update_transfer_progress(transfer_id: int):
    uploaded_chunks = get_transfer_chunk_count(transfer_id)
    transfer = query_one("SELECT * FROM transfers WHERE id = ?", (transfer_id,))
    if not transfer:
        return None
    status = "receiving"
    if uploaded_chunks >= transfer["total_chunks"]:
        status = "verifying"
    execute(
        "UPDATE transfers SET uploaded_chunks = ?, status = ?, updated_at = ? WHERE id = ?",
        (uploaded_chunks, status, utc_now_iso(), transfer_id),
    )
    emit_dashboard_update()
    return query_one("SELECT * FROM transfers WHERE id = ?", (transfer_id,))


def assemble_uploaded_file(transfer_id: int):
    transfer = query_one("SELECT * FROM transfers WHERE id = ?", (transfer_id,))
    if not transfer:
        return
    chunk_dir = partial_dir_for_transfer(transfer_id)
    final_path = UPLOAD_DIR / transfer["stored_name"]
    with open(final_path, "wb") as out_f:
        for idx in range(transfer["total_chunks"]):
            chunk_path = chunk_dir / f"{idx}.part"
            if not chunk_path.exists():
                raise FileNotFoundError(f"Missing chunk {idx}")
            with open(chunk_path, "rb") as in_f:
                out_f.write(in_f.read())

    actual_hash = sha256_file(final_path)
    if transfer["file_sha256"] and actual_hash != transfer["file_sha256"]:
        execute(
            "UPDATE transfers SET status = ?, updated_at = ? WHERE id = ?",
            ("checksum_failed", utc_now_iso(), transfer_id),
        )
        emit_dashboard_update()
        raise ValueError("Final file checksum mismatch")

    execute(
        "UPDATE transfers SET status = ?, updated_at = ?, completed_at = ?, file_sha256 = COALESCE(file_sha256, ?) WHERE id = ?",
        ("completed", utc_now_iso(), utc_now_iso(), actual_hash, transfer_id),
    )
    emit_dashboard_update()


@app.route("/")
def dashboard():
    _, encrypted_token = create_pair_session()
    phone_url = f"{build_base_url()}/pair?token={encrypted_token}"
    return render_template(
        "dashboard.html",
        phone_url=phone_url,
        token=encrypted_token,
        chunk_size=DEFAULT_CHUNK_SIZE,
    )


@app.route("/qr")
def qr_code():
    url = request.args.get("url", "")
    if not url:
        abort(400)
    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@app.get("/api/dashboard")
def api_dashboard():
    devices = [dict(x) for x in query_all("SELECT * FROM devices ORDER BY last_seen_at DESC")]
    transfers = [
        dict(x)
        for x in query_all(
            "SELECT t.*, d.device_name FROM transfers t LEFT JOIN devices d ON d.id = t.device_id ORDER BY t.id DESC LIMIT 50"
        )
    ]
    return jsonify({"ok": True, "devices": devices, "transfers": transfers})


@app.post("/api/pair")
def api_pair():
    payload = request.get_json(force=True)
    encrypted_token = payload.get("encrypted_token", "").strip()
    device_name = payload.get("device_name", "").strip() or "Android"
    platform = payload.get("platform", "Android").strip()

    pair_session = validate_pair_token(encrypted_token)
    if not pair_session:
        return jsonify({"ok": False, "error": "Invalid or expired pairing token."}), 400

    device_id, device_token = create_device(device_name, platform, pair_session["id"])
    return jsonify(
        {
            "ok": True,
            "device_id": device_id,
            "device_token": device_token,
            "server_url": build_base_url(),
            "message": "Pairing complete.",
        }
    )


@app.post("/api/phone/upload/init")
def api_phone_upload_init():
    payload = request.get_json(force=True)
    device = get_device_by_token(payload.get("device_token", ""))
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    filename = payload["filename"]
    size_bytes = int(payload["size_bytes"])
    chunk_size = int(payload.get("chunk_size", DEFAULT_CHUNK_SIZE))
    total_chunks = int(math.ceil(size_bytes / chunk_size)) if size_bytes > 0 else 1
    stored_name = f"{uuid.uuid4().hex}_{make_safe_name(filename)}"
    mime_type = payload.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_sha256 = payload.get("file_sha256")

    transfer_id = register_transfer(
        direction="phone_to_pc",
        filename=filename,
        stored_name=stored_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        device_id=device["id"],
        status="initialized",
        file_sha256=file_sha256,
    )
    touch_device(device["id"])
    emit_dashboard_update()
    return jsonify({"ok": True, "transfer_id": transfer_id, "chunk_size": chunk_size, "total_chunks": total_chunks})


@app.get("/api/phone/upload/status/<int:transfer_id>")
def api_phone_upload_status(transfer_id: int):
    device = get_device_by_token(request.args.get("device_token", ""))
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    transfer = query_one("SELECT * FROM transfers WHERE id = ? AND device_id = ?", (transfer_id, device["id"]))
    if not transfer:
        return jsonify({"ok": False, "error": "Transfer not found."}), 404

    rows = query_all("SELECT chunk_index FROM transfer_chunks WHERE transfer_id = ? ORDER BY chunk_index", (transfer_id,))
    uploaded = [int(r["chunk_index"]) for r in rows]
    return jsonify(
        {
            "ok": True,
            "transfer_id": transfer_id,
            "uploaded_chunks": uploaded,
            "uploaded_count": len(uploaded),
            "total_chunks": transfer["total_chunks"],
            "status": transfer["status"],
        }
    )


@app.post("/api/phone/upload/chunk")
def api_phone_upload_chunk():
    transfer_id = int(request.form["transfer_id"])
    chunk_index = int(request.form["chunk_index"])
    sent_chunk_sha256 = request.form.get("chunk_sha256", "").strip()

    device = get_device_by_token(request.form.get("device_token", ""))
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    transfer = query_one("SELECT * FROM transfers WHERE id = ? AND device_id = ?", (transfer_id, device["id"]))
    if not transfer:
        return jsonify({"ok": False, "error": "Transfer not found."}), 404

    file = request.files.get("chunk")
    if not file:
        return jsonify({"ok": False, "error": "Missing chunk."}), 400

    data = file.read()
    actual_sha256 = sha256_bytes(data)
    if sent_chunk_sha256 and actual_sha256 != sent_chunk_sha256:
        return jsonify({"ok": False, "error": "Chunk checksum mismatch."}), 400

    chunk_dir = partial_dir_for_transfer(transfer_id)
    chunk_path = chunk_dir / f"{chunk_index}.part"
    with open(chunk_path, "wb") as f:
        f.write(data)

    execute(
        "INSERT OR REPLACE INTO transfer_chunks (transfer_id, chunk_index, byte_size, chunk_sha256, received_at) VALUES (?, ?, ?, ?, ?)",
        (transfer_id, chunk_index, len(data), actual_sha256, utc_now_iso()),
    )

    updated = update_transfer_progress(transfer_id)
    if updated and int(updated["uploaded_chunks"]) >= int(updated["total_chunks"]):
        try:
            assemble_uploaded_file(transfer_id)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    touch_device(device["id"])
    socketio.emit(
        "transfer_progress",
        {
            "transfer_id": transfer_id,
            "uploaded_chunks": get_transfer_chunk_count(transfer_id),
            "total_chunks": transfer["total_chunks"],
            "direction": transfer["direction"],
            "filename": transfer["filename"],
        },
    )
    return jsonify({"ok": True, "transfer_id": transfer_id, "chunk_index": chunk_index, "server_chunk_sha256": actual_sha256})


@app.post("/api/laptop/send/init")
def api_laptop_send_init():
    device_id = int(request.form["device_id"])
    file = request.files.get("file")
    if not file:
        return jsonify({"ok": False, "error": "Missing file."}), 400

    device = query_one("SELECT * FROM devices WHERE id = ?", (device_id,))
    if not device:
        return jsonify({"ok": False, "error": "Device not found."}), 404

    filename = file.filename
    chunk_size = int(request.form.get("chunk_size", DEFAULT_CHUNK_SIZE))
    stored_name = f"{uuid.uuid4().hex}_{make_safe_name(filename)}"
    save_path = OUTGOING_DIR / stored_name
    file.save(save_path)
    size_bytes = save_path.stat().st_size
    total_chunks = int(math.ceil(size_bytes / chunk_size)) if size_bytes > 0 else 1
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_sha256 = sha256_file(save_path)
    download_token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=DOWNLOAD_TOKEN_TTL_MINUTES)).isoformat()

    transfer_id = register_transfer(
        direction="pc_to_phone",
        filename=filename,
        stored_name=stored_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        device_id=device_id,
        status="queued",
        file_sha256=file_sha256,
        download_token=download_token,
        download_expires_at=expires_at,
    )
    emit_dashboard_update()
    socketio.emit("phone_job_available", {"device_id": device_id})
    return jsonify({"ok": True, "transfer_id": transfer_id})


@app.get("/api/phone/jobs")
def api_phone_jobs():
    device = get_device_by_token(request.args.get("device_token", ""))
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    rows = query_all(
        """
        SELECT id, filename, mime_type, size_bytes, total_chunks, chunk_size, status, created_at, file_sha256
        FROM transfers
        WHERE device_id = ? AND direction = 'pc_to_phone' AND download_expires_at > ?
        ORDER BY id DESC
        """,
        (device["id"], utc_now_iso()),
    )
    touch_device(device["id"])
    return jsonify({"ok": True, "jobs": [dict(r) for r in rows]})


@app.get("/api/phone/download/status/<int:transfer_id>")
def api_phone_download_status(transfer_id: int):
    device = get_device_by_token(request.args.get("device_token", ""))
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    transfer = query_one(
        "SELECT * FROM transfers WHERE id = ? AND device_id = ? AND direction = 'pc_to_phone'",
        (transfer_id, device["id"]),
    )
    if not transfer:
        return jsonify({"ok": False, "error": "Transfer not found."}), 404

    return jsonify(
        {
            "ok": True,
            "transfer_id": transfer_id,
            "filename": transfer["filename"],
            "chunk_size": transfer["chunk_size"],
            "total_chunks": transfer["total_chunks"],
            "size_bytes": transfer["size_bytes"],
            "file_sha256": transfer["file_sha256"],
        }
    )


@app.get("/api/phone/download/chunk/<int:transfer_id>/<int:chunk_index>")
def api_phone_download_chunk(transfer_id: int, chunk_index: int):
    device = get_device_by_token(request.args.get("device_token", ""))
    if not device:
        return jsonify({"ok": False, "error": "Unauthorized device."}), 401

    transfer = query_one(
        "SELECT * FROM transfers WHERE id = ? AND device_id = ? AND direction = 'pc_to_phone'",
        (transfer_id, device["id"]),
    )
    if not transfer:
        return jsonify({"ok": False, "error": "Transfer not found."}), 404

    file_path = OUTGOING_DIR / transfer["stored_name"]
    if not file_path.exists():
        abort(404)

    chunk_size = int(transfer["chunk_size"])
    offset = chunk_index * chunk_size
    with open(file_path, "rb") as f:
        f.seek(offset)
        data = f.read(chunk_size)

    return jsonify(
        {
            "ok": True,
            "chunk_index": chunk_index,
            "chunk_sha256": sha256_bytes(data),
            "data_base64": base64.b64encode(data).decode("ascii"),
            "is_last": chunk_index + 1 >= int(transfer["total_chunks"]),
        }
    )


@app.get("/pair")
def pair_landing():
    token = request.args.get("token", "")
    return jsonify(
        {
            "message": "Use the Android app QR scanner or paste this token.",
            "encrypted_token": token,
            "server": build_base_url(),
        }
    )


@socketio.on("connect")
def handle_connect():
    emit("connected", {"ok": True})


if __name__ == "__main__":
    init_db()
    socketio.run(app, host=APP_HOST, port=APP_PORT, debug=True, ssl_context=build_ssl_context())