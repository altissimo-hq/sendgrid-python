"""Tests for SendGridClient."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from altissimo.sendgrid import SendGridClient
from altissimo.sendgrid.exceptions import SendGridImportError

from .conftest import FakeResponse


class TestClientConstruction:
    def test_basic_init(self) -> None:
        client = SendGridClient(api_key="SG.test-key")
        assert client._api_key == "SG.test-key"
        assert client._default_from is None
        assert client._client is None

    def test_init_with_default_from(self) -> None:
        client = SendGridClient(api_key="SG.test-key", default_from="me@example.com")
        assert client._default_from == "me@example.com"

    def test_from_env(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.from-env"}):
            client = SendGridClient.from_env()
            assert client._api_key == "SG.from-env"

    def test_from_env_custom_var(self) -> None:
        with patch.dict(os.environ, {"MY_SG_KEY": "SG.custom"}):
            client = SendGridClient.from_env(env_var="MY_SG_KEY")
            assert client._api_key == "SG.custom"

    def test_from_env_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="not set"):
            SendGridClient.from_env(env_var="NONEXISTENT_KEY")

    def test_from_env_empty(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": ""}), pytest.raises(ValueError, match="not set"):
            SendGridClient.from_env()

    def test_from_env_with_default_from(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test"}):
            client = SendGridClient.from_env(default_from="test@example.com")
            assert client._default_from == "test@example.com"


class TestLazyClient:
    def test_client_property_creates_instance(self) -> None:
        sg = SendGridClient(api_key="SG.test-key")
        with patch("altissimo.sendgrid.client._get_sendgrid_api_client") as mock_factory:
            mock_factory.return_value = MagicMock()
            _ = sg.client
            mock_factory.assert_called_once_with("SG.test-key")

    def test_client_property_caches(self) -> None:
        sg = SendGridClient(api_key="SG.test-key")
        with patch("altissimo.sendgrid.client._get_sendgrid_api_client") as mock_factory:
            mock_factory.return_value = MagicMock()
            first = sg.client
            second = sg.client
            assert first is second
            mock_factory.assert_called_once()


class TestResolveFrom:
    def test_explicit_from(self) -> None:
        sg = SendGridClient(api_key="SG.test", default_from="default@example.com")
        assert sg._resolve_from("explicit@example.com") == "explicit@example.com"

    def test_default_from(self) -> None:
        sg = SendGridClient(api_key="SG.test", default_from="default@example.com")
        assert sg._resolve_from(None) == "default@example.com"

    def test_no_from_raises(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        with pytest.raises(ValueError, match="No sender email"):
            sg._resolve_from(None)


class TestSendText:
    def test_send_text_success(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(to="user@example.com", subject="Hello", body="Hi there")
        assert result.ok is True
        assert result.status_code == 202
        fake_api_client.send.assert_called_once()

    def test_send_text_with_reply_to(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hello",
            body="Hi",
            reply_to="support@example.com",
        )
        assert result.ok is True
        fake_api_client.send.assert_called_once()

    def test_send_text_with_explicit_from(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hello",
            body="Hi",
            from_email="other@example.com",
        )
        assert result.ok is True

    def test_send_text_api_error(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        fake_api_client.send.side_effect = Exception("API down")
        result = client_with_mock.send_text(to="user@example.com", subject="Hello", body="Hi")
        assert result.ok is False
        assert result.error == "API down"


class TestSendHtml:
    def test_send_html_success(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_html(to="user@example.com", subject="Hello", html="<h1>Hi</h1>")
        assert result.ok is True
        assert result.status_code == 202

    def test_send_html_with_reply_to(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_html(
            to="user@example.com",
            subject="Hello",
            html="<h1>Hi</h1>",
            reply_to="support@example.com",
        )
        assert result.ok is True

    def test_send_html_api_error(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        fake_api_client.send.side_effect = RuntimeError("timeout")
        result = client_with_mock.send_html(to="user@example.com", subject="Hello", html="<h1>Hi</h1>")
        assert result.ok is False
        assert result.error == "timeout"


class TestSendTemplate:
    def test_send_template_success(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_template(
            to="user@example.com",
            template_id="d-abc123",
            dynamic_data={"first_name": "Alice"},
        )
        assert result.ok is True
        assert result.status_code == 202

    def test_send_template_no_data(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_template(to="user@example.com", template_id="d-abc123")
        assert result.ok is True

    def test_send_template_with_reply_to(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_template(
            to="user@example.com",
            template_id="d-abc123",
            dynamic_data={"year": 2026},
            reply_to="support@example.com",
        )
        assert result.ok is True

    def test_send_template_api_error(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        fake_api_client.send.side_effect = Exception("bad request")
        result = client_with_mock.send_template(
            to="user@example.com",
            template_id="d-abc123",
            dynamic_data={"name": "Test"},
        )
        assert result.ok is False
        assert result.error == "bad request"


class TestBuildResult:
    def test_bytes_body(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        response = FakeResponse(status_code=200, body=b'{"message": "ok"}', headers={"X-Id": "123"})
        result = sg._build_result(response)
        assert result.ok is True
        assert result.body == '{"message": "ok"}'
        assert result.headers == {"X-Id": "123"}

    def test_non_success_status(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        response = FakeResponse(status_code=400, body=b"Bad Request")
        result = sg._build_result(response)
        assert result.ok is False
        assert result.status_code == 400

    def test_empty_body(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        response = FakeResponse(status_code=202, body=b"", headers={})
        result = sg._build_result(response)
        assert result.ok is True
        assert result.body == ""

    def test_none_headers(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        response = FakeResponse(status_code=202)
        response.headers = None  # type: ignore[assignment]
        result = sg._build_result(response)
        assert result.headers == {}


class TestSendGridImportError:
    def test_import_error_message(self) -> None:
        err = SendGridImportError()
        assert "sendgrid" in str(err)
        assert "pip install" in str(err)

    def test_is_import_error(self) -> None:
        err = SendGridImportError()
        assert isinstance(err, ImportError)

    def test_lazy_import_error(self) -> None:
        with patch.dict("sys.modules", {"sendgrid": None}):
            sg = SendGridClient(api_key="SG.test")
            with pytest.raises(SendGridImportError):
                _ = sg.client
