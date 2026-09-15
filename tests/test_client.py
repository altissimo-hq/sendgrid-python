"""Tests for SendGridClient."""

from __future__ import annotations

import logging
import os
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from altissimo.sendgrid import SendGridClient
from altissimo.sendgrid.exceptions import SendGridImportError, SendGridSendError

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

    def test_from_env_does_not_read_env_var_eagerly(self) -> None:
        """Constructing via from_env() must not touch the environment at all."""
        with patch.dict(os.environ, {}, clear=True):
            client = SendGridClient.from_env(env_var="SENDGRID_API_KEY")
        assert client._api_key is None
        assert client._api_key_env_var == "SENDGRID_API_KEY"

    def test_from_env(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.from-env"}):
            client = SendGridClient.from_env()
            assert client._resolve_api_key() == "SG.from-env"

    def test_from_env_custom_var(self) -> None:
        with patch.dict(os.environ, {"MY_SG_KEY": "SG.custom"}):
            client = SendGridClient.from_env(env_var="MY_SG_KEY")
            assert client._resolve_api_key() == "SG.custom"

    def test_from_env_missing_does_not_raise_at_construction(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            client = SendGridClient.from_env(env_var="NONEXISTENT_KEY")
        assert client is not None

    def test_from_env_missing_raises_lazily_on_first_use(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            client = SendGridClient.from_env(env_var="NONEXISTENT_KEY")
            with pytest.raises(ValueError, match="not set"):
                client._resolve_api_key()
            with pytest.raises(ValueError, match="not set"):
                _ = client.client

    def test_from_env_empty_raises_lazily_on_first_use(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": ""}):
            client = SendGridClient.from_env()
            with pytest.raises(ValueError, match="not set"):
                client._resolve_api_key()

    def test_from_env_reads_env_var_set_after_construction(self) -> None:
        """The env var is read at first-use time, not construction time."""
        with patch.dict(os.environ, {}, clear=True):
            client = SendGridClient.from_env()
            os.environ["SENDGRID_API_KEY"] = "SG.set-later"
            assert client._resolve_api_key() == "SG.set-later"

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

    def test_suppresses_python_http_client_debug_logging(self) -> None:
        """python_http_client logs the API key in headers at DEBUG — must not leak."""
        from altissimo.sendgrid.client import _get_sendgrid_api_client

        target_logger = logging.getLogger("python_http_client")
        original_level = target_logger.level
        target_logger.setLevel(logging.DEBUG)
        try:
            with patch("sendgrid.SendGridAPIClient") as mock_sdk_client:
                mock_sdk_client.return_value = MagicMock()
                _get_sendgrid_api_client("SG.test-key")
            assert target_logger.level == logging.WARNING
        finally:
            target_logger.setLevel(original_level)


class TestResolveFrom:
    def test_explicit_from(self) -> None:
        sg = SendGridClient(api_key="SG.test", default_from="default@example.com")
        result = sg._resolve_from("explicit@example.com")
        assert result.email == "explicit@example.com"

    def test_default_from(self) -> None:
        sg = SendGridClient(api_key="SG.test", default_from="default@example.com")
        result = sg._resolve_from(None)
        assert result.email == "default@example.com"

    def test_default_from_with_name(self) -> None:
        sg = SendGridClient(api_key="SG.test", default_from=("team@example.com", "My Team"))
        result = sg._resolve_from(None)
        assert result.email == "team@example.com"
        assert result.name == "My Team"

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

    def test_send_text_api_error_raises_by_default(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        exc = Exception("API down")
        exc.status_code = 500  # type: ignore[attr-defined]
        fake_api_client.send.side_effect = exc
        with pytest.raises(SendGridSendError):
            client_with_mock.send_text(to="user@example.com", subject="Hello", body="Hi")

    def test_send_text_api_error_swallowed_when_opted_out(
        self, client_no_raise: Any, fake_api_client: MagicMock
    ) -> None:
        exc = Exception("API down")
        exc.status_code = 500  # type: ignore[attr-defined]
        fake_api_client.send.side_effect = exc
        result = client_no_raise.send_text(to="user@example.com", subject="Hello", body="Hi")
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

    def test_send_html_api_error_raises_by_default(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        fake_api_client.send.side_effect = TimeoutError("timeout")
        with pytest.raises(SendGridSendError):
            client_with_mock.send_html(to="user@example.com", subject="Hello", html="<h1>Hi</h1>")

    def test_send_html_api_error_swallowed_when_opted_out(
        self, client_no_raise: Any, fake_api_client: MagicMock
    ) -> None:
        fake_api_client.send.side_effect = TimeoutError("timeout")
        result = client_no_raise.send_html(to="user@example.com", subject="Hello", html="<h1>Hi</h1>")
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

    def test_send_template_api_error_raises_by_default(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        exc = Exception("bad request")
        exc.status_code = 400  # type: ignore[attr-defined]
        fake_api_client.send.side_effect = exc
        with pytest.raises(SendGridSendError):
            client_with_mock.send_template(
                to="user@example.com",
                template_id="d-abc123",
                dynamic_data={"name": "Test"},
            )

    def test_send_template_api_error_swallowed_when_opted_out(
        self, client_no_raise: Any, fake_api_client: MagicMock
    ) -> None:
        exc = Exception("bad request")
        exc.status_code = 400  # type: ignore[attr-defined]
        fake_api_client.send.side_effect = exc
        result = client_no_raise.send_template(
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


class TestBuildErrorResult:
    def test_reads_status_code_from_exception(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        exc = Exception("bad request")
        exc.status_code = 400  # type: ignore[attr-defined]
        result = sg._build_error_result(exc)
        assert result.status_code == 400

    def test_reads_code_from_urllib_http_error_as_fallback(self) -> None:
        import urllib.error

        sg = SendGridClient(api_key="SG.test")
        exc = urllib.error.HTTPError(url="https://api.sendgrid.com", code=429, msg="rate limited", hdrs=None, fp=None)
        result = sg._build_error_result(exc)
        assert result.status_code == 429

    def test_ignores_code_attribute_on_non_urllib_exception(self) -> None:
        """A `.code` attribute on an arbitrary exception must not be trusted as an HTTP status."""
        sg = SendGridClient(api_key="SG.test")
        exc = Exception("unrelated")
        exc.code = 429  # type: ignore[attr-defined]
        result = sg._build_error_result(exc)
        assert result.status_code == 0

    def test_status_code_defaults_to_zero(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        result = sg._build_error_result(Exception("network down"))
        assert result.status_code == 0

    def test_preserves_exception(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        exc = Exception("fail")
        result = sg._build_error_result(exc)
        assert result.exception is exc

    def test_does_not_log_above_debug(self) -> None:
        """The library must not report failures on the caller's behalf."""
        sg = SendGridClient(api_key="SG.test")
        with patch("altissimo.sendgrid.client.logger") as mock_logger:
            sg._build_error_result(Exception("fail"))
        mock_logger.exception.assert_not_called()
        mock_logger.error.assert_not_called()
        mock_logger.warning.assert_not_called()
        mock_logger.debug.assert_called_once()


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
        """Return a client with retries enabled, backoff patched out, and errors swallowed.

        Swallow mode (``raise_on_error=False``) lets these tests inspect the
        returned ``SendResult`` directly instead of catching an exception.
        """
        sg = SendGridClient(
            api_key="SG.fake",
            default_from="sender@example.com",
            max_retries=3,
            retry_delay=0.1,
            raise_on_error=False,
        )
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

    def test_retry_exhausted_raises_by_default(self, fake_api_client: MagicMock) -> None:
        """With raise_on_error=True (the default), an exhausted retry raises."""
        sg = SendGridClient(api_key="SG.fake", default_from="sender@example.com", max_retries=1, retry_delay=0.1)
        sg._client = fake_api_client

        exc = Exception("server error")
        exc.status_code = 500  # type: ignore[attr-defined]
        fake_api_client.send.side_effect = exc

        with patch.object(sg, "_backoff"), pytest.raises(SendGridSendError) as exc_info:
            sg.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert exc_info.value.status_code == 500
        assert exc_info.value.__cause__ is exc
        assert fake_api_client.send.call_count == 2

    def test_zero_retries_no_retry(self, fake_api_client: MagicMock) -> None:
        """With max_retries=0 (default), transient errors are not retried."""
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", raise_on_error=False)
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


class TestConfigAndProgrammingErrorsNotRetried:
    """Config/import errors and programming errors must surface immediately, unretried.

    Regression tests for the case where ``from_env()``'s deferred key
    resolution ran *inside* the retry loop's ``try`` block: a missing API
    key or an uninstalled SDK was caught, given ``status_code=0``, and
    treated as a retryable network error instead of propagating as the
    ``ValueError`` / ``SendGridImportError`` it actually is.
    """

    def test_missing_api_key_raises_immediately_without_retry(self, fake_api_client: MagicMock) -> None:
        with patch.dict(os.environ, {}, clear=True):
            sg = SendGridClient.from_env(default_from="sender@example.com", max_retries=2, retry_delay=0.1)
            with patch.object(sg, "_backoff") as mock_backoff, pytest.raises(ValueError, match="not set"):
                sg.send_template(to="a@example.com", template_id="d-1")
            mock_backoff.assert_not_called()
            fake_api_client.send.assert_not_called()

    def test_missing_sendgrid_sdk_raises_immediately_without_retry(self) -> None:
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", max_retries=2, retry_delay=0.1)
        with (
            patch.dict("sys.modules", {"sendgrid": None}),
            patch.object(sg, "_backoff") as mock_backoff,
            pytest.raises(SendGridImportError),
        ):
            sg.send_template(to="a@example.com", template_id="d-1")
        mock_backoff.assert_not_called()

    def test_programming_error_propagates_unretried_and_unwrapped(self, fake_api_client: MagicMock) -> None:
        """A bug in the SDK call (e.g. malformed payload) is not a send failure."""
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", max_retries=2, retry_delay=0.1)
        sg._client = fake_api_client
        fake_api_client.send.side_effect = TypeError("bad payload")

        with patch.object(sg, "_backoff") as mock_backoff, pytest.raises(TypeError, match="bad payload"):
            sg.send_template(to="a@example.com", template_id="d-1")
        mock_backoff.assert_not_called()
        fake_api_client.send.assert_called_once()

    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionError("connection reset"),
            TimeoutError("timed out"),
            urllib.error.URLError("dns failure"),
        ],
        ids=["ConnectionError", "TimeoutError", "URLError"],
    )
    def test_transport_errors_are_retried(self, fake_api_client: MagicMock, exc: Exception) -> None:
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", max_retries=2, retry_delay=0.1)
        sg._client = fake_api_client
        fake_api_client.send.side_effect = [exc, FakeResponse(status_code=202)]

        with patch.object(sg, "_backoff"):
            result = sg.send_template(to="a@example.com", template_id="d-1")
        assert result.ok is True
        assert fake_api_client.send.call_count == 2

    def test_real_http_error_with_permanent_status_not_retried(self, fake_api_client: MagicMock) -> None:
        from python_http_client.exceptions import BadRequestsError

        sg = SendGridClient(
            api_key="SG.test",
            default_from="sender@example.com",
            max_retries=2,
            retry_delay=0.1,
            raise_on_error=False,
        )
        sg._client = fake_api_client
        fake_api_client.send.side_effect = BadRequestsError(400, "Bad Request", b"bad payload", {})

        with patch.object(sg, "_backoff") as mock_backoff:
            result = sg.send_template(to="a@example.com", template_id="d-1")
        assert result.ok is False
        assert result.status_code == 400
        mock_backoff.assert_not_called()
        fake_api_client.send.assert_called_once()

    def test_real_http_error_with_transient_status_is_retried(self, fake_api_client: MagicMock) -> None:
        from python_http_client.exceptions import ServiceUnavailableError

        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", max_retries=2, retry_delay=0.1)
        sg._client = fake_api_client
        fake_api_client.send.side_effect = [
            ServiceUnavailableError(503, "Service Unavailable", b"try again", {}),
            FakeResponse(status_code=202),
        ]

        with patch.object(sg, "_backoff"):
            result = sg.send_template(to="a@example.com", template_id="d-1")
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


class TestSandboxConfig:
    def test_default_no_sandbox(self) -> None:
        sg = SendGridClient(api_key="SG.test")
        assert sg._sandbox_mode is False

    def test_sandbox_enabled(self) -> None:
        sg = SendGridClient(api_key="SG.test", sandbox_mode=True)
        assert sg._sandbox_mode is True

    def test_from_env_sandbox_explicit_true(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test"}):
            sg = SendGridClient.from_env(sandbox_mode=True)
            assert sg._sandbox_mode is True

    def test_from_env_sandbox_explicit_false(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test", "SENDGRID_SANDBOX_MODE": "true"}):
            sg = SendGridClient.from_env(sandbox_mode=False)
            assert sg._sandbox_mode is False

    @pytest.mark.parametrize("env_value", ["1", "true", "True", "TRUE", "yes", "Yes", "YES"])
    def test_from_env_sandbox_from_env_var_truthy(self, env_value: str) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test", "SENDGRID_SANDBOX_MODE": env_value}):
            sg = SendGridClient.from_env()
            assert sg._sandbox_mode is True

    @pytest.mark.parametrize("env_value", ["0", "false", "no", "", "anything"])
    def test_from_env_sandbox_from_env_var_falsy(self, env_value: str) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test", "SENDGRID_SANDBOX_MODE": env_value}):
            sg = SendGridClient.from_env()
            assert sg._sandbox_mode is False

    def test_from_env_sandbox_missing_env_var(self) -> None:
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test"}, clear=True):
            sg = SendGridClient.from_env()
            assert sg._sandbox_mode is False


class TestResolveSandbox:
    def test_per_call_true_overrides_client_false(self) -> None:
        sg = SendGridClient(api_key="SG.test", sandbox_mode=False)
        assert sg._resolve_sandbox(True) is True

    def test_per_call_false_overrides_client_true(self) -> None:
        sg = SendGridClient(api_key="SG.test", sandbox_mode=True)
        assert sg._resolve_sandbox(False) is False

    def test_per_call_none_falls_back_to_client_true(self) -> None:
        sg = SendGridClient(api_key="SG.test", sandbox_mode=True)
        assert sg._resolve_sandbox(None) is True

    def test_per_call_none_falls_back_to_client_false(self) -> None:
        sg = SendGridClient(api_key="SG.test", sandbox_mode=False)
        assert sg._resolve_sandbox(None) is False


class TestSandboxBehavior:
    def test_sandbox_applies_mail_settings(self, fake_api_client: MagicMock) -> None:
        """Sandbox mode should set mail_settings on the Mail object."""
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", sandbox_mode=True)
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=200)

        result = sg.send_text(to="user@example.com", subject="Test", body="Hello")
        assert result.ok is True

        # Verify send was called and mail_settings was applied
        sent_message = fake_api_client.send.call_args[0][0]
        assert sent_message.mail_settings is not None
        assert sent_message.mail_settings.sandbox_mode is not None

    def test_no_sandbox_no_mail_settings(self, fake_api_client: MagicMock) -> None:
        """Without sandbox mode, mail_settings should not be set."""
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com")
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=202)

        sg.send_text(to="user@example.com", subject="Test", body="Hello")

        sent_message = fake_api_client.send.call_args[0][0]
        assert sent_message.mail_settings is None

    def test_per_call_sandbox_override(self, fake_api_client: MagicMock) -> None:
        """Per-call sandbox=True should enable sandbox even when client has it off."""
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", sandbox_mode=False)
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=200)

        sg.send_text(to="user@example.com", subject="Test", body="Hello", sandbox=True)

        sent_message = fake_api_client.send.call_args[0][0]
        assert sent_message.mail_settings is not None

    def test_per_call_sandbox_false_disables(self, fake_api_client: MagicMock) -> None:
        """Per-call sandbox=False should disable sandbox even when client has it on."""
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", sandbox_mode=True)
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=202)

        sg.send_text(to="user@example.com", subject="Test", body="Hello", sandbox=False)

        sent_message = fake_api_client.send.call_args[0][0]
        assert sent_message.mail_settings is None

    def test_sandbox_with_send_html(self, fake_api_client: MagicMock) -> None:
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", sandbox_mode=True)
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=200)

        result = sg.send_html(to="user@example.com", subject="Test", html="<p>Hi</p>")
        assert result.ok is True
        sent_message = fake_api_client.send.call_args[0][0]
        assert sent_message.mail_settings is not None

    def test_sandbox_with_send_template(self, fake_api_client: MagicMock) -> None:
        sg = SendGridClient(api_key="SG.test", default_from="sender@example.com", sandbox_mode=True)
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=200)

        result = sg.send_template(to="user@example.com", template_id="d-abc123")
        assert result.ok is True
        sent_message = fake_api_client.send.call_args[0][0]
        assert sent_message.mail_settings is not None


class TestResolveEmail:
    def test_string(self) -> None:
        result = SendGridClient._resolve_email("user@example.com")
        assert result.email == "user@example.com"
        assert result.name is None

    def test_tuple(self) -> None:
        result = SendGridClient._resolve_email(("user@example.com", "User Name"))
        assert result.email == "user@example.com"
        assert result.name == "User Name"

    def test_email_address_dataclass(self) -> None:
        from altissimo.sendgrid.models import EmailAddress

        result = SendGridClient._resolve_email(EmailAddress("user@example.com", "User Name"))
        assert result.email == "user@example.com"
        assert result.name == "User Name"

    def test_email_address_no_name(self) -> None:
        from altissimo.sendgrid.models import EmailAddress

        result = SendGridClient._resolve_email(EmailAddress("user@example.com"))
        assert result.email == "user@example.com"
        assert result.name is None

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported email address type"):
            SendGridClient._resolve_email(12345)  # type: ignore[arg-type]


class TestEmailAddressLikeSend:
    """Test that all EmailAddressLike forms work in send methods."""

    def test_from_as_tuple(self, fake_api_client: MagicMock) -> None:
        sg = SendGridClient(api_key="SG.test", default_from=("team@example.com", "My Team"))
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=202)

        result = sg.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is True

    def test_from_as_email_address(self, fake_api_client: MagicMock) -> None:
        from altissimo.sendgrid.models import EmailAddress

        sg = SendGridClient(api_key="SG.test", default_from=EmailAddress("team@example.com", "My Team"))
        sg._client = fake_api_client
        fake_api_client.send.return_value = FakeResponse(status_code=202)

        result = sg.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is True

    def test_per_call_from_as_tuple(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_html(
            to="user@example.com",
            subject="Hi",
            html="<p>Hi</p>",
            from_email=("ceo@example.com", "Jane Smith"),
        )
        assert result.ok is True

    def test_reply_to_as_tuple(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hi",
            body="Hello",
            reply_to=("support@example.com", "Support Team"),
        )
        assert result.ok is True

    def test_reply_to_as_email_address(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        from altissimo.sendgrid.models import EmailAddress

        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hi",
            body="Hello",
            reply_to=EmailAddress("support@example.com", "Support"),
        )
        assert result.ok is True

    def test_to_as_tuple(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to=("user@example.com", "User"),
            subject="Hi",
            body="Hello",
        )
        assert result.ok is True

    def test_to_as_email_address_list(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        from altissimo.sendgrid.models import EmailAddress

        result = client_with_mock.send_html(
            to=[EmailAddress("a@example.com", "Alice"), EmailAddress("b@example.com", "Bob")],
            subject="Hi",
            html="<p>Hi</p>",
        )
        assert result.ok is True

    def test_cc_as_tuple(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hi",
            body="Hello",
            cc=("cc@example.com", "CC Person"),
        )
        assert result.ok is True

    def test_bcc_as_email_address(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        from altissimo.sendgrid.models import EmailAddress

        result = client_with_mock.send_text(
            to="user@example.com",
            subject="Hi",
            body="Hello",
            bcc=EmailAddress("bcc@example.com", "BCC Person"),
        )
        assert result.ok is True

    def test_template_with_named_recipients(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        from altissimo.sendgrid.models import EmailAddress

        result = client_with_mock.send_template(
            to=[EmailAddress("user@example.com", "Alice")],
            template_id="d-abc123",
            dynamic_data={"name": "Alice"},
            from_email=("team@example.com", "My Team"),
            reply_to=EmailAddress("support@example.com", "Support"),
        )
        assert result.ok is True


class TestSuccessLogging:
    def test_send_text_logs_on_success(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        with patch("altissimo.sendgrid.client.logger") as mock_logger:
            result = client_with_mock.send_text(to="user@example.com", subject="Hello", body="Hi")
        assert result.ok is True
        mock_logger.info.assert_called_once()
        log_args = mock_logger.info.call_args
        assert "subject" in log_args[0][0]
        assert "Hello" in str(log_args)

    def test_send_html_logs_on_success(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        with patch("altissimo.sendgrid.client.logger") as mock_logger:
            result = client_with_mock.send_html(to="user@example.com", subject="Hi", html="<p>Hi</p>")
        assert result.ok is True
        mock_logger.info.assert_called_once()
        assert "subject" in mock_logger.info.call_args[0][0]

    def test_send_template_logs_on_success(self, client_with_mock: Any, fake_api_client: MagicMock) -> None:
        with patch("altissimo.sendgrid.client.logger") as mock_logger:
            result = client_with_mock.send_template(
                to="user@example.com", template_id="d-abc123", dynamic_data={"name": "Test"}
            )
        assert result.ok is True
        mock_logger.info.assert_called_once()
        assert "template" in mock_logger.info.call_args[0][0]
        assert "d-abc123" in str(mock_logger.info.call_args)

    def test_no_success_log_on_failure(self, client_no_raise: Any, fake_api_client: MagicMock) -> None:
        exc = Exception("fail")
        exc.status_code = 500  # type: ignore[attr-defined]
        fake_api_client.send.side_effect = exc
        with patch("altissimo.sendgrid.client.logger") as mock_logger:
            result = client_no_raise.send_text(to="user@example.com", subject="Hi", body="Hello")
        assert result.ok is False
        mock_logger.info.assert_not_called()

    def test_warns_with_context_on_swallowed_failure(self, client_no_raise: Any, fake_api_client: MagicMock) -> None:
        """In swallow mode the library logs the failure — with context, unlike before."""
        exc = Exception("bad sender")
        exc.status_code = 400  # type: ignore[attr-defined]
        fake_api_client.send.side_effect = exc

        with patch("altissimo.sendgrid.client.logger") as mock_logger:
            client_no_raise.send_html(
                to="user@example.com",
                subject="Reset your password",
                html="<p>Hi</p>",
            )
            mock_logger.warning.assert_called_once()
            rendered = mock_logger.warning.call_args[0][0] % mock_logger.warning.call_args[0][1:]

        assert "user@example.com" in rendered
        assert "Reset your password" in rendered
        assert "400" in rendered
