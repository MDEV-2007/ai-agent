"""
Xavfsizlik moduli. Agent istalgan buyruqni bajaradi — hech narsa TAQIQLANMAGAN.

Tasdiq (Ha/Yo'q) faqat ikki holatda so'raladi:
  1. FAYL/PAPKA O'CHIRISH — foydalanuvchi talabi bilan har doim so'raladi.
     Ruxsat bersa o'chiradi, bermasa yo'q.
  2. Kompyuterni BUTUNLAY yo'q qiluvchi halokatli buyruqlar (disk formatlash,
     tizimni o'chirish...) — kichik LLM xato qilib chaqirmasligi uchun.

Qolgan hamma buyruqlar tasdiqsiz, erkin bajariladi.
"""
import re

# Hech narsa butunlay taqiqlanmaydi.
FORBIDDEN_PATTERNS: list[str] = []

# Fayl/papka O'CHIRISH buyruqlari — har doim tasdiq so'raydi.
DELETE_PATTERNS = [
    r"\brm\b",                 # unix: rm
    r"\brmdir\b",              # unix/win: rmdir
    r"\bunlink\b",
    r"\bdel\b",                # windows: del
    r"\berase\b",              # windows: erase
    r"(?<!\w)rd\s",            # windows: rd (rmdir)
    r"\bRemove-Item\b",        # powershell
    r"\bRemove-ItemProperty\b",
    r"\brimraf\b",
    r"shutil\.rmtree",         # python kodida ham
    r"os\.remove|os\.unlink|os\.rmdir",
]

# Halokatli, qaytarib bo'lmaydigan tizim buyruqlari — tasdiq so'raydi.
CATASTROPHIC_PATTERNS = [
    r":\(\)\s*\{\s*:\|:&\s*\};:",     # fork bomb
    r"mkfs(\.\w+)?\s+/dev",            # diskni formatlash
    r"dd\s+if=.*of=/dev/(sd|nvme|hd)", # diskni ustidan yozish
    r">\s*/dev/sd[a-z]",
    r"format\s+[a-zA-Z]:",             # Windows: format C:
    r"\bshutdown\b",
    r"\breboot\b",
    r"curl[^|]*\|\s*(bash|sh)\b",      # internetdan kod yuklab ishga tushirish
    r"wget[^|]*\|\s*(bash|sh)\b",
]


class DangerousCommandError(Exception):
    """Moslik uchun qoldirilgan (hech narsa taqiqlanmaydi)."""


def is_forbidden(command: str) -> bool:
    return False  # hech narsa taqiqlanmagan


def is_delete(command: str) -> bool:
    return any(re.search(p, command, re.IGNORECASE) for p in DELETE_PATTERNS)


def needs_confirmation(command: str) -> bool:
    """Fayl o'chirish yoki halokatli buyruq bo'lsa tasdiq talab qilinadi."""
    return is_delete(command) or any(
        re.search(p, command, re.IGNORECASE) for p in CATASTROPHIC_PATTERNS
    )


def check_command(command: str) -> None:
    """Hech narsani bloklamaydi (moslik uchun saqlangan bo'sh funksiya)."""
    return None
