"""
Broker adapters live here.

Design rules:
- No secrets in repo.
- Providers read local-only config under ~/.config/jerboa/
- Providers write tokens under ~/.cache/jerboa/
"""
