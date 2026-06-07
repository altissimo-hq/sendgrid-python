"""SendGrid email client with typed wrappers for common operations."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from altissimo.sendgrid.exceptions import SendGridImportError
from altissimo.sendgrid.models import SendResult

if TYPE_CHECKING:
    from sendgrid import SendGridAPIClient

logger = logging.getLogger(__name__)

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
    """

    def __init__(self, api_key: str, default_from: str | None = None) -> None:
        self._api_key = api_key
        self._default_from = default_from
        self._client: SendGridAPIClient | None = None

    @classmethod
    def from_env(
        cls,
        *,
        env_var: str = "SENDGRID_API_KEY",
        default_from: str | None = None,
    ) -> SendGridClient:
        """Create a client using an API key from an environment variable.

        Args:
            env_var: Name of the environment variable containing the API key.
            default_from: Default sender email address.

        Raises:
            ValueError: If the environment variable is not set.
        """
        api_key = os.environ.get(env_var)
        if not api_key:
            msg = f"Environment variable '{env_var}' is not set or is empty."
            raise ValueError(msg)
        return cls(api_key=api_key, default_from=default_from)

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

    def send_text(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        from_email: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Send a plain-text email.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plain-text email body.
            from_email: Sender email address (overrides ``default_from``).
            reply_to: Reply-to email address.

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
            to_emails=to,
            subject=subject,
            plain_text_content=body,
        )

        if reply_to:
            from sendgrid.helpers.mail import ReplyTo

            message.reply_to = ReplyTo(reply_to)

        try:
            response = self.client.send(message)
        except Exception as exc:
            return self._build_error_result(exc)

        return self._build_result(response)

    def send_html(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        from_email: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Send an HTML email.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            html: HTML email body.
            from_email: Sender email address (overrides ``default_from``).
            reply_to: Reply-to email address.

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
            to_emails=to,
            subject=subject,
            html_content=html,
        )

        if reply_to:
            from sendgrid.helpers.mail import ReplyTo

            message.reply_to = ReplyTo(reply_to)

        try:
            response = self.client.send(message)
        except Exception as exc:
            return self._build_error_result(exc)

        return self._build_result(response)

    def send_template(
        self,
        *,
        to: str,
        template_id: str,
        dynamic_data: dict[str, Any] | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Send a dynamic template email.

        Args:
            to: Recipient email address.
            template_id: SendGrid dynamic template ID (e.g. ``d-abc123``).
            dynamic_data: Template variable substitutions.
            from_email: Sender email address (overrides ``default_from``).
            reply_to: Reply-to email address.

        Returns:
            A ``SendResult`` with the API response details.
        """
        try:
            from sendgrid.helpers.mail import Mail, To
        except ImportError:
            raise SendGridImportError from None

        sender = self._resolve_from(from_email)
        message = Mail(
            from_email=sender,
            to_emails=To(
                email=to,
                dynamic_template_data=dynamic_data or {},
            ),
        )
        message.template_id = template_id

        if reply_to:
            from sendgrid.helpers.mail import ReplyTo

            message.reply_to = ReplyTo(reply_to)

        try:
            response = self.client.send(message)
        except Exception as exc:
            return self._build_error_result(exc)

        return self._build_result(response)
