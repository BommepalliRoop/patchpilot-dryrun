"""Run external commands without blocking the event loop (RISKS E7) and without our secrets (RISKS S2)."""
from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

# What a child process may inherit. Windows needs a few more for git/python to find their config and temp dirs.
_ENV_KEEP = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL", "SSL_CERT_FILE")
_ENV_KEEP_PREFIXES = ("PIP_",)


class CommandResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


class CommandTimeout(Exception):
    def __init__(self, cmd: Sequence[str], timeout: float) -> None:
        super().__init__(f"command timed out after {timeout:g}s: {Path(cmd[0]).name}")
        self.timeout = timeout


def clean_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Only PATH, HOME and PIP_* style variables (RISKS S2) so API keys never reach scanned code or tools."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() in _ENV_KEEP or k.upper().startswith(_ENV_KEEP_PREFIXES)}
    env.update(extra or {})
    return env


async def run(cmd: Sequence[str], *, cwd: Path | str | None = None, env: Mapping[str, str] | None = None,
              timeout: float) -> CommandResult:
    """Run `cmd` (no shell) with a hard timeout; the process is killed on timeout. `env=None` means `clean_env()`."""
    child_env = dict(env) if env is not None else clean_env()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd, env=child_env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except NotImplementedError:  # event loop without subprocess support (Windows selector loop)
        return await asyncio.to_thread(_run_blocking, list(cmd), cwd, child_env, timeout)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise CommandTimeout(cmd, timeout) from None
    except asyncio.CancelledError:  # scan timeout (RISKS E6) cancels us: do not leave the child running
        proc.kill()
        raise
    return CommandResult(proc.returncode if proc.returncode is not None else -1,
                         out.decode("utf-8", "replace"), err.decode("utf-8", "replace"))


def _run_blocking(cmd: list[str], cwd: Path | str | None, env: dict[str, str], timeout: float) -> CommandResult:
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        raise CommandTimeout(cmd, timeout) from None
    return CommandResult(p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"))
