"""
SEMA: encryption-at-rest for client-supplied credentials (data_sources_add_
prompt.md). Every DB password an admin types into the self-service SQL DB
wizard is encrypted with Fernet (symmetric, authenticated) before it ever
touches disk -- sema_core.client_connections_store stores only the
ciphertext, never plaintext.

The key comes from SEMA_SECRETS_KEY (a Fernet key, NOT a password -- generate
one with `Fernet.generate_key()`, see .env.example). There is no key
rotation or recovery here: losing the key makes every stored connection's
credentials permanently unreadable, and the admin must re-enter them (the
wizard already requires re-entry on edit for this exact reason).
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()


class SecretsKeyNotConfigured(Exception):
    """Raised when SEMA_SECRETS_KEY is unset -- the self-service SQL DB
    wizard's credential storage is unavailable until an admin sets it
    (generation instructions live in .env.example)."""


def _fernet() -> Fernet:
    key = os.environ.get("SEMA_SECRETS_KEY", "").strip()
    if not key:
        raise SecretsKeyNotConfigured(
            "SEMA_SECRETS_KEY is not set -- see .env.example for how to generate one."
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as e:
        raise SecretsKeyNotConfigured(f"SEMA_SECRETS_KEY is not a valid Fernet key: {e}") from None


def encrypt_secret(plaintext: str) -> str:
    """Encrypt one credential (a password) into a storable ciphertext
    string. Never logged, never returned to a client -- callers must treat
    the return value as write-only from the API's perspective."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored credential -- used ONLY server-side, immediately
    before opening a real DB connection (the connection test / health
    check). Never returned in an API response."""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise SecretsKeyNotConfigured(
            "Stored credential could not be decrypted -- SEMA_SECRETS_KEY may have changed."
        ) from None


def fingerprint(value: str) -> str:
    """A non-reversible, display-safe hint for a credential (e.g. "last 4 of
    a hash") -- lets the UI show "connection saved" without ever being able
    to reconstruct or leak the real value. Deliberately NOT the plaintext's
    own last 4 characters (that would leak real credential material)."""
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()[-4:]
