"""ASOSIBOT — terminal rejimi (Telegramsiz sinash/ishlatish uchun).

Ishga tushirish:  python asosibot_cli.py
Reminder scheduler ham ishlaydi — vaqti kelgan eslatma terminalga chiqadi.
"""
import sys

from dotenv import load_dotenv

load_dotenv()

from asosibot.assistant import handle  # noqa: E402
from asosibot.scheduler import ReminderScheduler  # noqa: E402


def main() -> None:
    # Windows terminalida emoji chiqishi uchun
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    sched = ReminderScheduler(on_due=lambda owner, msg: print(f"\n⏰ ESLATMA: {msg}\n> ", end=""))
    sched.start()

    print("🤖 ASOSIBOT — shaxsiy yordamchi. Chiqish uchun 'exit'.\n"
          "Masalan: TODO qo'shish - Backend API yozish | 10 daqiqadan keyin eslat - suv ich | mening tasklarim\n")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("exit", "quit", "chiqish"):
            break
        if not text:
            continue
        result = handle(text, owner="cli")
        print(f"{result.get('emoji', '')} {result.get('voice_response', '')}\n")

    sched.stop()


if __name__ == "__main__":
    main()
