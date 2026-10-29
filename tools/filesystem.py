"""
Fayl tizimi bilan ishlash tool'lari: o'qish, yozish, ro'yxatlash.

CHEKLOVSIZ: agent butun fayl tizimiga kira oladi. Yo'l nisbiy berilsa
WORKSPACE_DIR (BASE_DIR) ga nisbatan, absolyut berilsa (masalan Windows disk
yo'li yoki /home/...) o'sha joyga to'g'ridan-to'g'ri qo'llanadi. Ustidan
yozishda tasdiq so'ralmaydi.
"""
import os
from pathlib import Path

from tools.base import Tool, registry

# Nisbiy yo'llar uchun tayanch papka (absolyut yo'llar bunga bog'liq emas).
BASE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)


def _resolve(path: str) -> Path:
    """Yo'lni hal qiladi: absolyut bo'lsa o'zicha, nisbiy bo'lsa BASE_DIR'ga nisbatan.
    ~ (uy papka) va environment o'zgaruvchilari ham kengaytiriladi."""
    p = os.path.expanduser(os.path.expandvars(path.strip()))
    candidate = Path(p)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate.resolve()


class ReadFileTool(Tool):
    name = "read_file"
    description = "Istalgan faylni o'qiydi (absolyut yo'l yoki workspace'ga nisbatan)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Fayl yo'li (absolyut yoki nisbiy)"},
        },
        "required": ["path"],
    }

    def run(self, path: str) -> str:
        target = _resolve(path)
        if not target.exists():
            return f"XATO: fayl topilmadi: {path}"
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "XATO: fayl matn (text) formatida emas."
        except Exception as exc:
            return f"XATO: {exc}"


class WriteFileTool(Tool):
    name = "write_file"
    description = "Istalgan joyga faylga matn yozadi (absolyut yo'l yoki workspace'ga nisbatan). Ichma-ich papkalar avtomatik yaratiladi."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Fayl yo'li (absolyut yoki nisbiy)"},
            "content": {"type": "string", "description": "Faylga yoziladigan matn"},
        },
        "required": ["path", "content"],
    }

    def run(self, path: str, content: str) -> str:
        target = _resolve(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except Exception as exc:
            return f"XATO: {exc}"
        return f"Yozildi: {target} ({len(content)} belgi)"


class ListDirTool(Tool):
    name = "list_dir"
    description = "Istalgan papka tarkibini ro'yxatlaydi (absolyut yo'l yoki workspace'ga nisbatan)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Papka yo'li ('.' — workspace ildizi)"},
        },
        "required": [],
    }

    def run(self, path: str = ".") -> str:
        target = _resolve(path)
        if not target.exists():
            return f"XATO: papka topilmadi: {path}"
        try:
            entries = sorted(os.listdir(target))
        except Exception as exc:
            return f"XATO: {exc}"
        if not entries:
            return "(bo'sh papka)"
        return "\n".join(entries)


registry.register(ReadFileTool())
registry.register(WriteFileTool())
registry.register(ListDirTool())
