"""Хранение пароля приложения Яндекса в settings.json.

На Windows — системное шифрование DPAPI: расшифровать может только ваша учётная запись Windows
на этом компьютере. На других системах — просто без открытого текста (base64)."""
from __future__ import annotations

import base64
import sys


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    src = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):
        raise OSError("DPAPI не смог обработать пароль")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(text: str) -> str:
    raw = text.encode("utf-8")
    if sys.platform.startswith("win"):
        try:
            return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode("ascii")
        except Exception:
            pass
    return "b64:" + base64.b64encode(raw).decode("ascii")


def unprotect(value: str | None) -> str:
    if not value:
        return ""
    kind, _, body = value.partition(":")
    raw = base64.b64decode(body.encode("ascii"))
    if kind == "dpapi":
        return _dpapi(raw, False).decode("utf-8")
    return raw.decode("utf-8")
