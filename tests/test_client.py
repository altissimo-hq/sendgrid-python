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


class TestNormalizeRecipients:
    def test_single_string(self) -> None:
        assert SendGridClient._normalize_recipients("a@example.com") == ["a@example.com"]

    def test_list_of_strings(self) -> None:
        result = SendGridClient._normalize_recipients(["a@example.com", "b@example.com"])
        assert result == ["a@example.com", "b@example.com"]

    def test_single_item_list(self) -> None:
        assert SendGridClient._normalize_recipients(["a@example.com"]) == ["a@example.com"]


class TestMultipleRecipients:
    def test_send_text_multiple_to(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to=["a@example.com", "b@example.com"],
            subject="Hello",
            body="Hi",
        )
        assert result.ok is True
        fake_api_client.send.assert_called_once()

    def test_send_html_multiple_to(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_html(
            to=["a@example.com", "b@example.com"],
            subject="Hello",
            html="<h1>Hi</h1>",
        )
        assert result.ok is True
        fake_api_client.send.assert_called_once()

    def test_send_template_multiple_to(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_template(
            to=["a@example.com", "b@example.com"],
            template_id="d-abc123",
            dynamic_data={"name": "Test"},
        )
        assert result.ok is True
        fake_api_client.send.assert_called_once()

    def test_single_string_still_works(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        """Backward compatibility — single string `to` must still work."""
        result = client_with_mock.send_text(to="user@example.com", subject="Hello", body="Hi")
        assert result.ok is True


class TestCcBcc:
    def test_send_text_with_cc(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hello",
            body="Hi",
            cc="cc@example.com",
        )
        assert result.ok is True
        fake_api_client.send.assert_called_once()

    def test_send_text_with_bcc(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hello",
            body="Hi",
            bcc="bcc@example.com",
        )
        assert result.ok is True

    def test_send_text_with_cc_list(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hello",
            body="Hi",
            cc=["cc1@example.com", "cc2@example.com"],
        )
        assert result.ok is True

    def test_send_text_with_bcc_list(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hello",
            body="Hi",
            bcc=["bcc1@example.com", "bcc2@example.com"],
        )
        assert result.ok is True

    def test_send_html_with_cc_and_bcc(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_html(
            to="user@example.com",
            subject="Hello",
            html="<p>Hi</p>",
            cc="cc@example.com",
            bcc=["bcc1@example.com", "bcc2@example.com"],
        )
        assert result.ok is True

    def test_send_template_with_cc_and_bcc(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_template(
            to="user@example.com",
            template_id="d-abc123",
            dynamic_data={"name": "Test"},
            cc=["cc@example.com"],
            bcc="bcc@example.com",
        )
        assert result.ok is True

    def test_send_with_all_recipient_types(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        """Multiple to, CC, BCC, and reply_to all together."""
        result = client_with_mock.send_html(
            to=["a@example.com", "b@example.com"],
            subject="Hello",
            html="<p>Hi</p>",
            cc=["cc1@example.com", "cc2@example.com"],
            bcc=["bcc@example.com"],
            reply_to="support@example.com",
        )
        assert result.ok is True
        fake_api_client.send.assert_called_once()


class TestRetryConfig:
    def test_default_no_retries(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        assert sg._max_retries == 0
        assert sg._retry_delay == 1.0

    def test_custom_retry_config(self) -> None:
        sg = SendGridClient(api_key="SG.test", max_retries=3, retry_delay=0.5)
        assert sg._max_retries == 3
        assert sg._retry_delay == 0.5

    def test_from_env_with_retry_config(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test"}):
            sg = SendGridClient.from_env(max_retries=2, retry_delay=2.0)
            assert sg._max_retries == 2
            assert sg._retry_delay == 2.0


class TestRetryBehavior:
    @pytest.fixture
    def retry_client(self, fake_api_client: MagicMock) -> SendGridClient:
        """Return a client with retries enabled and backoff patched out."""
        sg = SendGridClient(api_key="SG.fake", default_from="sender@example.com", max_retries=3, retry_delay=0.1)
        sg._client = fake_api_client
        return sg

    def test_no_retry_on_success(self, retry_client: SendGridClient, fake_api_client: MagicMock) -> None:
        fake_api_client.send.return_value = FakeResponse(status_code=202)
        with patch.object(retry_client, "_backoff") as mock_backoff:
            result = retry_client.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is True
        assert result.status_code == 202
        fake_api_client.send.assert_called_once()
        mock_backoff.assert_not_called()

    def test_no_retry_on_client_error(self, retry_client: SendGridClient, fake_api_client: MagicMock) -> None:
        """4xx errors (except 429) should NOT be retried."""
        fake_api_client.send.return_value = FakeResponse(status_code=400, body=b"Bad Request")
        with patch.object(retry_client, "_backoff") as mock_backoff:
            result = retry_client.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is False
        assert result.status_code == 400
        fake_api_client.send.assert_called_once()
        mock_backoff.assert_not_called()

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
    def test_retry_on_transient_status(
        self, retry_client: SendGridClient, fake_api_client: MagicMock, status_code: int
    ) -> None:
        """Each retryable status code should trigger retries."""
        fake_api_client.send.return_value = FakeResponse(status_code=status_code)
        with patch.object(retry_client, "_backoff"):
            result = retry_client.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is False
        assert result.status_code == status_code
        # 1 initial + 3 retries = 4 total calls
        assert fake_api_client.send.call_count == 4

    def test_successful_retry_after_transient_failure(
        self, retry_client: SendGridClient, fake_api_client: MagicMock
    ) -> None:
        """Should succeed if a transient failure is followed by a success."""
        fake_api_client.send.side_effect = [
            FakeResponse(status_code=503),
            FakeResponse(status_code=503),
            FakeResponse(status_code=202),
        ]
        with patch.object(retry_client, "_backoff"):
            result = retry_client.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is True
        assert result.status_code == 202
        assert fake_api_client.send.call_count == 3

    def test_max_retries_exhausted(self, retry_client: SendGridClient, fake_api_client: MagicMock) -> None:
        """Should return the last failed result when all retries are exhausted."""
        fake_api_client.send.return_value = FakeResponse(status_code=500, body=b"Internal Server Error")
        with patch.object(retry_client, "_backoff"):
            result = retry_client.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is False
        assert result.status_code == 500
        assert fake_api_client.send.call_count == 4

    def test_retry_on_exception(self, retry_client: SendGridClient, fake_api_client: MagicMock) -> None:
        """Network exceptions should also be retried."""
        fake_api_client.send.side_effect = [
            ConnectionError("network down"),
            FakeResponse(status_code=202),
        ]
        with patch.object(retry_client, "_backoff"):
            result = retry_client.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is True
        assert result.status_code == 202
        assert fake_api_client.send.call_count == 2

    def test_exception_retries_exhausted(self, retry_client: SendGridClient, fake_api_client: MagicMock) -> None:
        """Should return error result when exceptions exhaust all retries."""
        fake_api_client.send.side_effect = ConnectionError("network down")
        with patch.object(retry_client, "_backoff"):
            result = retry_client.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is False
        assert result.error == "network down"
        assert fake_api_client.send.call_count == 4

    def test_zero_retries_no_retry(self, fake_api_client: MagicMock) -> None:
        """With max_retries=0 (default), transient errors are not retried."""
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com")
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=500)
        result = sg.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is False
        fake_api_client.send.assert_called_once()

    def test_retry_works_with_send_html(self, retry_client: SendGridClient, fake_api_client: MagicMock) -> None:
        fake_api_client.send.side_effect = [
            FakeResponse(status_code=429),
            FakeResponse(status_code=202),
        ]
        with patch.object(retry_client, "_backoff"):
            result = retry_client.send_html(to="user@example.com", subject="Hi", html="<p>Hi</p>")
        assert result.ok is True
        assert fake_api_client.send.call_count == 2

    def test_retry_works_with_send_template(self, retry_client: SendGridClient, fake_api_client: MagicMock) -> None:
        fake_api_client.send.side_effect = [
            FakeResponse(status_code=502),
            FakeResponse(status_code=202),
        ]
        with patch.object(retry_client, "_backoff"):
            result = retry_client.send_template(
                to="user@example.com", template_id="d-abc123", dynamic_data={"name": "Test"}
            )
        assert result.ok is True
        assert fake_api_client.send.call_count == 2


class TestBackoff:
    def test_backoff_calls_sleep(self) -> None:
        sg = SendGridClient(api_key="SG.test", retry_delay=1.0)
        with (
            patch("altissimo.sendgrid.client.time.sleep") as mock_sleep,
            patch("altissimo.sendgrid.client.random.uniform", return_value=0.25),
        ):
            sg._backoff(0)
        # delay = 1.0 * 2^0 = 1.0, jitter = 0.25 → total = 1.25
        mock_sleep.assert_called_once_with(1.25)

    def test_backoff_exponential(self) -> None:
        sg = SendGridClient(api_key="SG.test", retry_delay=1.0)
        with (
            patch("altissimo.sendgrid.client.time.sleep") as mock_sleep,
            patch("altissimo.sendgrid.client.random.uniform", return_value=0.0),
        ):
            sg._backoff(2)
        # delay = 1.0 * 2^2 = 4.0, jitter = 0.0 → total = 4.0
        mock_sleep.assert_called_once_with(4.0)
