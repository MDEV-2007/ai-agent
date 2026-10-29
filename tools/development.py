"""Kod loyihalari uchun Git va test amallari."""
import os
import subprocess
import sys
from pathlib import Path

from safety.approval import request_approval
from tools.base import Tool, registry

PROJECT_DIR = Path(os.getenv("PROJECT_DIR", ".")).resolve()
OUTPUT_LIMIT = 12000
TIMEOUT_SEC = 90


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, cwd=PROJECT_DIR, capture_output=True, text=True, timeout=TIMEOUT_SEC)
    except FileNotFoundError:
        return f"XATO: `{args[0]}` topilmadi."
    except subprocess.TimeoutExpired:
        return f"XATO: amal {TIMEOUT_SEC} soniyada tugamadi."
    output = (result.stdout + "\n" + result.stderr).strip()
    if len(output) > OUTPUT_LIMIT:
        output = output[:OUTPUT_LIMIT] + "\n... (natija qisqartirildi)"
    return f"{output or '(natija yo\'q)'}\nExit code: {result.returncode}"


class DevelopmentWorkflowTool(Tool):
    name = "development_workflow"
    description = "Git status/diff, standart testlar yoki tasdiq bilan commit yaratadi."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "diff", "tests", "commit"]},
            "message": {"type": "string", "description": "commit uchun xabar"},
        },
        "required": ["action"],
    }

    def run(self, action: str, message: str = "") -> str:
        if action == "status":
            return _run(["git", "status", "--short", "--branch"])
        if action == "diff":
            return _run(["git", "diff", "--stat"]) + "\n\n" + _run(["git", "diff", "--check"])
        if action == "tests":
            if (PROJECT_DIR / "pytest.ini").exists() or (PROJECT_DIR / "tests").exists():
                return _run([sys.executable, "-m", "pytest"])
            if (PROJECT_DIR / "package.json").exists():
                return _run(["npm", "test", "--", "--runInBand"])
            return "XATO: test sozlamasi topilmadi (tests/, pytest.ini yoki package.json yo'q)."
        if action == "commit":
            if not message.strip():
                return "XATO: commit uchun message kerak."
            if not request_approval(f"Git commit yaratiladi: {message}"):
                return "Foydalanuvchi commitni rad etdi."
            return _run(["git", "add", "-A"]) + "\n\n" + _run(["git", "commit", "-m", message.strip()])
        return "XATO: noma'lum workflow amali."


registry.register(DevelopmentWorkflowTool())
