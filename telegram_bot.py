"""
Telegram bot — kompyuterni Telegram orqali boshqarish uchun. Botga vazifa
yozasiz, u shu yerdagi agent (core/agent.py) orqali kompyuterda bajaradi va
natijani sizga qaytaradi. Xavfli amallar (fayl ustidan yozish, SMS, rm...)
Telegramning o'zida "✅ Ha / 🚫 Yo'q" tugmalari bilan tasdiq so'raydi.

XAVFSIZLIK: faqat ruxsat berilgan chat ID(lar) buyruq bera oladi. Birinchi
marta yozgan odam avtomatik "ega" bo'lib ro'yxatdan o'tadi (telegram_owner.txt
fayliga saqlanadi). Shuning uchun botni boshqalarga ko'rsatishdan OLDIN o'zingiz
yozib, egalikni "band qilib" qo'ying. Qo'shimcha ID'larni .env dagi
TELEGRAM_ALLOWED_IDS ga vergul bilan qo'shish mumkin.

Ishga tushirish (alohida terminalda):  python telegram_bot.py
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

from core.agent import Agent  # noqa: E402
from core.state import AgentState, AgentStatus  # noqa: E402
from safety.approval import set_approval_handler  # noqa: E402
from tools import registry  # noqa: E402

# ASOSIBOT — shaxsiy o'zbek yordamchisi (task/reminder/note/event). Kompyuter
# boshqaruv agentidan alohida rejimda ishlaydi (/asosibot bilan yoqiladi).
from asosibot.assistant import handle as asosibot_handle  # noqa: E402
from asosibot.scheduler import ReminderScheduler  # noqa: E402
from asosibot import voice as asosibot_voice  # noqa: E402

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"
AGENT_SERVER_URL = os.getenv("AGENT_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
TELEGRAM_AGENT_ID = os.getenv("TELEGRAM_AGENT_ID", "aziz")
OWNER_FILE = Path(__file__).resolve().parent / "telegram_owner.txt"
APPROVAL_TIMEOUT_SEC = 180
TELEGRAM_MSG_LIMIT = 3900  # Telegram 4096 chegarasidan biroz pastroq

# .env dagi qo'lda ruxsat berilgan ID'lar + fayldagi "ega"
_allowed = {x.strip() for x in os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",") if x.strip()}
if OWNER_FILE.exists():
    _allowed.update(x.strip() for x in OWNER_FILE.read_text(encoding="utf-8").split() if x.strip())

# Username bo'yicha ruxsat (raqamli ID shart emas). @ belgisisiz, kichik harfda saqlanadi.
_allowed_usernames = {
    x.strip().lstrip("@").lower()
    for x in os.getenv("TELEGRAM_ALLOWED_USERNAMES", "").split(",")
    if x.strip()
}

# Har chat qaysi rejimda: "agent" (kompyuter boshqaruvi, default) yoki "asosibot"
# (shaxsiy yordamchi). /asosibot va /agent bilan almashtiriladi.
_mode: dict[str, str] = {}
_scheduler: ReminderScheduler | None = None

# Har bir chat uchun alohida agent (suhbat konteksti saqlanadi)
_agents: dict[str, Agent] = {}
# Kutilayotgan tasdiq so'rovlari: approval_id -> {event, decision}
_pending: dict[str, dict] = {}
# Joriy thread qaysi chatga tegishli ekanini bilish uchun (approval marshrutlash)
_current = threading.local()


# --------------------------------------------------------------- Telegram API
def send_message(chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    if len(text) > TELEGRAM_MSG_LIMIT:
        text = text[:TELEGRAM_MSG_LIMIT] + "\n…(qisqartirildi)"
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{API}/sendMessage", json=data, timeout=20)
    except requests.RequestException as exc:
        print(f"[telegram] sendMessage xato: {exc}")


def answer_callback(callback_id: str, text: str = "") -> None:
    try:
        requests.post(f"{API}/answerCallbackQuery",
                      json={"callback_query_id": callback_id, "text": text}, timeout=20)
    except requests.RequestException:
        pass


# --------------------------------------------------------------- Tasdiqlash
def _telegram_approval(reason: str) -> bool:
    """Destruktiv amal oldidan Telegram orqali Ha/Yo'q so'raydi va javob
    kelguncha (yoki timeout) agent thread'ini bloklaydi."""
    chat_id = getattr(_current, "chat_id", None)
    if chat_id is None:
        return False
    approval_id = uuid.uuid4().hex[:10]
    event = threading.Event()
    _pending[approval_id] = {"event": event, "decision": False}
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Ha, ruxsat", "callback_data": f"ok:{approval_id}"},
        {"text": "🚫 Yo'q, rad et", "callback_data": f"no:{approval_id}"},
    ]]}
    send_message(chat_id, f"⚠️ Tasdiq talab qilinadi:\n\n{reason}\n\nRuxsat berasizmi?", keyboard)
    approved = event.wait(timeout=APPROVAL_TIMEOUT_SEC)
    slot = _pending.pop(approval_id, None)
    decision = bool(slot and slot["decision"]) if approved else False
    if not approved:
        send_message(chat_id, "⏱ Tasdiq kutish vaqti tugadi — amal rad etildi.")
    return decision


# --------------------------------------------------------------- Vazifa bajarish
def _get_agent(chat_id: str) -> Agent:
    """Chat uchun agent qaytaradi. Birinchi marta yaratilganda unga bitta
    state-subscriber ulaymiz — u har tool ishga tushganda Telegramga xabar
    yuboradi (subscriber faqat bir marta qo'shiladi, takrorlanmaydi)."""
    if chat_id not in _agents:
        agent = Agent(tools=registry, state=AgentState(agent_id=f"tg-{chat_id}"))
        last_tool = {"name": None}

        def on_state(state: AgentState) -> None:
            if state.status == AgentStatus.RUNNING and state.current_tool \
                    and state.current_tool != last_tool["name"]:
                last_tool["name"] = state.current_tool
                send_message(chat_id, f"🔧 {state.current_tool}")
            elif state.status == AgentStatus.THINKING:
                last_tool["name"] = None  # yangi qadam — keyingi tool'ni qayta xabar qilamiz

        agent.state.subscribe(on_state)
        _agents[chat_id] = agent
    return _agents[chat_id]


def _run_task(chat_id: str, text: str) -> None:
    """Vazifani saytdagi yagona agent/navbat tizimiga yuboradi."""
    task_id = uuid.uuid4().hex
    try:
        response = requests.post(
            f"{AGENT_SERVER_URL}/chat",
            json={"task": text, "agent_id": TELEGRAM_AGENT_ID, "task_id": task_id,
                  "source": "telegram", "chat_id": chat_id},  # chat_id — tasdiq shu chatga qaytadi
            timeout=15,
        )
        response.raise_for_status()
        accepted = response.json()
    except requests.RequestException as exc:
        send_message(chat_id, f"Server agentiga ulanib bo'lmadi: {exc}")
        return

    position = accepted.get("position", 0)
    if position:
        send_message(chat_id, f"Vazifa sayt agenti navbatiga qo'shildi ({position}-o'rin).")
    else:
        send_message(chat_id, "Vazifa sayt agentida bajarilmoqda. Ofis oynasida ham ko'rinadi.")

    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            status = requests.get(f"{AGENT_SERVER_URL}/tasks/{task_id}", timeout=10).json()
        except requests.RequestException:
            time.sleep(2)
            continue
        if status.get("status") == "done":
            entry = status["entry"]
            icon = "OK" if entry.get("status") == "done" else "XATO"
            send_message(chat_id, f"{icon}: {entry.get('result', '')}")
            return
        time.sleep(2)
    send_message(chat_id, "Vazifa hali davom etyapti; natija saytdagi tarixda ko'rinadi.")
    return
    """Vazifani alohida thread'da bajaradi (polling to'xtamasligi uchun)."""
    _current.chat_id = chat_id
    agent = _get_agent(chat_id)
    send_message(chat_id, "🤖 Vazifani bajaryapman...")
    result = agent.run(text)
    icon = "⚠️" if agent.state.status == AgentStatus.ERROR else "✅"
    send_message(chat_id, f"{icon} {result}")


def _run_asosibot(chat_id: str, text: str) -> None:
    """Xabarni ASOSIBOT yordamchisiga yuboradi (task/reminder/note/event).
    owner sifatida chat_id ishlatiladi — har foydalanuvchining ma'lumoti alohida."""
    try:
        result = asosibot_handle(text, owner=chat_id)
        send_message(chat_id, f"{result.get('emoji','')} {result.get('voice_response','')}".strip())
    except Exception as exc:
        send_message(chat_id, f"❌ Yordamchida xatolik: {exc}")


def _download_voice(file_id: str) -> bytes | None:
    """Telegram ovozli xabar faylini yuklab oladi (STT uchun)."""
    try:
        info = requests.get(f"{API}/getFile", params={"file_id": file_id}, timeout=20).json()
        if not info.get("ok"):
            return None
        path = info["result"]["file_path"]
        audio = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=60)
        return audio.content if audio.ok else None
    except requests.RequestException:
        return None


# --------------------------------------------------------------- Update'larni qayta ishlash
def _authorize(chat_id: str, username: str | None = None) -> bool:
    """Ruxsatni tekshiradi: chat_id yoki username ro'yxatda bo'lsa True.
    Hech kim ega bo'lmagan bo'lsa, birinchi yozgan odamni ega qilib oladi."""
    if chat_id in _allowed:
        return True
    if username and username.lower() in _allowed_usernames:
        _allowed.add(chat_id)  # keyingi safar tezroq bo'lishi uchun ID'ni ham eslab qolamiz
        return True
    if not _allowed and not _allowed_usernames:  # hali hech kim yo'q — birinchi kelgan ega bo'ladi
        _allowed.add(chat_id)
        try:
            with OWNER_FILE.open("a", encoding="utf-8") as f:
                f.write(chat_id + "\n")
        except OSError as exc:
            print(f"[telegram] egalikni saqlab bo'lmadi: {exc}")
        send_message(chat_id, "✅ Siz ega sifatida ro'yxatdan o'tdingiz. Endi menga vazifa yozing.")
        return True
    return False


def _handle_update(update: dict) -> None:
    # Tugma bosilishi (tasdiq javobi)
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data", "")

        # Ofis serveridan kelgan tasdiq (srvapprove:approval_id:ok|no) — javobni serverga uzatamiz
        if data.startswith("srvapprove:"):
            parts = data.split(":")
            if len(parts) == 3:
                aid, decision = parts[1], parts[2]
                try:
                    requests.post(f"{AGENT_SERVER_URL}/approve",
                                  json={"approval_id": aid, "decision": decision == "ok"}, timeout=10)
                except requests.RequestException:
                    pass
                answer_callback(cq["id"], "Qabul qilindi ✅" if decision == "ok" else "Rad etildi 🚫")
            return

        try:
            action, aid = data.split(":", 1)
        except ValueError:
            return
        slot = _pending.get(aid)
        if slot:
            slot["decision"] = action == "ok"
            slot["event"].set()
            answer_callback(cq["id"], "Qabul qilindi ✅" if action == "ok" else "Rad etildi 🚫")
        else:
            answer_callback(cq["id"], "Bu so'rov allaqachon yopilgan")
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = str(message["chat"]["id"])
    username = (message.get("from") or {}).get("username")

    if not _authorize(chat_id, username):
        uname = f"@{username}" if username else "(username yo'q)"
        send_message(chat_id, f"⛔ Sizda ruxsat yo'q.\nSizning ID: {chat_id}\nUsername: {uname}\n"
                              f".env ichida TELEGRAM_ALLOWED_IDS yoki TELEGRAM_ALLOWED_USERNAMES ga qo'shing.")
        return

    # Ovozli xabar: matnga o'giramiz (HuggingFace STT). Token bo'lmasa — matn so'raymiz.
    if "voice" in message or "audio" in message:
        media = message.get("voice") or message.get("audio")
        if not asosibot_voice.stt_available():
            send_message(chat_id, "🎤 Ovozni matnga o'girish uchun HUGGINGFACE_TOKEN kerak. "
                                  "Hozircha iltimos matn yozing.")
            return
        send_message(chat_id, "🎤 Tinglayapman...")
        audio = _download_voice(media["file_id"])
        text = asosibot_voice.transcribe(audio) if audio else None
        if not text:
            send_message(chat_id, "❌ Ovozni tushunolmadim. Iltimos, qayta ayting yoki matn yozing.")
            return
        send_message(chat_id, f"🎤 «{text}»")
        # Ovozli xabar har doim ASOSIBOT yordamchisiga ketadi
        threading.Thread(target=_run_asosibot, args=(chat_id, text), daemon=True).start()
        return

    if "text" not in message:
        return
    text = message["text"].strip()

    if text.startswith("/start"):
        mode = _mode.get(chat_id, "agent")
        send_message(chat_id, "👋 Salom! Menda ikki rejim bor:\n\n"
                              "🖥 /agent — kompyuter boshqaruvi (dastur ochish, kod, fayl, musiqa...)\n"
                              "🤖 /asosibot — shaxsiy yordamchi (task, eslatma, note, event)\n\n"
                              f"Hozirgi rejim: {'🤖 ASOSIBOT' if mode == 'asosibot' else '🖥 Agent'}\n"
                              "Rejimni almashtirish uchun yuqoridagi komandani yuboring.")
        return
    if text.startswith("/asosibot"):
        _mode[chat_id] = "asosibot"
        send_message(chat_id, "🤖 ASOSIBOT rejimi yoqildi. Endi men shaxsiy yordamchingizman.\n"
                              "Masalan:\n• TODO qo'shish - Backend API yozish\n"
                              "• 30 daqiqadan keyin eslat - suv ich\n• eslatma yoz - Groq kalitini yangilash\n"
                              "• mening tasklarim\n\nKompyuter boshqaruviga qaytish: /agent")
        return
    if text.startswith("/agent"):
        _mode[chat_id] = "agent"
        send_message(chat_id, "🖥 Agent rejimi yoqildi. Endi kompyuterni boshqaraman "
                              "(dastur ochish, kod, fayl, musiqa...).\n\nYordamchiga o'tish: /asosibot")
        return
    if text.startswith("/help"):
        send_message(chat_id, "Menga oddiy tilda vazifa yozing. Xavfli amallar (fayl "
                              "o'chirish/ustidan yozish, SMS...) uchun Ha/Yo'q tugmalari chiqadi.\n\n"
                              "/model — LLM modelni ko'rish yoki almashtirish\n"
                              "Masalan: /model qwen3-coder:30b (aqlliroq, sekinroq) yoki "
                              "/model qwen3:8b (tezroq)")
        return
    if text.startswith("/model"):
        parts = text.split(maxsplit=1)
        current = os.getenv("OLLAMA_MODEL", "qwen3:8b")
        if len(parts) < 2:
            send_message(chat_id, f"Joriy model: {current}\n\nO'zgartirish uchun:\n"
                                  f"/model qwen3-coder:30b — aqlliroq (loyiha qurish uchun), sekinroq\n"
                                  f"/model qwen3:8b — tezroq, oddiy vazifalar uchun")
        else:
            new_model = parts[1].strip()
            os.environ["OLLAMA_MODEL"] = new_model
            # Shu chatning agentini yangi model bilan qayta yaratilishga majburlaymiz
            if chat_id in _agents:
                _agents[chat_id]._llm = None
            send_message(chat_id, f"✅ Model o'zgartirildi: {new_model}\n"
                                  f"(Birinchi so'rov modelni yuklagani uchun biroz sekinroq bo'ladi.)")
        return

    # Rejimga qarab yo'naltiramiz: ASOSIBOT yordamchisi yoki kompyuter agenti.
    # Har ikkisi fon thread'ida — polling to'xtamaydi, tasdiq tugmalari ishlaydi.
    if _mode.get(chat_id) == "asosibot":
        threading.Thread(target=_run_asosibot, args=(chat_id, text), daemon=True).start()
    else:
        threading.Thread(target=_run_task, args=(chat_id, text), daemon=True).start()


# --------------------------------------------------------------- Asosiy sikl
def main() -> None:
    if not TOKEN:
        raise SystemExit("XATO: .env faylida TELEGRAM_BOT_TOKEN yo'q.")

    me = requests.get(f"{API}/getMe", timeout=20).json()
    if not me.get("ok"):
        raise SystemExit(f"XATO: token ishlamadi: {me}")
    print(f"[telegram] Bot ishga tushdi: @{me['result']['username']}")
    if _allowed:
        print(f"[telegram] Ruxsatli ID'lar: {_allowed}")
    else:
        print("[telegram] Hali ega yo'q — birinchi yozgan odam ega bo'ladi.")

    # ASOSIBOT reminder scheduler: vaqti kelgan eslatmani egasiga (chat_id) yuboradi.
    global _scheduler
    _scheduler = ReminderScheduler(
        on_due=lambda owner, msg: send_message(owner, f"⏰ Eslatma: {msg}")
    )
    _scheduler.start()
    print("[asosibot] Reminder scheduler ishga tushdi.")

    offset = None
    while True:
        try:
            resp = requests.get(f"{API}/getUpdates",
                                params={"timeout": 30, "offset": offset}, timeout=40)
            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                _handle_update(update)
        except requests.RequestException as exc:
            print(f"[telegram] polling xato: {exc}")
        except Exception as exc:  # bitta update xatosi butun botni to'xtatmasin
            print(f"[telegram] update xato: {exc}")


if __name__ == "__main__":
    main()
