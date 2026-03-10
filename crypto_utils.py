import base64
from cryptography.fernet import Fernet
import os
import hashlib

def get_cipher():
    secret = os.environ["APP_SECRET_KEY"]
    key = hashlib.sha256(secret.encode()).digest()
    key = base64.urlsafe_b64encode(key)
    return Fernet(key)

def encrypt(text: str) -> str:
    cipher = get_cipher()
    return cipher.encrypt(text.encode()).decode()

def decrypt(text: str) -> str:
    cipher = get_cipher()
    return cipher.decrypt(text.encode()).decode()