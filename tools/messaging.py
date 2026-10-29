"""
Telegram orqali xabar/fayl yuborish tool'i. Agent shu tool bilan natijalarni,
matnlarni yoki workspace ichidagi fayllarni Telegramga jo'natadi.

Standart holatda "egaga" (o'zingizga) yuboradi — bu Telegramdagi "Saved
Messages" kabi ishlaydi. Boshqa chat_id ko'rsatilsa (boshqa odamga yuborish)
xavfsizlik uchun tasdiq so'raladi.
"""
import os
from pathlib import Path

from safety.approval import request_approval
from tools.base import Tool, registry

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_FILE = Path(__file__).resolve().parent.parent / "telegram_owner.txt"
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()


def _default_chat() -> str | None:
    """Egangizning chat_id'si: .env dagi TELEGRAM_ALLOWED_IDS yoki owner faylidan."""
    ids = [x.strip() for x in os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",") if x.strip()]
    if not ids and OWNER_FILE.exists():
        ids = [x.strip() for x in OWNER_FILE.read_text(encoding="utf-8").split() if x.strip()]
    return ids[0] if ids else None


class SendTelegramTool(Tool):
    name = "send_telegram"
    description = (
        "Telegram orqali xabar (va ixtiyoriy fayl) yuboradi. chat_id berilmasa "
        "egangizga (o'zingizga) yuboriladi — 'Saved Messages' kabi. Foydalanuvchi "
        "'telegramga yubor', 'o'zimga jo'nat', 'saqlab qo'y' desa shu ishlatiladi."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Yuboriladigan matn (yoki fayl uchun izoh)"},
            "chat_id": {
                "type": "string",
                "description": "Qabul qiluvchi chat_id. Berilmasa — egangizga (o'zingizga).",
            },
            "file_path": {
                "type": "string",
                "description": "Ixtiyoriy: workspace ichidagi yuboriladigan fayl yo'li.",
            },
        },
        "required": ["text"],
    }

    def run(self, text: str, chat_id: str = "", file_path: str = "") -> str:
        import requests

        if not TOKEN:
            return "XATO: TELEGRAM_BOT_TOKEN sozlanmagan (.env)."

        owner = _default_chat()
        target = chat_id or owner
        if not target:
            return "XATO: qabul qiluvchi topilmadi. Avval botga /start yozing yoki chat_id bering."

        # Boshqa odamga (egadan boshqa) yuborilsa — tasdiq so'raymiz
        if chat_id and chat_id != owner:
            if not request_approval(f"Telegram xabar '{target}' ga yuboriladi: {text[:80]}"):
                return "Foydalanuvchi xabar yuborishni rad etdi."

        api = f"https://api.telegram.org/bot{TOKEN}"
        try:
            if file_path:
                target_file = (WORKSPACE_DIR / file_path).resolve()
                if WORKSPACE_DIR not in target_file.parents and target_file != WORKSPACE_DIR:
                    return f"XATO: fayl workspace ichida bo'lishi kerak: {file_path}"
                if not target_file.exists():
                    return f"XATO: fayl topilmadi: {file_path}"
                with target_file.open("rb") as f:
                    resp = requests.post(
                        f"{api}/sendDocument",
                        data={"chat_id": target, "caption": text[:1000]},
                        files={"document": f},
                        timeout=60,
                    )
            else:
                resp = requests.post(
                    f"{api}/sendMessage",
                    data={"chat_id": target, "text": text},
                    timeout=30,
                )
        except requests.RequestException as exc:
            return f"XATO: yuborishda muammo: {exc}"

        if resp.json().get("ok"):
            who = "o'zingizga" if target == owner else target
            return f"Telegramga yuborildi ({who})."
        return f"XATO: Telegram javobi: {resp.text[:150]}"


registry.register(SendTelegramTool())
