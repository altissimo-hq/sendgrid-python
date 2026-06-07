"""Tests for SendResult model."""

from __future__ import annotations

from altissimo.sendgrid.models import SendResult


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
        import pytest

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
