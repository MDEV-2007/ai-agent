"""Agentlar bir-biriga vazifa topshirishi uchun tool."""
import threading
from typing import Callable, Optional

from tools.base import Tool, registry

_delegate_handler: Optional[Callable[[str, str, str], str]] = None
_context = threading.local()


def set_delegate_handler(handler: Callable[[str, str, str], str]) -> None:
    global _delegate_handler
    _delegate_handler = handler


def set_delegation_source(agent_id: str) -> None:
    _context.agent_id = agent_id


class DelegateTaskTool(Tool):
    name = "delegate_task"
    description = "Boshqa mutaxassis agentga aniq, mustaqil sub-vazifa yuboradi."
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "enum": ["aziz", "malika", "bek", "nilufar", "timur"]},
            "task": {"type": "string", "description": "Batafsil sub-vazifa"},
        },
        "required": ["agent_id", "task"],
    }

    def run(self, agent_id: str, task: str) -> str:
        if _delegate_handler is None:
            return "XATO: delegatsiya faqat AgentLab server rejimida ishlaydi."
        source = getattr(_context, "agent_id", "noma'lum")
        if agent_id == source:
            return "XATO: agent o'ziga delegatsiya qila olmaydi."
        return _delegate_handler(agent_id, task, source)


registry.register(DelegateTaskTool())
