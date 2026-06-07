"""Tests for models."""

from __future__ import annotations

import pytest

from altissimo.sendgrid.models import EmailAddress, SendResult


class TestEmailAddress:
    def test_with_name(self) -> None:
        addr = EmailAddress(email="user@example.com", name="User Name")
        assert addr.email == "user@example.com"
        assert addr.name == "User Name"

    def test_without_name(self) -> None:
        addr = EmailAddress(email="user@example.com")
        assert addr.email == "user@example.com"
        assert addr.name is None

    def test_frozen(self) -> None:
        addr = EmailAddress(email="user@example.com")
        with pytest.raises(AttributeError):
            addr.email = "other@example.com"  # type: ignore[misc]

    def test_equality(self) -> None:
        a1 = EmailAddress("user@example.com", "User")
        a2 = EmailAddress("user@example.com", "User")
        assert a1 == a2

    def test_repr(self) -> None:
        addr = EmailAddress("user@example.com", "User")
        assert "EmailAddress" in repr(addr)
        assert "user@example.com" in repr(addr)


class TestSendResult:
    def test_ok_result(self) -> None:
        result = SendResult(ok=True, status_code=202, body="", headers={"X-Message-Id": "abc123"})
        assert result.ok is True
        assert result.status_code == 202
        assert result.error is None

    def test_error_result(self) -> None:
        result = SendResult(ok=False, status_code=0, error="Connection refused")
        assert result.ok is False
        assert result.status_code == 0
        assert result.error == "Connection refused"

    def test_defaults(self) -> None:
        result = SendResult(ok=True, status_code=200)
        assert result.body == ""
        assert result.headers == {}
        assert result.error is None

    def test_frozen(self) -> None:
        result = SendResult(ok=True, status_code=202)

        with pytest.raises(AttributeError):
            result.ok = False  # type: ignore[misc]

    def test_equality(self) -> None:
        r1 = SendResult(ok=True, status_code=202, body="ok")
        r2 = SendResult(ok=True, status_code=202, body="ok")
        assert r1 == r2

    def test_repr(self) -> None:
        result = SendResult(ok=True, status_code=202)
        assert "SendResult" in repr(result)
        assert "202" in repr(result)
