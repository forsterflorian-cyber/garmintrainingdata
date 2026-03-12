import base64
import hashlib
from cryptography.fernet import Fernet

from runtime_config import require_env

def get_cipher():
    secret = require_env("APP_SECRET_KEY", context="Garmin credential encryption")
    key = hashlib.sha256(secret.encode()).digest()
    key = base64.urlsafe_b64encode(key)
    return Fernet(key)

def encrypt(text: str) -> str:
    cipher = get_cipher()
    return cipher.encrypt(text.encode()).decode()

def decrypt(text: str) -> str:
    cipher = get_cipher()
    return cipher.decrypt(text.encode()).decode()
