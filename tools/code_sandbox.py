"""
Ixtiyoriy Python kodini xavfsiz bajarish tool'i. Kod hech qachon asosiy
tizimda ishlamaydi — faqat vaqtinchalik, tarmoqsiz (--network none),
avtomatik o'chiriladigan (--rm) Docker konteynerida, 30 soniya timeout bilan.
"""
import subprocess
import tempfile
from pathlib import Path

from tools.base import Tool, registry

DOCKER_TIMEOUT_SEC = 30
DOCKER_IMAGE = "python:3.11-slim"


class RunCodeTool(Tool):
    name = "run_code"
    description = (
        "Berilgan Python kodini izolyatsiyalangan Docker konteynerida bajaradi "
        "(tarmoqsiz, 30 soniya limit bilan) va stdout/stderr natijasini qaytaradi."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Bajariladigan Python kodi"},
        },
        "required": ["code"],
    }

    def run(self, code: str) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "script.py"
            script_path.write_text(code, encoding="utf-8")

            cmd = [
                "docker", "run", "--rm",
                "--network", "none",
                "--memory", "256m",
                "--cpus", "1",
                "-v", f"{tmpdir}:/sandbox:ro",
                DOCKER_IMAGE,
                "python", "/sandbox/script.py",
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=DOCKER_TIMEOUT_SEC
                )
            except FileNotFoundError:
                return "XATO: Docker topilmadi. Docker Desktop o'rnatilgan va ishga tushirilganini tekshiring."
            except subprocess.TimeoutExpired:
                return f"XATO: kod {DOCKER_TIMEOUT_SEC} soniyada tugamadi (timeout)."

        output = result.stdout.strip()
        error = result.stderr.strip()
        parts = []
        if output:
            parts.append(f"STDOUT:\n{output}")
        if error:
            parts.append(f"STDERR:\n{error}")
        parts.append(f"Exit code: {result.returncode}")
        return "\n".join(parts)


registry.register(RunCodeTool())
