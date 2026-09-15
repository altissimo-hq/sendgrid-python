# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-15

### Changed

- **BREAKING:** send failures now raise `SendGridSendError` by default instead of
  returning a `SendResult` with `ok=False`. Previously a failed send was
  indistinguishable from a successful one unless the caller remembered to check
  `result.ok` — and Python has no `must_use`, so nothing prompted them to. Pass
  `raise_on_error=False` to the constructor or `from_env()` to restore the previous
  behaviour for batch sends. (#7)
- `_build_error_result` no longer calls `logger.exception`. That log fired from a
  frame with no recipient, subject, or template context, so it was unactionable
  while making the failure look handled. Failures are now logged at `DEBUG` with
  `exc_info`, and reported to the caller instead — either as a raised exception or,
  in `raise_on_error=False` mode, as a `logger.warning` from the send method with
  full context. (#7)
- `status_code` on a failed send now reads the real HTTP status from the SendGrid
  SDK's exception (`exc.status_code`) instead of always being `0`, and retry
  classification now applies `_RETRYABLE_STATUS_CODES` to that path — a permanent
  `400`/`403` no longer burns the full retry/backoff schedule. (#7)
- Retry warnings now include the recipient and the subject or template being sent.
- `SendGridClient.from_env()` no longer reads or validates its environment variable
  at construction time — that read is now deferred to first use (the first send
  call, or access to `client`), matching the "side-effect-free construction"
  promise made for the regular constructor. (#10)

### Added

- `SendGridSendError`, exported from `altissimo.sendgrid`. Carries `status_code`
  and the failed `result`, and chains the originating exception as `__cause__`.
- `SendResult.raise_for_status(context?)` — mirrors
  `requests.Response.raise_for_status`; a no-op on success.
- `SendResult.exception` field preserving the originating exception so callers can
  log or re-raise it with their own context.
- `raise_on_error` parameter on `SendGridClient(...)` and
  `SendGridClient.from_env(...)` (default `True`).
- README "Error Handling" section covering both modes.

### Security

- Bumped `cryptography` (transitive, via the `sendgrid` SDK) from 48.0.0 to
  50.0.1, resolving four Dependabot advisories: GHSA-537c-gmf6-5ccf,
  GHSA-g6cj-pr64-35w5, GHSA-jwv3-5hgf-82ww, GHSA-m2h6-j472-rp4c.

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

[0.2.0]: https://github.com/altissimo-hq/sendgrid-python/releases/tag/v0.2.0
[0.1.0]: https://github.com/altissimo-hq/sendgrid-python/releases/tag/v0.1.0
