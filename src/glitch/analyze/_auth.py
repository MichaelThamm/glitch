"""Auth resolution: GITHUB_TOKEN → gh auth token fallback."""

from __future__ import annotations

import os
import shutil
import subprocess


class AuthError(Exception):
    """Copilot authentication failed."""


def resolve_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token

    if shutil.which("gh"):
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                token = result.stdout.strip()
                if token:
                    return token
        except (subprocess.TimeoutExpired, OSError):
            pass

    raise AuthError(
        "Copilot authentication failed.\n"
        "Set GITHUB_TOKEN environment variable or run: gh auth login"
    )
