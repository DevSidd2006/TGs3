from app.auth import hash_password, verify_password


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("correct horse")
    assert hashed != "correct horse"
    assert verify_password("correct horse", hashed) is True


def test_verify_password_rejects_wrong_value():
    hashed = hash_password("correct horse")
    assert verify_password("wrong", hashed) is False


def test_hash_is_salted_and_reproducible():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2
