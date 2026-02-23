# Security Policy

## Reporting a vulnerability
If you discover a security issue, please **do not** open a public GitHub issue.

Instead, report it privately:
- Open a GitHub Security Advisory (preferred), or
- Email the maintainer with details and reproduction steps.

## Secrets hygiene
- Never commit API keys, tokens, or credentials.
- Use environment variables and local `.env` files (not committed).
- Rotate any leaked credentials immediately.

## Supported versions
Security fixes are applied to the active development branch and the most recent release tag.

