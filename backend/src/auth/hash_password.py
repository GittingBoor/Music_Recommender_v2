"""Print a SITE_PASSWORD_HASH for .env.prod.

Usage (password is read without echo):
    docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm --no-deps \
        backend python -m src.auth.hash_password
"""
import getpass
import sys

from src.auth.password import hash_password


def main() -> None:
    password = getpass.getpass("Password: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
    if not password:
        sys.exit("Empty password, nothing hashed.")
    sys.stdout.write(hash_password(password) + "\n")


if __name__ == "__main__":
    main()
