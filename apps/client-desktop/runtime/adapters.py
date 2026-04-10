from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .logutil import get_logger, short_text
from .models import AdapterDiagnostics, RuntimeProfile, TransportKind
from .paths import RUNTIME_DIR, ensure_runtime_dirs, expected_binary_layout

WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _async_subprocess_hidden_kwargs() -> dict:
    if platform.system() != "Windows" or not WINDOWS_CREATE_NO_WINDOW:
        return {}
    return {"creationflags": WINDOWS_CREATE_NO_WINDOW}


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(slots=True)
class ActiveProcessGroup:
    transport: str
    profile_id: str
    config_path: str
    tunnel_name: str
    pids: list[int]
    processes: list[asyncio.subprocess.Process] | None = None


class BaseRuntimeAdapter:
    transport: TransportKind
    binary_keys: tuple[str, ...] = ()

    def diagnostics(self) -> AdapterDiagnostics:
        layout = expected_binary_layout()
        binaries: dict[str, str | None] = {}
        ready = True
        notes: list[str] = []
        for key in self.binary_keys:
            candidate = layout.get(key)
            if candidate and Path(candidate).exists():
                binaries[key] = candidate
            else:
                binaries[key] = None
                ready = False
                notes.append(f"missing {key}")
        return AdapterDiagnostics(name=self.transport.value, ready=ready, binaries=binaries, notes=notes)

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        raise NotImplementedError

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        raise NotImplementedError

    @staticmethod
    def _write_config(tunnel_name: str, config_text: str, suffix: str = ".json") -> Path:
        ensure_runtime_dirs()
        path = RUNTIME_DIR / f"{tunnel_name}{suffix}"
        path.write_text((config_text or "").replace("\r\n", "\n").strip() + "\n", encoding="utf-8")
        return path


class LustAdapter(BaseRuntimeAdapter):
    transport = TransportKind.LUST
    binary_keys = ("lust_client", "tun2socks", "wintun_dll")

    async def connect(self, profile: RuntimeProfile) -> ActiveProcessGroup:
        diag = self.diagnostics()
        if not diag.ready:
            raise RuntimeError("LuST adapter is not ready: " + ", ".join(diag.notes))
        tunnel_name = profile.metadata.get("tunnel_name") or "onyxlust0"
        config_path = self._write_config(tunnel_name, profile.config_text or "{}", suffix=".json")
        binary = expected_binary_layout()["lust_client"]
        if platform.system() == "Windows":
            await self._cleanup_stale_windows_runtime()
        args = [binary, "--config", str(config_path)]
        get_logger("adapters").info("lust_connect_start profile_id=%s tunnel=%s argv=%s", profile.id, tunnel_name, args)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_async_subprocess_hidden_kwargs(),
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            get_logger("adapters").info("lust_connect_ok profile_id=%s tunnel=%s config=%s", profile.id, tunnel_name, config_path)
            return ActiveProcessGroup(
                transport=self.transport.value,
                profile_id=profile.id,
                config_path=str(config_path),
                tunnel_name=tunnel_name,
                pids=[proc.pid] if proc.pid is not None else [],
                processes=None,
            )
        stdout = ""
        stderr = ""
        if proc.stdout is not None:
            stdout = (await proc.stdout.read()).decode("utf-8", errors="replace").strip()
        if proc.stderr is not None:
            stderr = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
        detail = stderr or stdout or "lust client failed to start"
        try:
            parsed = json.loads(profile.config_text or "{}")
            endpoint = parsed.get("endpoint") if isinstance(parsed, dict) else None
            if isinstance(endpoint, dict):
                detail += " | endpoint=" + short_text(json.dumps(endpoint, ensure_ascii=True), 300)
        except Exception:
            pass
        raise RuntimeError(detail)

    async def disconnect(self, session: ActiveProcessGroup) -> None:
        get_logger("adapters").info("lust_disconnect_start tunnel=%s profile_id=%s pids=%s", session.tunnel_name, session.profile_id, session.pids)
        for pid in session.pids:
            if not pid:
                continue
            if platform.system() == "Windows":
                proc = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **_async_subprocess_hidden_kwargs(),
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode not in (0, 128):
                    detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
                    raise RuntimeError(detail or f"taskkill failed for lust pid {pid}")
            else:
                os.kill(pid, 15)
        if platform.system() == "Windows":
            await self._cleanup_stale_windows_runtime()
        get_logger("adapters").info("lust_disconnect_ok tunnel=%s profile_id=%s", session.tunnel_name, session.profile_id)

    async def _cleanup_stale_windows_runtime(self) -> None:
        layout = expected_binary_layout()
        lust_path = layout.get("lust_client")
        tun2socks_path = layout.get("tun2socks")
        if not lust_path and not tun2socks_path:
            return
        script_lines = [
            "$targets = @()",
        ]
        if lust_path:
            script_lines.append(f"$targets += {_ps_quote(str(Path(lust_path).resolve()))}")
        if tun2socks_path:
            script_lines.append(f"$targets += {_ps_quote(str(Path(tun2socks_path).resolve()))}")
        script_lines.extend(
            [
                "$normalized = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::OrdinalIgnoreCase)",
                "foreach ($item in $targets) { [void]$normalized.Add($item) }",
                "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath } | ForEach-Object {",
                "  if ($normalized.Contains($_.ExecutablePath)) {",
                "    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}",
                "  }",
                "}",
            ]
        )
        proc = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "; ".join(script_lines),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_async_subprocess_hidden_kwargs(),
        )
        await proc.communicate()


def build_runtime_adapters() -> dict[str, BaseRuntimeAdapter]:
    adapters: list[BaseRuntimeAdapter] = [
        LustAdapter(),
    ]
    return {adapter.transport.value: adapter for adapter in adapters}
