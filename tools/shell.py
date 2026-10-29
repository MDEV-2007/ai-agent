"""
Shell buyruqlarini bajaruvchi tool. Xavfsizlik ikki bosqichda ta'minlanadi:
1) guards.py — butunlay taqiqlangan buyruqlarni bloklaydi (hech qachon o'tmaydi).
2) approval.py — shubhali (lekin taqiqlanmagan) buyruqlar uchun foydalanuvchidan
   tasdiq so'raydi.
"""
import subprocess

from safety.approval import request_approval
from safety.guards import DangerousCommandError, check_command, needs_confirmation
from tools.base import Tool, registry

SHELL_TIMEOUT_SEC = 30


class ShellTool(Tool):
    name = "run_shell"
    description = (
        "Terminalda shell buyrug'ini bajaradi va stdout/stderr natijasini qaytaradi. "
        "Faqat zarur bo'lgandagina ishlating; xavfli buyruqlar avtomatik bloklanadi."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Bajariladigan shell buyrug'i"},
        },
        "required": ["command"],
    }

    def run(self, command: str) -> str:
        try:
            check_command(command)
        except DangerousCommandError as exc:
            return f"XATO: {exc}"

        if needs_confirmation(command):
            if not request_approval(f"Quyidagi buyruq bajarilsin: `{command}`"):
                return "Foydalanuvchi buyruqni rad etdi."

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=SHELL_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            return f"XATO: buyruq {SHELL_TIMEOUT_SEC} soniyada tugamadi (timeout)."

        output = result.stdout.strip()
        error = result.stderr.strip()
        parts = []
        if output:
            parts.append(f"STDOUT:\n{output}")
        if error:
            parts.append(f"STDERR:\n{error}")
        parts.append(f"Exit code: {result.returncode}")
        return "\n".join(parts)


registry.register(ShellTool())
