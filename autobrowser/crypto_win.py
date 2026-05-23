"""Windows DPAPI encryption helpers for protecting sensitive config values."""

import ctypes
import ctypes.wintypes
import logging
from base64 import b64decode, b64encode

logger = logging.getLogger(__name__)

_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_CRYPTPROTECT_LOCAL_MACHINE = 0x4


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


_crypt32 = ctypes.windll.crypt32

_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB),  # pDataIn
    ctypes.c_wchar_p,  # szDataDescr
    ctypes.POINTER(_DATA_BLOB),  # pOptionalEntropy
    ctypes.c_void_p,  # pvReserved
    ctypes.c_void_p,  # pPromptStruct
    ctypes.wintypes.DWORD,  # dwFlags
    ctypes.POINTER(_DATA_BLOB),  # pDataOut
]
_crypt32.CryptProtectData.restype = ctypes.wintypes.BOOL

_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_wchar_p,
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.wintypes.DWORD,
    ctypes.POINTER(_DATA_BLOB),
]
_crypt32.CryptUnprotectData.restype = ctypes.wintypes.BOOL


def _free_blob(blob: _DATA_BLOB) -> None:
    """Release memory allocated by CryptProtectData / CryptUnprotectData."""
    if blob.pbData:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def encrypt(plaintext: str) -> str:
    """Encrypt a string using DPAPI (current user, local machine not required).

    Returns a base64-encoded ciphertext, or the plaintext unchanged on failure.
    """
    if not plaintext:
        return plaintext

    data_in = plaintext.encode("utf-8")
    blob_in = _DATA_BLOB(len(data_in), ctypes.cast(
        ctypes.create_string_buffer(data_in), ctypes.POINTER(ctypes.c_char),
    ))
    blob_out = _DATA_BLOB()

    try:
        ok = _crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            "AutoBrowser Proxy",
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            logger.debug("CryptProtectData failed, storing plaintext")
            return plaintext

        cipher_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        return b64encode(cipher_bytes).decode("ascii")
    except OSError:
        logger.debug("DPAPI encrypt failed, storing plaintext", exc_info=True)
        return plaintext
    finally:
        _free_blob(blob_out)


def decrypt(ciphertext: str) -> str:
    """Decrypt a DPAPI-encrypted, base64-encoded string.

    Returns the plaintext, or the input unchanged if it looks like it was
    never encrypted (plaintext fallback for backwards compatibility).
    """
    if not ciphertext:
        return ciphertext

    try:
        cipher_bytes = b64decode(ciphertext, validate=True)
    except (ValueError, TypeError):
        # Not base64 – probably old plaintext
        return ciphertext

    blob_in = _DATA_BLOB(len(cipher_bytes), ctypes.cast(
        ctypes.create_string_buffer(cipher_bytes), ctypes.POINTER(ctypes.c_char),
    ))
    blob_out = _DATA_BLOB()

    try:
        ok = _crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok or not blob_out.pbData:
            logger.debug("CryptUnprotectData failed, returning raw value")
            return ciphertext

        plain_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        return plain_bytes.decode("utf-8")
    except OSError:
        logger.debug("DPAPI decrypt failed", exc_info=True)
        return ciphertext
    finally:
        _free_blob(blob_out)
