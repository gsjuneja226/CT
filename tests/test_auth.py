import pytest
from jose import jwt


def test_mock_login_submitter_returns_token(db_conn):
    from backend.services.auth_service import create_user_token, decode_token
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO users (email, role) VALUES ('s@test.com','submitter') RETURNING id")
        uid = str(cur.fetchone()["id"])
    token = create_user_token(uid, "s@test.com", "submitter")
    assert token is not None
    payload = decode_token(token)
    assert payload["role"] == "submitter"
    assert payload["sub"] == uid


def test_mock_login_contributor_returns_token(db_conn):
    from backend.services.auth_service import create_user_token, decode_token
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO users (email, role) VALUES ('c@test.com','contributor') RETURNING id")
        uid = str(cur.fetchone()["id"])
    token = create_user_token(uid, "c@test.com", "contributor")
    payload = decode_token(token)
    assert payload["role"] == "contributor"


def test_invalid_role_rejected():
    from fastapi import HTTPException
    from backend.services.auth_service import decode_token
    with pytest.raises(Exception):
        decode_token("not.a.valid.token")


def test_expired_token_returns_401():
    from datetime import datetime, timedelta
    from jose import jwt
    from backend.config import settings
    from fastapi import HTTPException
    from backend.services.auth_service import decode_token

    expired_payload = {
        "sub": "some-id",
        "role": "submitter",
        "exp": datetime.utcnow() - timedelta(hours=1)
    }
    token = jwt.encode(expired_payload, settings.JWT_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401


def test_tampered_token_returns_401():
    from fastapi import HTTPException
    from backend.services.auth_service import decode_token
    tampered = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJoYWNrZXIifQ.invalid_sig"
    with pytest.raises(HTTPException) as exc:
        decode_token(tampered)
    assert exc.value.status_code == 401


def test_node_token_created():
    from backend.services.auth_service import create_node_token, decode_token
    token = create_node_token("node-123")
    payload = decode_token(token)
    assert payload["type"] == "node"
    assert payload["sub"] == "node-123"
