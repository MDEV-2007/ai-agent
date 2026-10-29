"""
Terminal chat interfeysi — FAZA 1 uchun test maydoni. Piksel-ofis UI hali yo'q
(u FAZA 3'da qo'shiladi), shu fayl orqali agentni to'g'ridan-to'g'ri
terminaldan sinab ko'rish mumkin.
"""
from dotenv import load_dotenv

load_dotenv()

from core.agent import Agent  # noqa: E402  — dotenv yuklangandan keyin import qilinishi kerak
from core.state import AgentState, AgentStatus  # noqa: E402
from tools import registry  # noqa: E402

STATUS_LABELS = {
    AgentStatus.IDLE: "bo'sh",
    AgentStatus.THINKING: "o'ylayapti",
    AgentStatus.RUNNING: "ishlayapti",
    AgentStatus.DONE: "tugadi",
    AgentStatus.ERROR: "xatolik",
}


def _print_state(state: AgentState) -> None:
    label = STATUS_LABELS.get(state.status, state.status.value)
    if state.status == AgentStatus.RUNNING and state.current_tool:
        print(f"  [{label}] tool: {state.current_tool}")
    else:
        print(f"  [{label}] (qadam {state.step})")


def main() -> None:
    state = AgentState()
    state.subscribe(_print_state)
    agent = Agent(tools=registry, state=state)

    print("Shaxsiy AI agent — terminal rejimi. Chiqish uchun 'exit' yozing.\n")
    while True:
        task = input("\nVazifa: ").strip()
        if task.lower() in ("exit", "quit", "chiqish"):
            break
        if not task:
            continue
        answer = agent.run(task)
        print(f"\nAgent: {answer}")


if __name__ == "__main__":
    main()
