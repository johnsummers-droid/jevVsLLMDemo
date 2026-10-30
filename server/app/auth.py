"""Session codes and bearer tokens. The database only ever sees HMAC-SHA256(TOKEN_SECRET, token)."""

import hashlib
import hmac
import secrets

# No 0/O/1/I/L: codes are read aloud and typed from a projector.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6


def new_session_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(code: str) -> str:
    """Codes are matched case-insensitively."""
    return code.strip().upper()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(secret: str, token: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def same_secret(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode(), expected.encode())
