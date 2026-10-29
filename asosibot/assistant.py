"""ASOSIBOT orchestrator — miya (brain) tasnifini oladi va uni xotiraga (store)
bajaradi, vaqtlarni hisoblaydi, yakuniy o'zbekcha javob qaytaradi.

Ro'yxat (list/search) so'rovlarida javobni model emas, haqiqiy DB ma'lumoti
asosida quramiz — chunki modelda DB tarkibi yo'q.
"""
from datetime import datetime, timedelta

from . import store
from .brain import classify


def _resolve_time(delay_minutes, dt_str):
    """delay_minutes yoki 'YYYY-MM-DD HH:MM' dan aniq vaqt (datetime) qaytaradi."""
    if delay_minutes:
        try:
            return datetime.now() + timedelta(minutes=int(delay_minutes))
        except (ValueError, TypeError):
            pass
    if dt_str:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(dt_str.strip(), fmt)
            except ValueError:
                continue
    return None


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _friendly_when(dt: datetime) -> str:
    """Bugun/ertaga + soat ko'rinishida o'zbekcha vaqt."""
    today = datetime.now().date()
    day = "bugun" if dt.date() == today else ("ertaga" if dt.date() == today + timedelta(days=1) else dt.strftime("%d-%m-%Y"))
    return f"{day} soat {dt.strftime('%H:%M')}"


def handle(user_text: str, owner: str = "local") -> dict:
    """Bitta buyruqni to'liq bajaradi. Qaytaradi:
    {"voice_response","emoji","action", "clarification_needed"}"""
    r = classify(user_text)
    action = r.get("action", "error")
    emoji = r.get("emoji", "")
    voice = r.get("voice_response", "")

    # O'zbekchada "eslatma" ham note, ham reminder — model ba'zan chalkashtiradi.
    # Qidiruvni har doim note'ga yo'naltiramiz (qidiriladigan asosiy store — notes).
    if action.startswith("search"):
        action = "search_notes"
    elif action.startswith("list") and action not in (
            "list_tasks", "list_reminders", "list_notes", "list_events"):
        action = "list_notes"

    # Aniqlik kerak bo'lsa — hech nima bajarmasdan savolni qaytaramiz
    if r.get("clarification_needed"):
        return {"voice_response": r.get("clarification_question") or voice or "Aniqroq ayting?",
                "emoji": "🤔", "action": action, "clarification_needed": True}

    try:
        # ------------------------------------------------------------- TASKS
        if action == "add_task":
            t = r.get("task") or {}
            due_dt = _resolve_time(None, f"{t.get('due_date','')} {t.get('due_time','')}".strip()) \
                if t.get("due_date") else None
            store.add_task(owner, t.get("title", user_text), t.get("description", ""),
                           t.get("category", "personal"), t.get("priority", "medium"),
                           _fmt_dt(due_dt) if due_dt else None, t.get("tags") or [])
            return _ok(voice or f"Task qo'shildi: {t.get('title')}", "✅", action)

        if action == "list_tasks":
            rows = store.list_tasks(owner, status="pending")
            if not rows:
                return _ok("Hozircha bajarilmagan tasklar yo'q.", "📋", action)
            lines = [f"{i+1}) {row['title']}" + (f" — {row['priority']}" if row['priority'] != 'medium' else "")
                     for i, row in enumerate(rows[:10])]
            return _ok("📋 Tasklaringiz:\n" + "\n".join(lines), "📋", action)

        if action == "mark_done":
            title = store.mark_task_done(owner, r.get("target") or user_text)
            if title:
                return _ok(f"Ajoyib! Bajarildi deb belgiladim: {title}.", "✅", action)
            return _ok("Bunday nomli task topilmadi.", "❌", action)

        if action == "delete_task":
            title = store.delete_task(owner, r.get("target") or user_text)
            return _ok(f"O'chirildi: {title}." if title else "Bunday task topilmadi.",
                       "✅" if title else "❌", action)

        # --------------------------------------------------------- REMINDERS
        if action == "add_reminder":
            rem = r.get("reminder") or {}
            when = _resolve_time(rem.get("delay_minutes"), rem.get("datetime"))
            if not when:
                return _ok("Vaqtni tushunolmadim. Necha daqiqadan keyin yoki qaysi soatda eslatay?", "🤔", action)
            store.add_reminder(owner, rem.get("message", user_text), _fmt_dt(when), rem.get("repeat", "once"))
            return _ok(f"⏰ {_friendly_when(when)}da eslatib beraman: {rem.get('message')}.", "⏰", action)

        if action == "list_reminders":
            rows = store.list_reminders(owner)
            if not rows:
                return _ok("Faol eslatmalar yo'q.", "⏰", action)
            lines = [f"{i+1}) {row['message']} — {row['scheduled_time']}" for i, row in enumerate(rows[:10])]
            return _ok("⏰ Eslatmalaringiz:\n" + "\n".join(lines), "⏰", action)

        if action == "cancel_reminder":
            msg = store.cancel_reminder(owner, r.get("target") or user_text)
            return _ok(f"Bekor qilindi: {msg}." if msg else "Bunday eslatma topilmadi.",
                       "✅" if msg else "❌", action)

        # ------------------------------------------------------------- NOTES
        if action == "write_note":
            n = r.get("note") or {}
            store.write_note(owner, n.get("content", user_text), n.get("title", ""), n.get("tags") or [])
            return _ok(voice or "📝 Eslatma saqlandi.", "💾", action)

        if action == "search_notes":
            q = (r.get("search") or {}).get("query", user_text)
            rows = store.search_notes(owner, q)
            if not rows:
                return _ok(f"'{q}' bo'yicha eslatma topilmadi.", "🔍", action)
            lines = [f"{i+1}) {row['content'][:60]}" for i, row in enumerate(rows[:8])]
            return _ok("🔍 Topildi:\n" + "\n".join(lines), "🔍", action)

        if action == "list_notes":
            rows = store.list_notes(owner)
            if not rows:
                return _ok("Hali eslatmalar yo'q.", "📝", action)
            lines = [f"{i+1}) {row['content'][:60]}" for i, row in enumerate(rows[:10])]
            return _ok("📝 Eslatmalaringiz:\n" + "\n".join(lines), "📝", action)

        if action == "delete_note":
            title = store.delete_note(owner, r.get("target") or user_text)
            return _ok(f"O'chirildi: {title}." if title else "Bunday eslatma topilmadi.",
                       "✅" if title else "❌", action)

        # ------------------------------------------------------------ EVENTS
        if action == "add_event":
            ev = r.get("event") or {}
            when = _resolve_time(ev.get("delay_minutes"), ev.get("datetime"))
            if not when:
                return _ok("Event vaqtini tushunolmadim. Qachon bo'ladi?", "🤔", action)
            store.add_event(owner, ev.get("title", user_text), _fmt_dt(when))
            return _ok(f"📅 Event qo'shildi: {ev.get('title')} — {_friendly_when(when)}.", "📅", action)

        if action == "list_events":
            rows = store.list_events(owner)
            if not rows:
                return _ok("Rejalashtirilgan eventlar yo'q.", "📅", action)
            lines = [f"{i+1}) {row['title']} — {row['start_time']}" for i, row in enumerate(rows[:10])]
            return _ok("📅 Eventlaringiz:\n" + "\n".join(lines), "📅", action)

        if action == "delete_event":
            title = store.delete_event(owner, r.get("target") or user_text)
            return _ok(f"O'chirildi: {title}." if title else "Bunday event topilmadi.",
                       "✅" if title else "❌", action)

        # ------------------------------------------------- LOKAL UTILITALAR
        if action == "time":
            return _ok(f"🕐 Hozir soat {datetime.now().strftime('%H:%M')}.", "🕐", action)
        if action == "date":
            return _ok(f"📅 Bugun {datetime.now().strftime('%d-%m-%Y, %A')}.", "📅", action)

        # small_talk, define, explain va boshqalar — model javobini shundoq beramiz
        return _ok(voice or "Tinglayapman.", emoji or "💬", action)

    except Exception as exc:  # DB yoki kutilmagan xato yordamchini o'ldirmasin
        return _ok(f"Kechirasiz, xatolik yuz berdi: {exc}", "❌", "error")


def _ok(voice, emoji, action):
    return {"voice_response": voice, "emoji": emoji, "action": action, "clarification_needed": False}
