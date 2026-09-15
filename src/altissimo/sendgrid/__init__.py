"""Altissimo SendGrid — reusable SendGrid email client."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .client import EmailAddressLike, EmailRecipients, SendGridClient
from .exceptions import SendGridError, SendGridImportError, SendGridSendError
from .models import EmailAddress, SendResult

try:
    __version__ = version("altissimo-sendgrid")
except PackageNotFoundError:
    __version__ = "0.2.0"

__all__ = [
    "EmailAddress",
    "EmailAddressLike",
    "EmailRecipients",
    "SendGridClient",
    "SendGridError",
    "SendGridImportError",
    "SendGridSendError",
    "SendResult",
    "__version__",
]
