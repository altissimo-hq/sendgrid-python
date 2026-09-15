# altissimo-sendgrid

[![CI](https://github.com/altissimo-hq/sendgrid-python/actions/workflows/ci.yml/badge.svg)](https://github.com/altissimo-hq/sendgrid-python/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Reusable SendGrid email client for Altissimo Python projects.

## Features

- 📧 **Plain text** emails via `send_text()`
- 🎨 **HTML** emails via `send_html()`
- 📋 **Dynamic templates** via `send_template()`
- 🏗️ **Factory method** — `SendGridClient.from_env()` reads `SENDGRID_API_KEY` from the environment
- 🔌 **Optional dependency** — `sendgrid` SDK is lazily imported with a helpful error message
- 📐 **Typed** — full type annotations with `py.typed` PEP 561 marker
- ✅ **Consistent return type** — all methods return a `SendResult` dataclass
- 🔄 **Retry with backoff** — configurable retry for transient failures
- 🔔 **Fails loudly** — send failures raise `SendGridSendError` by default; opt out per client for batch sends

## Requirements

- Python 3.11+

## Installation

```bash
pip install altissimo-sendgrid[sendgrid]   # core + SendGrid SDK
```

## Quick Start

```python
from altissimo.sendgrid import SendGridClient

client = SendGridClient.from_env()

# Plain text
result = client.send_text(
    to="user@example.com",
    subject="Hello",
    body="Welcome aboard!",
)

# HTML
result = client.send_html(
    to="user@example.com",
    subject="Hello",
    html="<h1>Welcome!</h1>",
    reply_to="support@example.com",
)

# Template
result = client.send_template(
    to="user@example.com",
    template_id="d-abc123",
    dynamic_data={"first_name": "Alice", "year": 2026},
)

print(result.status_code)
```

## Error Handling

By default a failed send raises `SendGridSendError`. The originating exception
is preserved as `__cause__`, and the full `SendResult` is attached as `.result`:

```python
from altissimo.sendgrid import SendGridClient, SendGridSendError

try:
    result = client.send_html(to="user@example.com", subject="Hi", html="<p>Hi</p>")
except SendGridSendError as exc:
    logger.error("Welcome email failed (status=%s): %s", exc.status_code, exc)
else:
    logger.info("Welcome email sent: status=%s", result.status_code)
```

For batch sends where one bad recipient should not abort the run, opt out and
check `result.ok` yourself:

```python
client = SendGridClient.from_env(raise_on_error=False)

for user in users:
    result = client.send_text(to=user.email, subject="Hi", body="Hello")
    if not result.ok:
        failures.append((user.email, result.status_code, result.error))
```

`SendResult.raise_for_status()` converts a result to an exception on demand
(mirroring `requests.Response.raise_for_status`), which is handy when you want
swallow semantics in one place and raise semantics in another:

```python
client.send_html(to=..., subject=..., html=...).raise_for_status()
```

> **Note:** the library does not log send failures above `DEBUG` when
> `raise_on_error=True` — it has no recipient or subject/template context
> worth logging from that frame, and a log there would make the failure look
> handled. Reporting is the caller's job.

## API Reference

### `SendGridClient`

| Method | Description |
|---|---|
| `SendGridClient(api_key, default_from?, max_retries?, retry_delay?, sandbox_mode?, raise_on_error?)` | Create a client with an explicit API key |
| `SendGridClient.from_env(env_var?, default_from?, max_retries?, retry_delay?, sandbox_mode?, raise_on_error?)` | Create a client from an environment variable |
| `send_text(to, subject, body, from_email?, reply_to?, cc?, bcc?, sandbox?)` | Send a plain-text email |
| `send_html(to, subject, html, from_email?, reply_to?, cc?, bcc?, sandbox?)` | Send an HTML email |
| `send_template(to, template_id, dynamic_data?, from_email?, reply_to?, cc?, bcc?, sandbox?)` | Send a dynamic template email |

### `SendResult`

| Field | Type | Description |
|---|---|---|
| `ok` | `bool` | Whether the request succeeded (2xx status) |
| `status_code` | `int` | HTTP status code from SendGrid |
| `body` | `str` | Response body |
| `headers` | `dict[str, str]` | Response headers |
| `error` | `str \| None` | Error message on failure |
| `exception` | `Exception \| None` | Originating exception on failure |

| Method | Description |
|---|---|
| `raise_for_status(context?)` | Raise `SendGridSendError` if `ok` is `False`; no-op otherwise |

### Exceptions

| Exception | Raised when |
|---|---|
| `SendGridError` | Base class for all library errors |
| `SendGridImportError` | The `sendgrid` SDK is not installed |
| `SendGridSendError` | A send failed (carries `status_code` and `result`) |

## Architecture

```text
altissimo.sendgrid
├── __init__.py       # Public API surface
├── client.py         # SendGridClient with lazy SDK initialization
├── exceptions.py     # SendGridError, SendGridImportError, SendGridSendError
├── models.py         # SendResult and EmailAddress dataclasses
└── py.typed          # PEP 561 marker
```

## Development

```bash
# Install all dependencies
poetry sync

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=altissimo --cov-report=term-missing

# Run linters
poetry run ruff check .
poetry run ruff format --check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## Security

For reporting security vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
