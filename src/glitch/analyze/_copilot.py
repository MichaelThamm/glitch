"""CopilotClient wrapper with persistent event loop and session lifecycle."""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path
from typing import Any

import copilot
from copilot import CopilotClient, SubprocessConfig
from copilot.session import PermissionHandler


_f = copilot.__file__
_copilot_bin = Path(_f if _f is not None else "/dev/null").parent / "bin" / "copilot"
if _copilot_bin.exists() and not os.access(_copilot_bin, os.X_OK):
    _copilot_bin.chmod(_copilot_bin.stat().st_mode | stat.S_IXUSR)


class CopilotSession:
    def __init__(
        self, token: str | None = None, model: str | None = None
    ) -> None:
        self._model = model
        self._token = token
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Any = None
        self._session: Any = None
        self._closed = False

    def classify(self, prompt: str) -> str:
        if self._closed:
            raise RuntimeError("Session is closed — cannot classify().")
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop.run_until_complete(self._send(prompt))

    async def _send(self, prompt: str) -> str:
        if self._client is None:
            if self._token:
                self._client = CopilotClient(
                    SubprocessConfig(github_token=self._token)
                )
            else:
                self._client = CopilotClient()

        if self._session is None:
            session_kwargs: dict[str, Any] = {}
            if self._model:
                session_kwargs["model"] = self._model
            self._session = await self._client.create_session(
                on_permission_request=PermissionHandler.approve_all,
                **session_kwargs,
            )

        response = await self._session.send_and_wait(
            prompt, timeout=300
        )
        if (
            response
            and hasattr(response, "data")
            and hasattr(response.data, "content")
        ):
            return response.data.content or ""
        return ""

    def close(self) -> None:
        self._closed = True
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        if self._session:
            try:
                loop.run_until_complete(self._session.disconnect())
            except Exception:
                pass
            self._session = None

        if self._client:
            try:
                loop.run_until_complete(self._client.stop())
            except Exception:
                pass
            self._client = None

        loop.close()
        self._loop = None