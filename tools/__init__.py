"""
Tool paketi. Bu faylni import qilish barcha tool modullarini yuklaydi va ular
o'zlarini registry'ga ro'yxatdan o'tkazadi (har bir modul oxirida
`registry.register(...)` chaqiriladi). Yangi tool qo'shilganda uni shu yerga
ham import qilib qo'shish kerak.
"""
from tools import android, code_sandbox, desktop, filesystem, messaging, shell, web_music  # noqa: F401  — registratsiya uchun import qilinadi
from tools import collaboration, development  # noqa: F401
from tools.base import registry

__all__ = ["registry"]
