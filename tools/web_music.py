"""
Veb va musiqa bilan bog'liq tool'lar: YouTube'dan qidirib brauzerda ochish
va istalgan URL manzilni ochish.
"""
import webbrowser

from tools.base import Tool, registry


class PlayYoutubeTool(Tool):
    name = "play_youtube"
    description = (
        "YouTube'dan qo'shiq yoki video qidiradi va uni brauzerda ochib ijro etadi. "
        "Ixtiyoriy start_seconds bilan videoni ma'lum vaqtdan (masalan 20-sekunddan) "
        "boshlash mumkin."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Qidiriladigan qo'shiq yoki video nomi"},
            "start_seconds": {
                "type": "integer",
                "description": "Videoni shu sekunddan boshlash (masalan 20). Berilmasa 0 dan.",
            },
        },
        "required": ["query"],
    }

    def run(self, query: str, start_seconds: int = 0) -> str:
        try:
            from yt_dlp import YoutubeDL
        except ImportError:
            return "XATO: yt-dlp o'rnatilmagan. 'pip install yt-dlp' bajaring."

        options = {"quiet": True, "noplaylist": True, "default_search": "ytsearch1"}
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(query, download=False)
                entry = info["entries"][0] if "entries" in info else info
                url = entry["webpage_url"]
                title = entry.get("title", query)
        except Exception as exc:
            return f"XATO: YouTube'dan qidirishda muammo: {exc}"

        if start_seconds and start_seconds > 0:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}t={int(start_seconds)}s"

        webbrowser.open(url)
        pos = f" ({start_seconds}-sekunddan)" if start_seconds else ""
        return f"Ijro etilmoqda{pos}: {title} ({url})"


class StopMusicTool(Tool):
    name = "stop_music"
    description = (
        "Ijro etilayotgan musiqa yoki videoni to'xtatadi (pauza qiladi). "
        "Foydalanuvchi 'musiqani to'xtat', 'pauza', 'to'xtat' desa shu ishlatiladi. "
        "Media play/pause tugmasini bosadi — brauzerdagi YouTube ham to'xtaydi."
    )
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self) -> str:
        import pyautogui

        pyautogui.press("playpause")
        return "Musiqa to'xtatildi (pauza). Yana bosilsa qayta boshlanadi."


class MediaControlTool(Tool):
    name = "media_control"
    description = (
        "Media (musiqa/video) boshqaruvi: pauza/davom, keyingi/oldingi trek, "
        "ovoz balandligini o'zgartirish yoki ovozni o'chirish."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play_pause", "next", "previous", "volume_up", "volume_down", "mute"],
                "description": "Bajariladigan amal",
            },
        },
        "required": ["action"],
    }

    _KEY_MAP = {
        "play_pause": "playpause",
        "next": "nexttrack",
        "previous": "prevtrack",
        "volume_up": "volumeup",
        "volume_down": "volumedown",
        "mute": "volumemute",
    }

    def run(self, action: str) -> str:
        import pyautogui

        key = self._KEY_MAP.get(action)
        if key is None:
            return f"XATO: noma'lum amal: {action}"
        # Ovoz balandligini sezilarli o'zgartirish uchun bir necha marta bosamiz
        presses = 5 if action in ("volume_up", "volume_down") else 1
        for _ in range(presses):
            pyautogui.press(key)
        return f"Bajarildi: {action}"


class OpenUrlTool(Tool):
    name = "open_url"
    description = "Berilgan URL manzilni standart brauzerda ochadi."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Ochiladigan to'liq URL manzil"},
        },
        "required": ["url"],
    }

    def run(self, url: str) -> str:
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
        webbrowser.open(url)
        return f"Ochildi: {url}"


registry.register(PlayYoutubeTool())
registry.register(StopMusicTool())
registry.register(MediaControlTool())
registry.register(OpenUrlTool())
