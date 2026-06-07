"""SendGrid email client with typed wrappers for common operations."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import TYPE_CHECKING, Any

from altissimo.sendgrid.exceptions import SendGridImportError
from altissimo.sendgrid.models import SendResult

if TYPE_CHECKING:
    from sendgrid import SendGridAPIClient

logger = logging.getLogger(__name__)

#: Type alias for recipient arguments — a single email or a list of emails.
EmailRecipients = str | list[str]

#: HTTP status codes that are considered transient and eligible for retry.
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

__all__ = ["SendGridClient"]


def _get_sendgrid_api_client(api_key: str) -> SendGridAPIClient:
    """Lazily import and instantiate the SendGrid SDK client.

    Raises:
        SendGridImportError: If the ``sendgrid`` package is not installed.
    """
    try:
        from sendgrid import SendGridAPIClient as _Client
    except ImportError:
        raise SendGridImportError from None

    return _Client(api_key=api_key)


class SendGridClient:
    """Thin, typed wrapper around the SendGrid SDK.

    Provides three convenience methods for the most common email operations:
    plain-text, HTML, and dynamic template emails.

    The underlying ``SendGridAPIClient`` is lazily initialized on the first
    send call, so constructing a ``SendGridClient`` is side-effect-free.

    Args:
        api_key: SendGrid API key.
        default_from: Default sender email address. Used when ``from_email``
            is not provided to individual send methods.
        max_retries: Maximum number of retry attempts for transient errors.
            Set to ``0`` (default) to disable retries.
        retry_delay: Base delay in seconds between retries. Actual delay
            uses exponential backoff with jitter.
    """

    def __init__(
        self,
        api_key: str,
        default_from: str | None = None,
        *,
        max_retries: int = 0,
        retry_delay: float = 1.0,
    ) -> None:
        self._api_key = api_key
        self._default_from = default_from
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._client: SendGridAPIClient | None = None

    @classmethod
    def from_env(
        cls,
        *,
        env_var: str = "SENDGRID_API_KEY",
        default_from: str | None = None,
        max_retries: int = 0,
        retry_delay: float = 1.0,
    ) -> SendGridClient:
        """Create a client using an API key from an environment variable.

        Args:
            env_var: Name of the environment variable containing the API key.
            default_from: Default sender email address.
            max_retries: Maximum number of retry attempts for transient errors.
            retry_delay: Base delay in seconds between retries.

        Raises:
            ValueError: If the environment variable is not set.
        """
        api_key = os.environ.get(env_var)
        if not api_key:
            msg = f"Environment variable '{env_var}' is not set or is empty."
            raise ValueError(msg)
        return cls(api_key=api_key, default_from=default_from, max_retries=max_retries, retry_delay=retry_delay)

    @property
    def client(self) -> SendGridAPIClient:
        """Return the lazily-initialized ``SendGridAPIClient``."""
        if self._client is None:
            self._client = _get_sendgrid_api_client(self._api_key)
        return self._client

    def _resolve_from(self, from_email: str | None) -> str:
        """Resolve the sender email, falling back to the default.

        Raises:
            ValueError: If no sender email is provided or configured.
        """
        resolved = from_email or self._default_from
        if not resolved:
            msg = "No sender email provided. Pass 'from_email' to the send method or set 'default_from' on the client."
            raise ValueError(msg)
        return resolved

    @staticmethod
    def _normalize_recipients(recipients: EmailRecipients) -> list[str]:
        """Normalize a recipient argument to a list of email strings."""
        if isinstance(recipients, str):
            return [recipients]
        return list(recipients)

    @staticmethod
    def _apply_cc_bcc(
        message: Any,
        cc: EmailRecipients | None,
        bcc: EmailRecipients | None,
    ) -> None:
        """Add CC and BCC recipients to the first personalization."""
        if not cc and not bcc:
            return

        try:
            from sendgrid.helpers.mail import Bcc, Cc
        except ImportError:
            raise SendGridImportError from None

        # SendGrid Mail objects store a list of Personalization objects;
        # we add CC/BCC to the first one (the primary personalization).
        personalization = message.personalizations[0]

        if cc:
            cc_list = [cc] if isinstance(cc, str) else cc
            for addr in cc_list:
                personalization.add_cc(Cc(addr))

        if bcc:
            bcc_list = [bcc] if isinstance(bcc, str) else bcc
            for addr in bcc_list:
                personalization.add_bcc(Bcc(addr))

    def _build_result(self, response: Any) -> SendResult:
        """Convert a SendGrid API response to a ``SendResult``."""
        status_code = response.status_code
        body = response.body.decode() if isinstance(response.body, bytes) else str(response.body or "")
        headers = dict(response.headers) if response.headers else {}

        return SendResult(
            ok=200 <= status_code < 300,
            status_code=status_code,
            body=body,
            headers=headers,
        )

    def _build_error_result(self, exc: Exception) -> SendResult:
        """Build a ``SendResult`` from an exception."""
        logger.exception("SendGrid API error")
        return SendResult(
            ok=False,
            status_code=0,
            error=str(exc),
        )

    def _send_with_retry(self, message: Any) -> SendResult:
        """Send a message, retrying on transient failures with exponential backoff.

        Retries are only attempted when ``max_retries > 0`` and the response
        status code is in ``_RETRYABLE_STATUS_CODES``.
        """
        last_result: SendResult | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = self.client.send(message)
            except Exception as exc:
                last_result = self._build_error_result(exc)
                # Exceptions (network errors, etc.) are also retryable
                if attempt < self._max_retries:
                    self._backoff(attempt)
                    continue
                return last_result

            result = self._build_result(response)

            if result.ok or result.status_code not in _RETRYABLE_STATUS_CODES:
                return result

            # Transient failure — retry if we have attempts left
            last_result = result
            if attempt < self._max_retries:
                logger.warning(
                    "SendGrid returned %d, retrying (attempt %d/%d)",
                    result.status_code,
                    attempt + 1,
                    self._max_retries,
                )
                self._backoff(attempt)

        # All retries exhausted — return the last result
        return last_result  # type: ignore[return-value]

    def _backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff and jitter."""
        delay = self._retry_delay * (2**attempt)
        jitter = random.uniform(0, delay * 0.5)  # noqa: S311
        time.sleep(delay + jitter)

    def send_text(
        self,
        *,
        to: EmailRecipients,
        subject: str,
        body: str,
        from_email: str | None = None,
        reply_to: str | None = None,
        cc: EmailRecipients | None = None,
        bcc: EmailRecipients | None = None,
    ) -> SendResult:
        """Send a plain-text email.

        Args:
            to: Recipient email address or list of addresses.
            subject: Email subject line.
            body: Plain-text email body.
            from_email: Sender email address (overrides ``default_from``).
            reply_to: Reply-to email address.
            cc: CC recipient(s) — a single email or list of emails.
            bcc: BCC recipient(s) — a single email or list of emails.

        Returns:
            A ``SendResult`` with the API response details.
        """
        try:
            from sendgrid.helpers.mail import Mail
        except ImportError:
            raise SendGridImportError from None

        sender = self._resolve_from(from_email)
        message = Mail(
            from_email=sender,
            to_emails=self._normalize_recipients(to),
            subject=subject,
            plain_text_content=body,
        )

        self._apply_cc_bcc(message, cc, bcc)

        if reply_to:
            from sendgrid.helpers.mail import ReplyTo

            message.reply_to = ReplyTo(reply_to)

        return self._send_with_retry(message)

    def send_html(
        self,
        *,
        to: EmailRecipients,
        subject: str,
        html: str,
        from_email: str | None = None,
        reply_to: str | None = None,
        cc: EmailRecipients | None = None,
        bcc: EmailRecipients | None = None,
    ) -> SendResult:
        """Send an HTML email.

        Args:
            to: Recipient email address or list of addresses.
            subject: Email subject line.
            html: HTML email body.
            from_email: Sender email address (overrides ``default_from``).
            reply_to: Reply-to email address.
            cc: CC recipient(s) — a single email or list of emails.
            bcc: BCC recipient(s) — a single email or list of emails.

        Returns:
            A ``SendResult`` with the API response details.
        """
        try:
            from sendgrid.helpers.mail import Mail
        except ImportError:
            raise SendGridImportError from None

        sender = self._resolve_from(from_email)
        message = Mail(
            from_email=sender,
            to_emails=self._normalize_recipients(to),
            subject=subject,
            html_content=html,
        )

        self._apply_cc_bcc(message, cc, bcc)

        if reply_to:
            from sendgrid.helpers.mail import ReplyTo

            message.reply_to = ReplyTo(reply_to)

        return self._send_with_retry(message)

    def send_template(
        self,
        *,
        to: EmailRecipients,
        template_id: str,
        dynamic_data: dict[str, Any] | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
        cc: EmailRecipients | None = None,
        bcc: EmailRecipients | None = None,
    ) -> SendResult:
        """Send a dynamic template email.

        Args:
            to: Recipient email address or list of addresses.
            template_id: SendGrid dynamic template ID (e.g. ``d-abc123``).
            dynamic_data: Template variable substitutions.
            from_email: Sender email address (overrides ``default_from``).
            reply_to: Reply-to email address.
            cc: CC recipient(s) — a single email or list of emails.
            bcc: BCC recipient(s) — a single email or list of emails.

        Returns:
            A ``SendResult`` with the API response details.
        """
        try:
            from sendgrid.helpers.mail import Mail, To
        except ImportError:
            raise SendGridImportError from None

        sender = self._resolve_from(from_email)
        recipients = self._normalize_recipients(to)
        to_emails = [To(email=addr, dynamic_template_data=dynamic_data or {}) for addr in recipients]
        message = Mail(
            from_email=sender,
            to_emails=to_emails,
        )
        message.template_id = template_id

        self._apply_cc_bcc(message, cc, bcc)

        if reply_to:
            from sendgrid.helpers.mail import ReplyTo

            message.reply_to = ReplyTo(reply_to)

        return self._send_with_retry(message)
