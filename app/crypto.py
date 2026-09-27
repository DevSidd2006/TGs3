import base64
import binascii
import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ENVELOPE_VERSION = "tgs3-file-envelope-v1"
MASTER_KEY_BYTES = 32
DATA_KEY_BYTES = 32
NONCE_BYTES = 12

_DATA_AAD_PREFIX = b"tgs3:file:"
_WRAP_AAD = b"tgs3:file-key:v1"


class CryptoError(ValueError):
    """Raised when encrypted file material cannot be decoded or verified."""


@dataclass(frozen=True)
class EncryptedFileEnvelope:
    version: str
    algorithm: str
    key_algorithm: str
    nonce: bytes
    key_nonce: bytes
    wrapped_key: bytes
    ciphertext: bytes
    plaintext_sha256: str

    def to_bytes(self) -> bytes:
        payload = {
            "version": self.version,
            "algorithm": self.algorithm,
            "key_algorithm": self.key_algorithm,
            "nonce": _b64encode(self.nonce),
            "key_nonce": _b64encode(self.key_nonce),
            "wrapped_key": _b64encode(self.wrapped_key),
            "ciphertext": _b64encode(self.ciphertext),
            "plaintext_sha256": self.plaintext_sha256,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_bytes(cls, payload: bytes) -> "EncryptedFileEnvelope":
        try:
            raw = json.loads(payload.decode("utf-8"))
            return cls(
                version=_require_str(raw, "version"),
                algorithm=_require_str(raw, "algorithm"),
                key_algorithm=_require_str(raw, "key_algorithm"),
                nonce=_b64decode(_require_str(raw, "nonce"), "nonce"),
                key_nonce=_b64decode(_require_str(raw, "key_nonce"), "key_nonce"),
                wrapped_key=_b64decode(_require_str(raw, "wrapped_key"), "wrapped_key"),
                ciphertext=_b64decode(_require_str(raw, "ciphertext"), "ciphertext"),
                plaintext_sha256=_require_str(raw, "plaintext_sha256"),
            )
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CryptoError("invalid encrypted file envelope") from exc


def generate_master_key() -> bytes:
    return secrets.token_bytes(MASTER_KEY_BYTES)


def encode_master_key(master_key: bytes) -> str:
    _validate_key(master_key, "master key")
    return base64.urlsafe_b64encode(master_key).decode("ascii")


def decode_master_key(encoded: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise CryptoError("master key must be urlsafe base64") from exc
    _validate_key(key, "master key")
    return key


def sha256_digest(content: bytes) -> bytes:
    return hashlib.sha256(content).digest()


def sha256_hexdigest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encrypt_file(content: bytes, master_key: bytes) -> EncryptedFileEnvelope:
    _validate_key(master_key, "master key")
    data_key = secrets.token_bytes(DATA_KEY_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    key_nonce = secrets.token_bytes(NONCE_BYTES)
    digest = sha256_hexdigest(content)

    ciphertext = AESGCM(data_key).encrypt(nonce, content, _data_aad(digest))
    wrapped_key = AESGCM(master_key).encrypt(key_nonce, data_key, _WRAP_AAD)
    return EncryptedFileEnvelope(
        version=ENVELOPE_VERSION,
        algorithm="AES-256-GCM",
        key_algorithm="AES-256-GCM",
        nonce=nonce,
        key_nonce=key_nonce,
        wrapped_key=wrapped_key,
        ciphertext=ciphertext,
        plaintext_sha256=digest,
    )


def decrypt_file(envelope: EncryptedFileEnvelope, master_key: bytes) -> bytes:
    _validate_envelope(envelope)
    _validate_key(master_key, "master key")
    try:
        data_key = AESGCM(master_key).decrypt(envelope.key_nonce, envelope.wrapped_key, _WRAP_AAD)
        content = AESGCM(data_key).decrypt(envelope.nonce, envelope.ciphertext, _data_aad(envelope.plaintext_sha256))
    except InvalidTag as exc:
        raise CryptoError("encrypted file authentication failed") from exc
    if sha256_hexdigest(content) != envelope.plaintext_sha256:
        raise CryptoError("encrypted file hash mismatch")
    return content


def encrypt_to_bytes(content: bytes, master_key: bytes) -> bytes:
    return encrypt_file(content, master_key).to_bytes()


def decrypt_from_bytes(payload: bytes, master_key: bytes) -> bytes:
    return decrypt_file(EncryptedFileEnvelope.from_bytes(payload), master_key)


def _validate_envelope(envelope: EncryptedFileEnvelope) -> None:
    if envelope.version != ENVELOPE_VERSION:
        raise CryptoError(f"unsupported encrypted file envelope version {envelope.version!r}")
    if envelope.algorithm != "AES-256-GCM" or envelope.key_algorithm != "AES-256-GCM":
        raise CryptoError("unsupported encrypted file algorithm")
    if len(envelope.nonce) != NONCE_BYTES:
        raise CryptoError("invalid encrypted file nonce")
    if len(envelope.key_nonce) != NONCE_BYTES:
        raise CryptoError("invalid encrypted key nonce")
    if len(envelope.plaintext_sha256) != 64:
        raise CryptoError("invalid encrypted file hash")


def _validate_key(key: bytes, label: str) -> None:
    if len(key) != MASTER_KEY_BYTES:
        raise CryptoError(f"{label} must be {MASTER_KEY_BYTES} bytes")


def _data_aad(digest: str) -> bytes:
    return _DATA_AAD_PREFIX + ENVELOPE_VERSION.encode("ascii") + b":" + digest.encode("ascii")


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise CryptoError(f"encrypted file envelope field {key!r} must be a string")
    return value


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str, field: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise CryptoError(f"encrypted file envelope field {field!r} must be urlsafe base64") from exc
