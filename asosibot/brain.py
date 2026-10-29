"""ASOSIBOT miyasi — foydalanuvchi matnini (o'zbekcha) tushunib, bajariladigan
struktura JSON'ga aylantiradi. Lokal Ollama (qwen3:8b) + format=json ishlatadi.

Chiqish sxemasi (faqat biz bajaradigan maydonlar):
{
  "action": "add_task|list_tasks|mark_done|delete_task|
             add_reminder|list_reminders|cancel_reminder|
             write_note|search_notes|list_notes|delete_note|
             add_event|list_events|delete_event|
             time|date|small_talk|define|error",
  "confidence": 0.0-1.0,
  "clarification_needed": bool,
  "clarification_question": "matn yoki null",
  "voice_response": "O'ZBEKCHA javob",
  "emoji": "✅|⏰|📋|📝|📄|🔍|❌|📅|👋",
  "target": "mark_done/delete/cancel uchun qidiriladigan nom yoki null",
  "task": {"title","description","category","priority","due_date","due_time","tags"} | null,
  "reminder": {"message","delay_minutes","datetime","repeat"} | null,
  "note": {"title","content","tags"} | null,
  "event": {"title","delay_minutes","datetime"} | null,
  "search": {"query","search_in"} | null
}
"""
import json
import os
import re
from datetime import datetime

SYSTEM_PROMPT = """Sen ASOSIBOT — shaxsiy o'zbek ovozli yordamchisan. Foydalanuvchining
tasklar, eslatmalar (reminder), notes, event/calendar bilan ishlashiga yordam berasan.

QAT'IY QOIDALAR:
1. FAQAT bitta JSON obyekt qaytar — boshqa hech qanday matn, izoh yoki markdown yo'q.
2. "voice_response" MAJBURIY o'zbek tilida, qisqa (1-2 jumla), samimiy ("siz" bilan).
3. Buyruq noaniq bo'lsa (masalan mazmun yoki vaqt yo'q) — clarification_needed=true qil
   va clarification_question'ni o'zbekcha yoz.
4. Vaqt: nisbiy bo'lsa ("30 daqiqa keyin", "3 soat keyin") delay_minutes ber (butun son).
   Aniq bo'lsa ("ertaga 9:00") datetime ber "YYYY-MM-DD HH:MM" ko'rinishida. Bittasini.
5. mark_done/delete_task/cancel_reminder/delete_note/delete_event uchun "target"ga
   qidiriladigan nomni yoz.

action qiymatlari: add_task, list_tasks, mark_done, delete_task, add_reminder,
list_reminders, cancel_reminder, write_note, search_notes, list_notes, delete_note,
add_event, list_events, delete_event, time, date, small_talk, define.

MUHIM AJRATISH (o'zbekcha noaniqlik):
- "eslat", "eslatib ber", "... daqiqadan/soatdan keyin", "ertaga soat ..." → add_reminder
  (bu VAQTGA bog'liq eslatma).
- "eslatma yoz", "eslatma saqla", "note" → write_note (bu matn/qayd).
- "qidir", "izla", "topib ber" so'zi bo'lsa → HAR DOIM search_notes (list emas!).
- "ro'yxat", "hammasini ko'rsat", "menikilar" → list_* (qidiruvsiz).

JSON sxemasi (keraksiz obyektlarni null qil):
{"action","confidence","clarification_needed","clarification_question","voice_response",
"emoji","target","task":{"title","description","category","priority","due_date","due_time","tags"},
"reminder":{"message","delay_minutes","datetime","repeat"},"note":{"title","content","tags"},
"event":{"title","delay_minutes","datetime"},"search":{"query","search_in"}}

Misollar:
User: "TODO qo'shish - Backend API yozish, bugun"
{"action":"add_task","confidence":0.97,"clarification_needed":false,"clarification_question":null,
"voice_response":"Task qo'shildi: Backend API yozish. Bugungi muddat bilan.","emoji":"✅","target":null,
"task":{"title":"Backend API yozish","description":"","category":"work","priority":"high","due_date":null,"due_time":null,"tags":["Backend","API"]},
"reminder":null,"note":null,"event":null,"search":null}

User: "30 daqiqadan keyin eslat - Code review"
{"action":"add_reminder","confidence":0.98,"clarification_needed":false,"clarification_question":null,
"voice_response":"30 daqiqadan keyin eslatib beraman: Code review.","emoji":"⏰","target":null,
"task":null,"reminder":{"message":"Code review","delay_minutes":30,"datetime":null,"repeat":"once"},"note":null,"event":null,"search":null}

User: "eslatma yoz - Groq kalitni yangilash kerak"
{"action":"write_note","confidence":0.96,"clarification_needed":false,"clarification_question":null,
"voice_response":"Eslatma saqlandi.","emoji":"📝","target":null,
"task":null,"reminder":null,"note":{"title":"","content":"Groq kalitni yangilash kerak","tags":["Groq"]},"event":null,"search":null}

User: "task tugadi - Database setup"
{"action":"mark_done","confidence":0.95,"clarification_needed":false,"clarification_question":null,
"voice_response":"Ajoyib! Bajarilgan deb belgiladim: Database setup.","emoji":"✅","target":"Database setup",
"task":null,"reminder":null,"note":null,"event":null,"search":null}

User: "reminder qo'shish"
{"action":"add_reminder","confidence":0.6,"clarification_needed":true,"clarification_question":"Nimani va necha daqiqadan keyin eslatay?",
"voice_response":"Nimani eslatay va necha daqiqadan keyin?","emoji":"🤔","target":null,
"task":null,"reminder":null,"note":null,"event":null,"search":null}

User: "salom, qalaysan"
{"action":"small_talk","confidence":0.99,"clarification_needed":false,"clarification_question":null,
"voice_response":"Salom! Yaxshiman, rahmat. Sizga qanday yordam beray?","emoji":"👋","target":null,
"task":null,"reminder":null,"note":null,"event":null,"search":null}"""


def _extract_json(text: str) -> dict:
    """Modeldan kelgan matndan JSON obyektni ajratib oladi (format=json bo'lsa
    toza keladi, lekin ehtiyot uchun markdown/atrof matnni ham tozalaymiz)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    # ```json ... ``` bo'lsa ichini olamiz
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    # birinchi { dan oxirgi } gacha
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def classify(user_text: str, model: str | None = None) -> dict:
    """Foydalanuvchi matnini struktura JSON'ga aylantiradi. Xato bo'lsa
    action='error' qaytaradi (chaqiruvchi buni tushunadi)."""
    import ollama

    model = model or os.getenv("ASOSIBOT_MODEL", os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    client = ollama.Client(host=host)

    now = datetime.now()
    context = f"Hozirgi sana va vaqt: {now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%A')})."
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n" + context},
        {"role": "user", "content": user_text},
    ]

    kwargs = {"model": model, "messages": messages, "format": "json",
              "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
              "options": {"temperature": 0.2}}
    try:
        try:
            resp = client.chat(think=False, **kwargs)
        except Exception as exc:
            if "think" not in str(exc).lower() and not isinstance(exc, TypeError):
                raise
            resp = client.chat(**kwargs)
        return _extract_json(resp.message.content or "{}")
    except Exception as exc:
        return {
            "action": "error",
            "voice_response": "Kechirasiz, sizni tushunolmadim. Iltimos, qayta ayting.",
            "emoji": "❌",
            "_error": str(exc),
        }
