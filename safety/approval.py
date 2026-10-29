"""
Destruktiv amallar oldidan foydalanuvchidan tasdiq (ha/yo'q) so'rash moduli.
Standart holatda terminal orqali so'raydi, lekin handler'ni almashtirish
mumkin — masalan, FAZA 3'da piksel-ofis UI orqali (WebSocket + tugma bilan)
tasdiq so'rash uchun.
"""
from typing import Callable, Optional

# Tashqaridan (masalan frontend) almashtirilishi mumkin bo'lgan tasdiqlash funksiyasi
_approval_handler: Optional[Callable[[str], bool]] = None


def set_approval_handler(handler: Callable[[str], bool]) -> None:
    """Tasdiqlash mexanizmini almashtiradi (masalan, UI integratsiyasi uchun)."""
    global _approval_handler
    _approval_handler = handler


def _default_terminal_approval(reason: str) -> bool:
    answer = input(f"\n[TASDIQ KERAK] {reason}\nDavom etaymi? (ha/yo'q): ").strip().lower()
    return answer in ("ha", "h", "yes", "y")


def request_approval(reason: str) -> bool:
    """Foydalanuvchidan tasdiq so'raydi. Rozi bo'lsa True qaytaradi."""
    handler = _approval_handler or _default_terminal_approval
    return handler(reason)
