from dataclasses import replace

import pytest

from app.crypto import (
    CryptoError,
    EncryptedFileEnvelope,
    decode_master_key,
    decrypt_file,
    decrypt_from_bytes,
    encode_master_key,
    encrypt_file,
    generate_master_key,
    sha256_hexdigest,
)


def test_encrypt_file_round_trips_and_records_plaintext_hash():
    master_key = generate_master_key()
    content = b"course project demo file"

    envelope = encrypt_file(content, master_key)
    restored = decrypt_file(envelope, master_key)

    assert restored == content
    assert envelope.ciphertext != content
    assert envelope.plaintext_sha256 == sha256_hexdigest(content)


def test_encrypted_file_envelope_serializes_and_decrypts():
    master_key = generate_master_key()
    content = b"serialized payload"

    payload = encrypt_file(content, master_key).to_bytes()
    restored = decrypt_from_bytes(payload, master_key)

    assert restored == content


def test_encrypt_file_uses_unique_file_key_and_nonce():
    master_key = generate_master_key()

    first = encrypt_file(b"same content", master_key)
    second = encrypt_file(b"same content", master_key)

    assert first.nonce != second.nonce
    assert first.key_nonce != second.key_nonce
    assert first.wrapped_key != second.wrapped_key
    assert first.ciphertext != second.ciphertext


def test_decrypt_file_rejects_tampered_ciphertext():
    master_key = generate_master_key()
    envelope = encrypt_file(b"do not alter", master_key)
    tampered = replace(envelope, ciphertext=envelope.ciphertext[:-1] + bytes([envelope.ciphertext[-1] ^ 1]))

    with pytest.raises(CryptoError):
        decrypt_file(tampered, master_key)


def test_decrypt_file_rejects_tampered_hash_binding():
    master_key = generate_master_key()
    envelope = encrypt_file(b"hash is authenticated", master_key)
    tampered = replace(envelope, plaintext_sha256="0" * 64)

    with pytest.raises(CryptoError):
        decrypt_file(tampered, master_key)


def test_master_key_can_be_encoded_and_decoded():
    master_key = generate_master_key()

    encoded = encode_master_key(master_key)

    assert decode_master_key(encoded) == master_key


def test_decode_master_key_rejects_wrong_key_size():
    with pytest.raises(CryptoError):
        decode_master_key("c2hvcnQ=")


def test_envelope_from_bytes_rejects_invalid_payload():
    with pytest.raises(CryptoError):
        EncryptedFileEnvelope.from_bytes(b"not-json")
