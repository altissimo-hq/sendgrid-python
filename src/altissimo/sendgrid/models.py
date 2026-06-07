"""SendGrid email models."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    """

    ok: bool
    status_code: int
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None
