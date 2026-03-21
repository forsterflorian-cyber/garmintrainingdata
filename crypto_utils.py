import base64
import hashlib
import os
from functools import lru_cache
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from runtime_config import require_env


@lru_cache(maxsize=1)
def get_cipher() -> Fernet:
    """
    Get cached Fernet cipher with proper key derivation.
    Uses PBKDF2 with SHA256 and 100,000 iterations (OWASP recommended minimum).
    """
    secret = require_env("APP_SECRET_KEY", context="Garmin credential encryption")
    
    # Get salt from environment or use a default (should be unique per deployment)
    salt_env = os.getenv("APP_SECRET_SALT")
    if salt_env:
        salt = salt_env.encode()
    else:
        # Generate a deterministic salt from the secret (not ideal but backward compatible)
        salt = hashlib.sha256(secret.encode()).digest()[:16]
    
    # Use PBKDF2 for proper key derivation
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,  # OWASP recommended minimum for 2024+
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return Fernet(key)


def encrypt(text: str) -> str:
    """
    Encrypt text using Fernet symmetric encryption.
    The encrypted text includes a timestamp and is URL-safe base64 encoded.
    """
    if not text:
        raise ValueError("Text to encrypt cannot be empty")
    
    cipher = get_cipher()
    encrypted = cipher.encrypt(text.encode())
    return encrypted.decode()


def decrypt(text: str) -> str:
    """
    Decrypt Fernet-encrypted text.
    Raises ValueError if decryption fails or token is invalid/expired.
    """
    if not text:
        raise ValueError("Text to decrypt cannot be empty")
    
    cipher = get_cipher()
    try:
        decrypted = cipher.decrypt(text.encode())
        return decrypted.decode()
    except Exception as exc:
        # Don't expose internal error details
        raise ValueError("Decryption failed: invalid or corrupted data") from exc


def encrypt_with_context(text: str, context: str = "") -> str:
    """
    Encrypt text with additional context for audit purposes.
    Context is not encrypted but can be used for logging/debugging.
    """
    encrypted = encrypt(text)
    if context:
        # Log encryption event (without exposing the actual data)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Data encrypted with context: {context[:50]}...")
    return encrypted


def rotate_encryption(old_encrypted: str, new_cipher: Fernet) -> str:
    """
    Re-encrypt data with a new cipher (for key rotation).
    This is a placeholder for future key rotation implementation.
    """
    # First decrypt with old cipher
    old_cipher = get_cipher()
    decrypted = old_cipher.decrypt(old_encrypted.encode()).decode()
    
    # Then encrypt with new cipher
    return new_cipher.encrypt(decrypted.encode()).decode()
