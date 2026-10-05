"""Hash and verify the shared site password with scrypt (stdlib only).

Stored format: ``scrypt:<n>:<r>:<p>:<salt hex>:<hash hex>``. Colons instead of
the usual ``$`` because Docker Compose interpolates ``$`` in env files.
"""
import hashlib
import hmac
import secrets

_SCHEME = "scrypt"
_N = 2**15
_R = 8
_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32
_MAX_MEM = 64 * 1024 * 1024


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, maxmem=_MAX_MEM, dklen=_KEY_BYTES
    )


def hash_password(password: str) -> str:
    """Return a storable scrypt hash of ``password`` with a random salt."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt, _N, _R, _P)
    return f"{_SCHEME}:{_N}:{_R}:{_P}:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check ``password`` against a hash from :func:`hash_password`.

    Raises:
        ValueError: ``stored`` is not a hash in the expected format. Regenerate
            it with ``python -m src.auth.hash_password``.
    """
    parts = stored.split(":")
    if len(parts) != 6 or parts[0] != _SCHEME:
        raise ValueError(
            "SITE_PASSWORD_HASH has an unknown format; regenerate it with "
            "`python -m src.auth.hash_password`."
        )
    n, r, p = (int(x) for x in parts[1:4])
    salt, expected = bytes.fromhex(parts[4]), bytes.fromhex(parts[5])
    return hmac.compare_digest(_derive(password, salt, n, r, p), expected)
