# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-07

### Added

- `SendGridClient` class with lazy `SendGridAPIClient` initialization
- `SendGridClient.from_env()` factory method (reads `SENDGRID_API_KEY` from environment)
- `send_text()` method for plain-text emails
- `send_html()` method for HTML emails
- `send_template()` method for dynamic template emails
- `SendResult` dataclass with `ok`, `status_code`, `body`, `headers`, `error` fields
- `sendgrid` SDK as an optional dependency with lazy import and helpful error message
- `py.typed` marker for PEP 561 typed package support
- Poetry 2 build system with `src/altissimo/sendgrid/` namespace layout
- Ruff linting and formatting configuration
- Pytest setup with unit tests
- Pre-commit hooks configuration
- GitHub Actions CI workflow (lint, test matrix 3.11–3.13, build verification)

[0.1.0]: https://github.com/altissimo-hq/sendgrid-python/releases/tag/v0.1.0
