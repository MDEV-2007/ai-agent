"""
Desktop avtomatlashtirish tool'lari: dastur ochish, matn kiritish, tugma
bosish, skrinshot olish. pyautogui orqali real sichqoncha/klaviatura
harakatini simulyatsiya qiladi. Import lazy (funksiya ichida) qilingan —
pyautogui o'rnatilmagan bo'lsa ham registry buzilmasin.
"""
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from tools.base import Tool, registry

WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


class OpenAppTool(Tool):
    name = "open_app"
    description = "Desktopda dastur (app) ochadi (masalan 'notepad', 'calc', 'chrome')."
    parameters = {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Ochiladigan dastur nomi yoki buyrug'i"},
        },
        "required": ["app_name"],
    }

    def run(self, app_name: str) -> str:
        try:
            if os.name == "nt":
                os.startfile(app_name)
            else:
                subprocess.Popen([app_name])
            return f"'{app_name}' ochildi."
        except Exception as exc:
            return f"XATO: '{app_name}' ochilmadi: {exc}"


class TypeTextTool(Tool):
    name = "type_text"
    description = "Joriy faol oynaga (masalan ochiq dastur) klaviaturadan matn kiritadi."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Kiritiladigan matn"},
        },
        "required": ["text"],
    }

    def run(self, text: str) -> str:
        import pyautogui

        time.sleep(0.3)  # faol oyna tayyor bo'lishi uchun qisqa kutish
        pyautogui.write(text, interval=0.02)
        return f"Matn kiritildi ({len(text)} belgi)."


class PressKeyTool(Tool):
    name = "press_key"
    description = "Klaviatura tugmasini yoki kombinatsiyasini bosadi (masalan 'enter', 'ctrl+s')."
    parameters = {
        "type": "object",
        "properties": {
            "keys": {"type": "string", "description": "Tugma nomi yoki '+' bilan ajratilgan kombinatsiya"},
        },
        "required": ["keys"],
    }

    def run(self, keys: str) -> str:
        import pyautogui

        parts = [k.strip() for k in keys.split("+")]
        if len(parts) > 1:
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(parts[0])
        return f"Bosildi: {keys}"


class ScreenshotTool(Tool):
    name = "screenshot"
    description = "Ekranning skrinshotini oladi va workspace ichiga saqlaydi, fayl nomini qaytaradi."
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self) -> str:
        import pyautogui

        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = WORKSPACE_DIR / filename
        pyautogui.screenshot(str(path))
        return f"Skrinshot saqlandi: {filename}"


class MouseClickTool(Tool):
    name = "mouse_click"
    description = "Ekranning berilgan x,y nuqtasiga sichqoncha bilan bosadi (chap/o'ng, bir/ikki marta)."
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X koordinata (piksel)"},
            "y": {"type": "integer", "description": "Y koordinata (piksel)"},
            "button": {"type": "string", "enum": ["left", "right"], "description": "Sichqoncha tugmasi"},
            "double": {"type": "boolean", "description": "Ikki marta bosishmi (double-click)"},
        },
        "required": ["x", "y"],
    }

    def run(self, x: int, y: int, button: str = "left", double: bool = False) -> str:
        import pyautogui

        if double:
            pyautogui.doubleClick(x, y, button=button)
        else:
            pyautogui.click(x, y, button=button)
        return f"Bosildi: ({x}, {y}) {button}{' x2' if double else ''}"


class ScrollTool(Tool):
    name = "scroll"
    description = "Ekranni yuqoriga (musbat) yoki pastga (manfiy) aylantiradi."
    parameters = {
        "type": "object",
        "properties": {
            "amount": {"type": "integer", "description": "Aylantirish miqdori: musbat=yuqoriga, manfiy=pastga"},
        },
        "required": ["amount"],
    }

    def run(self, amount: int) -> str:
        import pyautogui

        pyautogui.scroll(amount)
        return f"Aylantirildi: {amount}"


class WaitSecondsTool(Tool):
    name = "wait_seconds"
    description = (
        "Belgilangan soniya kutadi. Ketma-ket amallar orasida foydali — masalan "
        "'musiqani qo'y, 20 soniya kut, keyin to'xtat'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "seconds": {"type": "number", "description": "Kutish vaqti (soniya, maksimum 120)"},
        },
        "required": ["seconds"],
    }

    def run(self, seconds: float) -> str:
        seconds = max(0.0, min(float(seconds), 120.0))  # cheksiz kutishning oldini olamiz
        time.sleep(seconds)
        return f"{seconds:g} soniya kutildi."


class ClipboardTool(Tool):
    name = "clipboard"
    description = "Buferga (clipboard) matn yozadi yoki undagi matnni o'qiydi."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["copy", "paste"], "description": "copy=yozish, paste=o'qish"},
            "text": {"type": "string", "description": "copy uchun yoziladigan matn"},
        },
        "required": ["action"],
    }

    def run(self, action: str, text: str = "") -> str:
        try:
            import pyperclip
        except ImportError:
            return "XATO: pyperclip o'rnatilmagan."
        if action == "copy":
            pyperclip.copy(text)
            return f"Buferga yozildi ({len(text)} belgi)."
        return f"Buferdagi matn: {pyperclip.paste()}"


registry.register(OpenAppTool())
registry.register(TypeTextTool())
registry.register(PressKeyTool())
registry.register(ScreenshotTool())
registry.register(MouseClickTool())
registry.register(ScrollTool())
registry.register(WaitSecondsTool())
registry.register(ClipboardTool())
