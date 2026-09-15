"""SendGrid email client with typed wrappers for common operations."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import TYPE_CHECKING, Any

from altissimo.sendgrid.exceptions import SendGridImportError
from altissimo.sendgrid.models import EmailAddress, SendResult

if TYPE_CHECKING:
    from sendgrid import SendGridAPIClient

logger = logging.getLogger(__name__)

#: Flexible type for email address arguments — plain string, (email, name) tuple,
#: or :class:`EmailAddress` dataclass.
EmailAddressLike = str | tuple[str, str] | EmailAddress

#: Type alias for recipient arguments — a single address or a list of addresses.
#: Each element can be any :data:`EmailAddressLike` form.
EmailRecipients = EmailAddressLike | list[EmailAddressLike]

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
    send call, so constructing a ``SendGridClient`` — via either the
    constructor or :meth:`from_env` — is side-effect-free.

    Args:
        api_key: SendGrid API key.
        default_from: Default sender email address. Accepts a plain string,
            a ``(email, name)`` tuple, or an :class:`EmailAddress`.
        max_retries: Maximum number of retry attempts for transient errors.
            Set to ``0`` (default) to disable retries.
        retry_delay: Base delay in seconds between retries. Actual delay
            uses exponential backoff with jitter.
        sandbox_mode: When ``True``, all sends use SendGrid sandbox mode
            (validates without delivering). Can be overridden per-call.
        raise_on_error: If ``True`` (default), a failed send raises
            :class:`SendGridSendError` instead of returning a
            ``SendResult`` with ``ok=False``. Set to ``False`` for batch
            sends where you want to inspect results and continue past a
            failed recipient — but then you are responsible for checking
            ``result.ok``, because nothing else will.
    """

    def __init__(
        self,
        api_key: str,
        default_from: EmailAddressLike | None = None,
        *,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        sandbox_mode: bool = False,
        raise_on_error: bool = True,
    ) -> None:
        self._init_common(default_from, max_retries, retry_delay, sandbox_mode, raise_on_error)
        self._api_key: str | None = api_key
        self._api_key_env_var: str | None = None

    def _init_common(
        self,
        default_from: EmailAddressLike | None,
        max_retries: int,
        retry_delay: float,
        sandbox_mode: bool,
        raise_on_error: bool,
    ) -> None:
        self._default_from = default_from
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._sandbox_mode = sandbox_mode
        self._raise_on_error = raise_on_error
        self._client: SendGridAPIClient | None = None

    @classmethod
    def from_env(
        cls,
        *,
        env_var: str = "SENDGRID_API_KEY",
        default_from: EmailAddressLike | None = None,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        sandbox_mode: bool | None = None,
        raise_on_error: bool = True,
    ) -> SendGridClient:
        """Create a client that reads its API key from an environment variable.

        The environment variable is not read until the API key is actually
        needed (the first send call, or access to :attr:`client`) — this
        factory is just as side-effect-free as the regular constructor.

        Args:
            env_var: Name of the environment variable containing the API key.
            default_from: Default sender email address.
            max_retries: Maximum number of retry attempts for transient errors.
            retry_delay: Base delay in seconds between retries.
            sandbox_mode: Enable sandbox mode. If ``None`` (default), reads
                from the ``SENDGRID_SANDBOX_MODE`` environment variable
                (truthy values: ``1``, ``true``, ``yes``).
            raise_on_error: Raise :class:`SendGridSendError` on send failure.

        Raises:
            ValueError: If the environment variable is not set or is empty,
                raised lazily on first use rather than from this call.
        """
        if sandbox_mode is None:
            sandbox_mode = os.environ.get("SENDGRID_SANDBOX_MODE", "").lower() in ("1", "true", "yes")
        instance = cls.__new__(cls)
        instance._init_common(default_from, max_retries, retry_delay, sandbox_mode, raise_on_error)
        instance._api_key = None
        instance._api_key_env_var = env_var
        return instance

    def _resolve_api_key(self) -> str:
        """Return the API key, reading it from the environment on first use.

        Raises:
            ValueError: If the client was built via :meth:`from_env` and the
                configured environment variable is not set or is empty.
        """
        if self._api_key is not None:
            return self._api_key
        env_var = self._api_key_env_var
        api_key = os.environ.get(env_var) if env_var else None
        if not api_key:
            msg = f"Environment variable '{env_var}' is not set or is empty."
            raise ValueError(msg)
        self._api_key = api_key
        return api_key

    @property
    def client(self) -> SendGridAPIClient:
        """Return the lazily-initialized ``SendGridAPIClient``."""
        if self._client is None:
            self._client = _get_sendgrid_api_client(self._resolve_api_key())
        return self._client

    # ------------------------------------------------------------------
    # Email address resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_email(value: EmailAddressLike) -> Any:
        """Convert any email address format to a SendGrid ``Email`` object.

        Args:
            value: A plain string, ``(email, name)`` tuple, or :class:`EmailAddress`.

        Returns:
            A ``sendgrid.helpers.mail.Email`` instance.

        Raises:
            SendGridImportError: If the ``sendgrid`` package is not installed.
            TypeError: If *value* is not a supported type.
        """
        try:
            from sendgrid.helpers.mail import Email
        except ImportError:
            raise SendGridImportError from None

        if isinstance(value, str):
            return Email(value)
        if isinstance(value, tuple):
            return Email(email=value[0], name=value[1])
        if isinstance(value, EmailAddress):
            return Email(email=value.email, name=value.name)
        msg = f"Unsupported email address type: {type(value)}"
        raise TypeError(msg)

    @staticmethod
    def _resolve_to(
        value: EmailAddressLike,
        dynamic_template_data: dict[str, Any] | None = None,
    ) -> Any:
        """Convert an email address to a SendGrid ``To`` object.

        Args:
            value: A plain string, ``(email, name)`` tuple, or :class:`EmailAddress`.
            dynamic_template_data: Optional template data for dynamic templates.

        Returns:
            A ``sendgrid.helpers.mail.To`` instance.
        """
        try:
            from sendgrid.helpers.mail import To
        except ImportError:
            raise SendGridImportError from None

        if isinstance(value, str):
            return To(email=value, dynamic_template_data=dynamic_template_data)
        if isinstance(value, tuple):
            return To(email=value[0], name=value[1], dynamic_template_data=dynamic_template_data)
        if isinstance(value, EmailAddress):
            return To(email=value.email, name=value.name, dynamic_template_data=dynamic_template_data)
        msg = f"Unsupported email address type: {type(value)}"
        raise TypeError(msg)

    def _resolve_from(self, from_email: EmailAddressLike | None) -> Any:
        """Resolve the sender email, falling back to the default.

        Returns:
            A ``sendgrid.helpers.mail.Email`` instance.

        Raises:
            ValueError: If no sender email is provided or configured.
        """
        resolved = from_email or self._default_from
        if not resolved:
            msg = "No sender email provided. Pass 'from_email' to the send method or set 'default_from' on the client."
            raise ValueError(msg)
        return self._resolve_email(resolved)

    @staticmethod
    def _normalize_recipients(recipients: EmailRecipients) -> list[EmailAddressLike]:
        """Normalize a recipient argument to a list."""
        if isinstance(recipients, list):
            return list(recipients)
        return [recipients]

    def _apply_cc_bcc(
        self,
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
            cc_list = self._normalize_recipients(cc)
            for addr in cc_list:
                resolved = self._resolve_email(addr)
                personalization.add_cc(Cc(email=resolved.email, name=resolved.name))

        if bcc:
            bcc_list = self._normalize_recipients(bcc)
            for addr in bcc_list:
                resolved = self._resolve_email(addr)
                personalization.add_bcc(Bcc(email=resolved.email, name=resolved.name))

    # ------------------------------------------------------------------
    # Result building
    # ------------------------------------------------------------------

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
        """Build a ``SendResult`` from an exception.

        Deliberately does not log at warning or above. The library has no
        recipient, subject, or template context here, so a log emitted from
        this frame is both unactionable and misleading — it makes the failure
        look handled. Reporting is the caller's job: the exception is
        preserved on the result, and the send methods either raise it or log
        it with full context.
        """
        status_code = 0
        if hasattr(exc, "status_code"):
            status_code = getattr(exc, "status_code", 0)
        elif hasattr(exc, "code"):
            status_code = getattr(exc, "code", 0)

        logger.debug("SendGrid API error (status=%s)", status_code, exc_info=exc)

        return SendResult(
            ok=False,
            status_code=status_code,
            error=str(exc),
            exception=exc,
        )

    # ------------------------------------------------------------------
    # Sandbox mode
    # ------------------------------------------------------------------

    def _resolve_sandbox(self, per_call: bool | None) -> bool:
        """Resolve sandbox mode: per-call overrides client-level."""
        if per_call is not None:
            return per_call
        return self._sandbox_mode

    @staticmethod
    def _apply_sandbox(message: Any, enabled: bool) -> None:
        """Enable SendGrid sandbox mode on a ``Mail`` object if requested."""
        if not enabled:
            return

        try:
            from sendgrid.helpers.mail import MailSettings, SandBoxMode
        except ImportError:
            raise SendGridImportError from None

        mail_settings = MailSettings()
        mail_settings.sandbox_mode = SandBoxMode(True)
        message.mail_settings = mail_settings

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def _send_with_retry(self, message: Any, *, context: str = "") -> SendResult:
        """Send a message, retrying on transient failures with exponential backoff.

        Retries are only attempted when ``max_retries > 0`` and the failure
        is transient — a response in ``_RETRYABLE_STATUS_CODES``, or an
        exception with no discoverable HTTP status (network errors, etc.).

        Args:
            message: The SendGrid ``Mail`` object to send.
            context: Description of the send, used in retry logs and in the
                raised exception message.

        Returns:
            A ``SendResult`` with the API response details.

        Raises:
            SendGridSendError: If the send ultimately failed and the client
                was constructed with ``raise_on_error=True`` (the default).
        """
        last_result: SendResult | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = self.client.send(message)
            except Exception as exc:
                last_result = self._build_error_result(exc)
            else:
                last_result = self._build_result(response)

            if last_result.ok:
                return last_result

            retryable = last_result.status_code in _RETRYABLE_STATUS_CODES or last_result.status_code == 0
            if attempt < self._max_retries and retryable:
                logger.warning(
                    "SendGrid error (status=%d) for %s, retrying (attempt %d/%d)",
                    last_result.status_code,
                    context or "send",
                    attempt + 1,
                    self._max_retries,
                )
                self._backoff(attempt)
                continue

            return self._finalize(last_result, context)

        # All retries exhausted
        return self._finalize(last_result, context)  # type: ignore[arg-type]

    def _finalize(self, result: SendResult, context: str = "") -> SendResult:
        """Raise if the send failed and ``raise_on_error`` is enabled, else return it."""
        if self._raise_on_error:
            result.raise_for_status(context or None)
        return result

    def _backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff and jitter."""
        delay = self._retry_delay * (2**attempt)
        jitter = random.uniform(0, delay * 0.5)  # noqa: S311
        time.sleep(delay + jitter)

    # ------------------------------------------------------------------
    # Send methods
    # ------------------------------------------------------------------

    def send_text(
        self,
        *,
        to: EmailRecipients,
        subject: str,
        body: str,
        from_email: EmailAddressLike | None = None,
        reply_to: EmailAddressLike | None = None,
        cc: EmailRecipients | None = None,
        bcc: EmailRecipients | None = None,
        sandbox: bool | None = None,
    ) -> SendResult:
        """Send a plain-text email.

        Args:
            to: Recipient email address or list of addresses.
            subject: Email subject line.
            body: Plain-text email body.
            from_email: Sender email (overrides ``default_from``). Accepts
                a string, ``(email, name)`` tuple, or :class:`EmailAddress`.
            reply_to: Reply-to email address. Accepts same forms as ``from_email``.
            cc: CC recipient(s) — a single address or list of addresses.
            bcc: BCC recipient(s) — a single address or list of addresses.
            sandbox: Enable sandbox mode for this call. Overrides client-level
                ``sandbox_mode`` when explicitly set.

        Returns:
            A ``SendResult`` with the API response details.
        """
        try:
            from sendgrid.helpers.mail import Mail
        except ImportError:
            raise SendGridImportError from None

        sender = self._resolve_from(from_email)
        recipients = self._normalize_recipients(to)
        to_emails = [self._resolve_to(r) for r in recipients]
        message = Mail(
            from_email=sender,
            to_emails=to_emails,
            subject=subject,
            plain_text_content=body,
        )

        self._apply_cc_bcc(message, cc, bcc)
        self._apply_sandbox(message, self._resolve_sandbox(sandbox))

        if reply_to:
            message.reply_to = self._resolve_email(reply_to)

        context = f"to={to} subject={subject!r}"
        result = self._send_with_retry(message, context=context)
        if result.ok:
            logger.info("Email sent: subject=%r to=%s status=%d", subject, to, result.status_code)
        else:
            # Only reachable when raise_on_error=False.
            logger.warning(
                "Email send failed: subject=%r to=%s status=%d error=%s",
                subject,
                to,
                result.status_code,
                result.error,
            )
        return result

    def send_html(
        self,
        *,
        to: EmailRecipients,
        subject: str,
        html: str,
        from_email: EmailAddressLike | None = None,
        reply_to: EmailAddressLike | None = None,
        cc: EmailRecipients | None = None,
        bcc: EmailRecipients | None = None,
        sandbox: bool | None = None,
    ) -> SendResult:
        """Send an HTML email.

        Args:
            to: Recipient email address or list of addresses.
            subject: Email subject line.
            html: HTML email body.
            from_email: Sender email (overrides ``default_from``). Accepts
                a string, ``(email, name)`` tuple, or :class:`EmailAddress`.
            reply_to: Reply-to email address. Accepts same forms as ``from_email``.
            cc: CC recipient(s) — a single address or list of addresses.
            bcc: BCC recipient(s) — a single address or list of addresses.
            sandbox: Enable sandbox mode for this call. Overrides client-level
                ``sandbox_mode`` when explicitly set.

        Returns:
            A ``SendResult`` with the API response details.
        """
        try:
            from sendgrid.helpers.mail import Mail
        except ImportError:
            raise SendGridImportError from None

        sender = self._resolve_from(from_email)
        recipients = self._normalize_recipients(to)
        to_emails = [self._resolve_to(r) for r in recipients]
        message = Mail(
            from_email=sender,
            to_emails=to_emails,
            subject=subject,
            html_content=html,
        )

        self._apply_cc_bcc(message, cc, bcc)
        self._apply_sandbox(message, self._resolve_sandbox(sandbox))

        if reply_to:
            message.reply_to = self._resolve_email(reply_to)

        context = f"to={to} subject={subject!r}"
        result = self._send_with_retry(message, context=context)
        if result.ok:
            logger.info("Email sent: subject=%r to=%s status=%d", subject, to, result.status_code)
        else:
            # Only reachable when raise_on_error=False.
            logger.warning(
                "Email send failed: subject=%r to=%s status=%d error=%s",
                subject,
                to,
                result.status_code,
                result.error,
            )
        return result

    def send_template(
        self,
        *,
        to: EmailRecipients,
        template_id: str,
        dynamic_data: dict[str, Any] | None = None,
        from_email: EmailAddressLike | None = None,
        reply_to: EmailAddressLike | None = None,
        cc: EmailRecipients | None = None,
        bcc: EmailRecipients | None = None,
        sandbox: bool | None = None,
    ) -> SendResult:
        """Send a dynamic template email.

        Args:
            to: Recipient email address or list of addresses.
            template_id: SendGrid dynamic template ID (e.g. ``d-abc123``).
            dynamic_data: Template variable substitutions.
            from_email: Sender email (overrides ``default_from``). Accepts
                a string, ``(email, name)`` tuple, or :class:`EmailAddress`.
            reply_to: Reply-to email address. Accepts same forms as ``from_email``.
            cc: CC recipient(s) — a single address or list of addresses.
            bcc: BCC recipient(s) — a single address or list of addresses.
            sandbox: Enable sandbox mode for this call. Overrides client-level
                ``sandbox_mode`` when explicitly set.

        Returns:
            A ``SendResult`` with the API response details.
        """
        try:
            from sendgrid.helpers.mail import Mail
        except ImportError:
            raise SendGridImportError from None

        sender = self._resolve_from(from_email)
        recipients = self._normalize_recipients(to)
        to_emails = [self._resolve_to(r, dynamic_template_data=dynamic_data or {}) for r in recipients]
        message = Mail(
            from_email=sender,
            to_emails=to_emails,
        )
        message.template_id = template_id

        self._apply_cc_bcc(message, cc, bcc)
        self._apply_sandbox(message, self._resolve_sandbox(sandbox))

        if reply_to:
            message.reply_to = self._resolve_email(reply_to)

        context = f"to={to} template={template_id}"
        result = self._send_with_retry(message, context=context)
        if result.ok:
            logger.info("Email sent: template=%s to=%s status=%d", template_id, to, result.status_code)
        else:
            # Only reachable when raise_on_error=False.
            logger.warning(
                "Email send failed: template=%s to=%s status=%d error=%s",
                template_id,
                to,
                result.status_code,
                result.error,
            )
        return result
