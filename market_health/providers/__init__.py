"""
Provider boundaries for optional/paid/external signals.

Rules:
- Must degrade gracefully when not configured.
- No secrets in repo.
- Prefer local-only config under ~/.config/jerboa/
"""
