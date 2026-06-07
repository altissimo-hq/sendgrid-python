"""Altissimo SendGrid — reusable SendGrid email client."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .client import SendGridClient
from .exceptions import SendGridError, SendGridImportError
from .models import SendResult

try:
    __version__ = version("altissimo-sendgrid")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = [
    "SendGridClient",
    "SendGridError",
    "SendGridImportError",
    "SendResult",
    "__version__",
]
