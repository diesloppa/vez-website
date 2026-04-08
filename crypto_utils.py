import base64
import getpass
import json
import os
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DEFAULT_ITERATIONS = 310_000


def get_password(required: bool = False, prompt: str = "Пароль для шифрования данных: ") -> str | None:
    for env_name in ("SITE_PASSWORD", "DATA_PASSWORD"):
        value = os.environ.get(env_name)
        if value:
            return value

    if sys.stdin.isatty():
        value = getpass.getpass(prompt)
        if value:
            return value

    if required:
        raise RuntimeError("Password is required. Set SITE_PASSWORD or DATA_PASSWORD.")
    return None


def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_bytes(data: bytes, password: str, iterations: int = DEFAULT_ITERATIONS) -> dict:
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = _derive_key(password, salt, iterations)
    ciphertext = AESGCM(key).encrypt(iv, data, None)
    return {
        "version": 1,
        "alg": "AES-GCM",
        "kdf": "PBKDF2-SHA256",
        "iterations": iterations,
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_bytes(payload: dict, password: str) -> bytes:
    salt = base64.b64decode(payload["salt"])
    iv = base64.b64decode(payload["iv"])
    ciphertext = base64.b64decode(payload["ciphertext"])
    iterations = int(payload.get("iterations", DEFAULT_ITERATIONS))
    key = _derive_key(password, salt, iterations)
    return AESGCM(key).decrypt(iv, ciphertext, None)


def load_json(plain_path: str, encrypted_path: str | None = None, password: str | None = None) -> dict:
    if os.path.exists(plain_path):
        with open(plain_path, encoding="utf-8") as f:
            return json.load(f)

    if encrypted_path and os.path.exists(encrypted_path):
        secret = password or get_password(required=True)
        with open(encrypted_path, encoding="utf-8") as f:
            payload = json.load(f)
        return json.loads(decrypt_bytes(payload, secret).decode("utf-8"))

    raise FileNotFoundError(f"Neither {plain_path} nor {encrypted_path} exists")


def dump_encrypted_json(data: dict, output_path: str, password: str, *, compact: bool = False) -> bool:
    plain = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    if os.path.exists(output_path):
        try:
            with open(output_path, encoding="utf-8") as f:
                current_payload = json.load(f)
            if decrypt_bytes(current_payload, password) == plain:
                return False
        except Exception:
            pass

    payload = encrypt_bytes(plain, password)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=None if compact else 2)
        if not compact:
            f.write("\n")
    return True
