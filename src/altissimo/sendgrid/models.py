"""SendGrid email models."""

from __future__ import annotations

from dataclasses import dataclass, field

from altissimo.sendgrid.exceptions import SendGridSendError


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """An email address with an optional display name.

    Supports three input forms for convenience:

    - Plain string: ``"user@example.com"``
    - Tuple: ``("user@example.com", "Display Name")``
    - Dataclass: ``EmailAddress("user@example.com", "Display Name")``

    Attributes:
        email: The email address.
        name: Optional display name (e.g. ``"Darwin's Ark"``).
    """

    email: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class SendResult:
    """Structured result returned by all send methods.

    Attributes:
        ok: Whether the request was successful (2xx status code).
        status_code: HTTP status code from the SendGrid API.
        body: Response body as a string.
        headers: Response headers as a dictionary.
        error: Error message if the request failed, ``None`` otherwise.
        exception: The originating SDK exception if the request failed,
            ``None`` otherwise. Preserved so callers can log or re-raise it
            with their own context.
    """

    ok: bool
    status_code: int
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    exception: Exception | None = None

    def raise_for_status(self, context: str | None = None) -> None:
        """Raise :class:`SendGridSendError` if the send failed.

        Mirrors ``requests.Response.raise_for_status`` — a no-op on success,
        so it is safe to call unconditionally::

            client.send_html(to=..., subject=..., html=...).raise_for_status()

        Args:
            context: Optional description of what was being sent (e.g.
                ``"to=user@example.com subject='Reset your password'"``),
                included in the exception message.

        Raises:
            SendGridSendError: If ``ok`` is ``False``.
        """
        if self.ok:
            return

        detail = f" for {context}" if context else ""
        msg = f"SendGrid send failed (status={self.status_code}){detail}: {self.error}"
        raise SendGridSendError(msg, status_code=self.status_code, result=self) from self.exception
