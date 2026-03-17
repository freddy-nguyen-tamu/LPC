import base64
import json
import os
from cryptography.fernet import Fernet, InvalidToken
from config import FERNET_KEY


def get_fernet() -> Fernet:
    key = FERNET_KEY.strip().encode()
    if not key:
        env_key = os.environ.get("FERNET_KEY")
        if env_key:
            key = env_key.encode()
    if not key:
        raise RuntimeError(
            "FERNET_KEY is not set. Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key)


def encrypt_payload(payload: dict) -> str:
    data = json.dumps(payload).encode("utf-8")
    token = get_fernet().encrypt(data)
    return token.decode("utf-8")


def decrypt_payload(token: str) -> dict:
    try:
        raw = get_fernet().decrypt(token.encode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted token") from exc