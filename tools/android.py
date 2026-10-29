"""
Android telefonni ADB orqali boshqarish tool'lari. Telefonda USB debugging
yoqilgan va `adb` PATH'da mavjud bo'lishi kerak (test/eski telefon tavsiya
etiladi). SMS yuborish kabi qaytarib bo'lmaydigan amal ikki bosqichli
himoyaga ega: (1) agentdan tasdiq so'raladi, (2) SMS avtomatik yuborilmaydi —
faqat oldindan to'ldirilgan holda ochiladi, jismoniy "Yuborish" tugmasini
foydalanuvchi telefonning o'zida bosishi kerak.
"""
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List

from safety.approval import request_approval
from tools.base import Tool, registry

ADB_TIMEOUT_SEC = 20


def _adb(args: List[str]) -> str:
    try:
        result = subprocess.run(
            ["adb", *args], capture_output=True, text=True, timeout=ADB_TIMEOUT_SEC
        )
    except FileNotFoundError:
        return "XATO: 'adb' topilmadi. Android SDK platform-tools o'rnatilganini tekshiring."
    except subprocess.TimeoutExpired:
        return f"XATO: adb buyrug'i {ADB_TIMEOUT_SEC} soniyada javob bermadi."

    output = result.stdout.strip()
    error = result.stderr.strip()
    if result.returncode != 0:
        return f"XATO: {error or output or 'adb buyrugi muvaffaqiyatsiz tugadi'}"
    return output or "Bajarildi."


class AndroidOpenAppTool(Tool):
    name = "android_open_app"
    description = "Android telefonda dastur ochadi (package nomi bo'yicha, masalan 'com.whatsapp')."
    parameters = {
        "type": "object",
        "properties": {
            "package": {"type": "string", "description": "Android package nomi"},
        },
        "required": ["package"],
    }

    def run(self, package: str) -> str:
        return _adb(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])


class AndroidTapTool(Tool):
    name = "android_tap"
    description = "Android ekranida berilgan x,y koordinataga bosadi."
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X koordinata (piksel)"},
            "y": {"type": "integer", "description": "Y koordinata (piksel)"},
        },
        "required": ["x", "y"],
    }

    def run(self, x: int, y: int) -> str:
        return _adb(["shell", "input", "tap", str(x), str(y)])


class AndroidTypeTool(Tool):
    name = "android_type"
    description = "Android'da joriy faol input maydoniga matn kiritadi."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Kiritiladigan matn"},
        },
        "required": ["text"],
    }

    def run(self, text: str) -> str:
        escaped = text.replace(" ", "%s")
        return _adb(["shell", "input", "text", escaped])


class AndroidScreenshotTool(Tool):
    name = "android_screenshot"
    description = "Android ekranining skrinshotini oladi va workspace'ga saqlaydi."
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self) -> str:
        import os

        workspace = Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        filename = f"android_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        device_path = "/sdcard/_agent_screenshot.png"

        capture_result = _adb(["shell", "screencap", "-p", device_path])
        if capture_result.startswith("XATO"):
            return capture_result

        local_path = workspace / filename
        pull_result = _adb(["pull", device_path, str(local_path)])
        _adb(["shell", "rm", device_path])
        if pull_result.startswith("XATO"):
            return pull_result
        return f"Skrinshot saqlandi: {filename}"


class AndroidSendSmsTool(Tool):
    name = "android_send_sms"
    description = (
        "Android telefonda SMS yuborish oynasini raqam va matn bilan oldindan to'ldirib ochadi. "
        "Xabar avtomatik yuborilmaydi — foydalanuvchi telefonning o'zida 'Yuborish' tugmasini "
        "bosishi shart."
    )
    parameters = {
        "type": "object",
        "properties": {
            "phone_number": {"type": "string", "description": "Qabul qiluvchi telefon raqami"},
            "message": {"type": "string", "description": "SMS matni"},
        },
        "required": ["phone_number", "message"],
    }

    def run(self, phone_number: str, message: str) -> str:
        if not request_approval(f'SMS oynasi ochiladi: {phone_number} -> "{message}"'):
            return "Foydalanuvchi SMS yuborishni rad etdi."

        return _adb(
            [
                "shell", "am", "start",
                "-a", "android.intent.action.SENDTO",
                "-d", f"sms:{phone_number}",
                "--es", "sms_body", message,
            ]
        )


registry.register(AndroidOpenAppTool())
registry.register(AndroidTapTool())
registry.register(AndroidTypeTool())
registry.register(AndroidScreenshotTool())
registry.register(AndroidSendSmsTool())
