"""Tests for the altissimo.sendgrid public API surface."""

from __future__ import annotations


class TestPublicAPI:
    def test_imports(self) -> None:
        from altissimo.sendgrid import (
            SendGridClient,
            SendGridError,
            SendGridImportError,
            SendGridSendError,
            SendResult,
        )

        assert SendGridClient is not None
        assert SendResult is not None
        assert SendGridError is not None
        assert SendGridImportError is not None
        assert SendGridSendError is not None

    def test_version(self) -> None:
        from altissimo.sendgrid import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_all_exports(self) -> None:
        import altissimo.sendgrid as sg

        assert hasattr(sg, "__all__")
        for name in sg.__all__:
            assert hasattr(sg, name), f"{name} listed in __all__ but not accessible"
