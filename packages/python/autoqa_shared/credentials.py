from cryptography.fernet import Fernet, InvalidToken

from .settings import get_settings


PREFIX = "autoqa:fernet:"


def _cipher() -> Fernet | None:
    key = get_settings().credential_encryption_key
    if key is None:
        return None
    try:
        return Fernet(key.get_secret_value())
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid AutoQA credential encryption key.") from exc


def protect_password(password: str | None) -> str | None:
    if not password:
        return None
    cipher = _cipher()
    if cipher is None:
        if get_settings().environment != "development" or password.startswith(PREFIX):
            raise ValueError("Configure the AutoQA credential encryption key before saving this password.")
        return password
    return PREFIX + cipher.encrypt(password.encode()).decode("ascii")


def read_password(password: str | None) -> str | None:
    if password is None or not password.startswith(PREFIX):
        return password
    cipher = _cipher()
    if cipher is None:
        raise ValueError("The worker needs the AutoQA credential encryption key.")
    try:
        return cipher.decrypt(password[len(PREFIX):].encode("ascii")).decode()
    except (InvalidToken, UnicodeError) as exc:
        raise ValueError("The saved password could not be decrypted.") from exc
