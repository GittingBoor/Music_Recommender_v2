"""E-mail normalisation and a deliberately simple plausibility check."""
import re

_MAX_EMAIL_LENGTH = 254
# One "@", no whitespace, a dot inside the domain. The reset mail proves the rest.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(raw: str) -> str:
    """Trimmed and lower-cased, so "Foo@Bar.de " and "foo@bar.de" are one account."""
    return raw.strip().lower()


def is_valid_email(email: str) -> bool:
    return len(email) <= _MAX_EMAIL_LENGTH and _EMAIL_RE.match(email) is not None
