"""Хранение базы на диске: обычный файл или зашифрованный паролем. Без Qt.

Надёжность записи: база целиком пишется во временный файл, сбрасывается на диск (fsync)
и только потом атомарно подменяет старый файл. Сбой питания посреди записи оставляет
прежнюю целую версию, а не наполовину записанную.

Шифрование (если задан пароль):
  * данные шифруются AES-256-GCM случайным «ключом данных» (32 байта);
  * ключ данных хранится в заголовке файла дважды — зашифрованным ключом из пароля
    и ключом из кода восстановления (оба получаются через scrypt);
  * GCM проверяет целостность: неверный пароль или повреждённый файл обнаруживаются,
    а не дают «мусор».
Смена пароля перешифровывает только ключ данных, сами данные не трогаются.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"HTENC1\n"
PLAIN_NAME = "tracker.sqlite3"
ENCRYPTED_NAME = "tracker.htenc"

# scrypt: ~0.1–0.3 с на вход — незаметно для человека, дорого для перебора.
KDF_PARAMS = {"n": 2 ** 15, "r": 8, "p": 1}
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без похожих O/0, I/1


class StorageError(Exception):
    pass


class WrongPassword(StorageError):
    pass


class CorruptFile(StorageError):
    pass


# ---------------------------------------------------------------- запись на диск

def atomic_write(path: Path, data: bytes, attempts: int = 6) -> None:
    """Записать файл целиком или не записать вовсе."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    # На Windows замену может ненадолго заблокировать антивирус или синхронизация облака.
    for i in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.15 * (i + 1))


# ---------------------------------------------------------------- ключи

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _kdf(secret: str, salt: bytes, params: dict) -> bytes:
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=params["n"], r=params["r"],
                          p=params["p"], maxmem=128 * 1024 * 1024, dklen=32)


def normalize_recovery(code: str) -> str:
    """Код можно вводить с пробелами, дефисами, строчными буквами; 0→O не нужен — их нет."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def format_recovery(code: str) -> str:
    code = normalize_recovery(code)
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def new_recovery_code() -> str:
    return format_recovery("".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(24)))


class Keyring:
    """Ключ данных + его копии, зашифрованные паролем и кодом восстановления."""

    def __init__(self, data_key: bytes, header: dict):
        self.data_key = data_key
        self.header = header

    def _wrap(self, secret: str) -> dict:
        salt, nonce = os.urandom(16), os.urandom(12)
        kek = _kdf(secret, salt, self.header["kdf"])
        ct = AESGCM(kek).encrypt(nonce, self.data_key, b"habittracker-key")
        return {"salt": _b64(salt), "nonce": _b64(nonce), "ct": _b64(ct)}

    @staticmethod
    def _unwrap(slot: dict, secret: str, kdf: dict) -> bytes:
        kek = _kdf(secret, _unb64(slot["salt"]), kdf)
        try:
            return AESGCM(kek).decrypt(_unb64(slot["nonce"]), _unb64(slot["ct"]), b"habittracker-key")
        except InvalidTag:
            raise WrongPassword() from None

    @classmethod
    def create(cls, password: str) -> tuple["Keyring", str]:
        ring = cls(AESGCM.generate_key(bit_length=256), {"v": 1, "kdf": dict(KDF_PARAMS)})
        code = new_recovery_code()
        ring.header["pw"] = ring._wrap(password)
        ring.header["rc"] = ring._wrap(normalize_recovery(code))
        return ring, code

    @classmethod
    def unlock(cls, header: dict, password: str | None = None,
               recovery: str | None = None) -> "Keyring":
        if password is not None:
            key = cls._unwrap(header["pw"], password, header["kdf"])
        elif recovery is not None:
            key = cls._unwrap(header["rc"], normalize_recovery(recovery), header["kdf"])
        else:
            raise WrongPassword()
        return cls(key, json.loads(json.dumps(header)))

    def check_password(self, password: str) -> bool:
        try:
            return self._unwrap(self.header["pw"], password, self.header["kdf"]) == self.data_key
        except WrongPassword:
            return False

    def set_password(self, password: str) -> None:
        self.header["pw"] = self._wrap(password)

    def new_recovery(self) -> str:
        code = new_recovery_code()
        self.header["rc"] = self._wrap(normalize_recovery(code))
        return code

    # ---- контейнер ----

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(12)
        head = json.dumps(self.header, separators=(",", ":")).encode("ascii")
        return MAGIC + head + b"\n" + nonce + AESGCM(self.data_key).encrypt(nonce, data, MAGIC)

    def decrypt(self, blob: bytes) -> bytes:
        _, payload = split_container(blob)
        nonce, ct = payload[:12], payload[12:]
        try:
            return AESGCM(self.data_key).decrypt(nonce, ct, MAGIC)
        except InvalidTag:
            raise CorruptFile("Файл повреждён или зашифрован другим ключом") from None


def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(MAGIC)


def split_container(blob: bytes) -> tuple[dict, bytes]:
    if not is_encrypted(blob):
        raise CorruptFile("Это не зашифрованный файл трекера")
    try:
        end = blob.index(b"\n", len(MAGIC))
        header = json.loads(blob[len(MAGIC):end].decode("ascii"))
        return header, blob[end + 1:]
    except (ValueError, UnicodeDecodeError) as e:
        raise CorruptFile("Заголовок файла повреждён") from e


def read_header(blob: bytes) -> dict:
    return split_container(blob)[0]


# ---------------------------------------------------------------- хранилища

class PlainStore:
    encrypted = False

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> bytes | None:
        return self.path.read_bytes() if self.path.exists() and self.path.stat().st_size else None

    def save(self, data: bytes) -> None:
        atomic_write(self.path, data)

    def wrap_for_backup(self, data: bytes) -> bytes:
        return data


class EncryptedStore:
    encrypted = True

    def __init__(self, path: Path, keyring: Keyring):
        self.path = Path(path)
        self.keyring = keyring

    def load(self) -> bytes | None:
        if not self.path.exists():
            return None
        return self.keyring.decrypt(self.path.read_bytes())

    def save(self, data: bytes) -> None:
        atomic_write(self.path, self.keyring.encrypt(data))

    def wrap_for_backup(self, data: bytes) -> bytes:
        return self.keyring.encrypt(data)


def current_file(data_dir: Path) -> tuple[Path | None, bool]:
    """Какой файл базы сейчас действующий: (путь, зашифрован ли).

    Если остались оба (сбой во время включения/выключения пароля) — берём более новый.
    """
    plain, enc = Path(data_dir) / PLAIN_NAME, Path(data_dir) / ENCRYPTED_NAME
    if enc.exists() and plain.exists():
        return (enc, True) if enc.stat().st_mtime >= plain.stat().st_mtime else (plain, False)
    if enc.exists():
        return enc, True
    if plain.exists():
        return plain, False
    return None, False
