"""Shared test fixtures for altissimo-sendgrid."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest


@dataclass
class FakeResponse:
    """Mimics a SendGrid API response for testing."""

    status_code: int = 202
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


@pytest.fixture
def fake_api_client() -> MagicMock:
    """Return a mock SendGridAPIClient whose ``send`` returns a 202."""
    mock = MagicMock()
    mock.send.return_value = FakeResponse(status_code=202)
    return mock


@pytest.fixture
def client_with_mock(fake_api_client: MagicMock) -> Any:
    """Return a ``SendGridClient`` wired to the fake API client."""
    from altissimo.sendgrid import SendGridClient

    sg = SendGridClient(api_key="SG.fake-key", default_from="sender@example.com")
    sg._client = fake_api_client
    return sg
