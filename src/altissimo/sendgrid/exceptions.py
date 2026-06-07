"""Exceptions for altissimo-sendgrid."""

from __future__ import annotations


class SendGridError(Exception):
    """Base exception for all altissimo-sendgrid errors."""


class SendGridImportError(SendGridError, ImportError):
    """Raised when the ``sendgrid`` SDK is not installed.

    Install with::

        pip install altissimo-sendgrid[sendgrid]
    """

    def __init__(self) -> None:
        super().__init__(
            "The 'sendgrid' package is required but not installed. "
            "Install it with: pip install altissimo-sendgrid[sendgrid]"
        )
