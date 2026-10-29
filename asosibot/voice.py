"""Ovoz (STT/TTS) — ixtiyoriy HuggingFace Inference API integratsiyasi.

STT (nutqni matnga): Telegram ovozli xabarini Whisper orqali o'zbekcha matnga
o'giradi. TTS (matnni nutqqa): javobni audio qiladi.

MUHIM: bu funksiyalar HUGGINGFACE_TOKEN muhit o'zgaruvchisini talab qiladi.
Token bo'lmasa — None qaytaradi va chaqiruvchi matn bilan davom etadi (ovoz
funksiyasi shunchaki o'chirilgan bo'ladi, hech narsa buzilmaydi). HF Inference
API modellari vaqti-vaqti bilan o'zgaradi/sekin javob beradi, shuning uchun
xatolar yumshoq (None) qaytariladi.
"""
import logging
import os

logger = logging.getLogger("asosibot.voice")

GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "").strip()
# HuggingFace eski api-inference.huggingface.co manzilini o'chirdi — yangi
# "Inference Providers" routeri ishlatiladi. whisper-large-v3 hf-inference
# provideri orqali qo'llab-quvvatlanadi (whisper-small/base bu yerda yo'q).
STT_MODEL = os.getenv("HF_STT_MODEL", "openai/whisper-large-v3")
TTS_MODEL = os.getenv("HF_TTS_MODEL", "facebook/mms-tts-uzn")  # o'zbekcha TTS
ROUTER = "https://router.huggingface.co/hf-inference/models"
STT_LANG = os.getenv("ASOSIBOT_STT_LANG", "uz")  # tilni MAJBURLAYMIZ — noto'g'ri taxminning oldini oladi


def stt_available() -> bool:
    return bool(GROQ_KEY or HF_TOKEN)


def _groq_transcribe(audio_bytes: bytes) -> str | None:
    """Groq Whisper — TEZ va language=uz bilan. Asosiy STT yo'li."""
    if not GROQ_KEY:
        return None
    import requests

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
            data={"model": GROQ_STT_MODEL, "language": STT_LANG, "response_format": "json"},
            timeout=60,
        )
        if resp.status_code != 200:
            logger.warning("Groq STT xato: %s %s", resp.status_code, resp.text[:150])
            return None
        return (resp.json().get("text") or "").strip() or None
    except Exception:
        logger.warning("Groq STT so'rovi muvaffaqiyatsiz", exc_info=True)
        return None


def _hf_transcribe(audio_bytes: bytes) -> str | None:
    """HuggingFace zaxira STT (Groq ishlamasa). Bepul tarif — sekin/beqaror."""
    if not HF_TOKEN:
        return None
    import requests

    try:
        resp = requests.post(
            f"{ROUTER}/{STT_MODEL}",
            headers={"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "audio/ogg",
                     "x-wait-for-model": "true"},
            data=audio_bytes,
            timeout=120,
        )
        if resp.status_code != 200:
            logger.warning("HF STT xato: %s %s", resp.status_code, resp.text[:150])
            return None
        data = resp.json()
        text = data.get("text") if isinstance(data, dict) else None
        return (text or "").strip() or None
    except Exception:
        logger.warning("HF STT so'rovi muvaffaqiyatsiz", exc_info=True)
        return None


def transcribe(audio_bytes: bytes) -> str | None:
    """Ovozli xabarni matnga o'giradi. Avval Groq (tez, language=uz), u ishlamasa
    HuggingFace zaxira. Ikkalasi ham bo'lmasa None."""
    return _groq_transcribe(audio_bytes) or _hf_transcribe(audio_bytes)


def synthesize(text: str) -> bytes | None:
    """Matnni audio (baytlar) qiladi. Token/xato bo'lsa None."""
    if not HF_TOKEN:
        return None
    import requests

    try:
        resp = requests.post(
            f"{ROUTER}/{TTS_MODEL}",
            headers={"Authorization": f"Bearer {HF_TOKEN}"},
            json={"inputs": text},
            timeout=60,
        )
        if resp.status_code != 200:
            logger.warning("TTS xato: %s %s", resp.status_code, resp.text[:150])
            return None
        return resp.content or None
    except Exception:
        logger.warning("TTS so'rovi muvaffaqiyatsiz", exc_info=True)
        return None
