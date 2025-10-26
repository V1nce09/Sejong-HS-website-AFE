import os
import base64
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _load_aes_key() -> bytes:
    key_b64 = os.environ.get("APP_AES_KEY", "")
    if not key_b64:
        raise RuntimeError("APP_AES_KEY is not set")
    key = base64.urlsafe_b64decode(key_b64)
    if len(key) not in (16, 24, 32):
        raise RuntimeError("APP_AES_KEY must decode to 16/24/32 bytes")
    return key


def aesgcm_encrypt(plaintext: bytes, aad: Optional[bytes] = None, kid: str = "v1") -> str:
    key = _load_aes_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return f"{kid}.{_b64e(nonce)}.{_b64e(ct)}"


def aesgcm_decrypt(token: str, aad: Optional[bytes] = None) -> bytes:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid token format")
    _, n_s, ct_s = parts
    nonce, ct = _b64d(n_s), _b64d(ct_s)
    key = _load_aes_key()
    return AESGCM(key).decrypt(nonce, ct, aad)
