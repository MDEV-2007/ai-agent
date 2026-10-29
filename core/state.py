"""
Agentning joriy holatini saqlaydi (idle/thinking/running/done/error + joriy
vazifa/tool). FAZA 3'da bu holat WebSocket orqali piksel-ofis frontendiga
uzatiladi, shuning uchun observer (subscribe/notify) mexanizmi bilan yozilgan
— frontend ulanganda shunchaki subscribe qilib, holat o'zgarganda xabar oladi.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentState:
    agent_id: str = "agent-1"
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    current_tool: Optional[str] = None
    step: int = 0
    last_message: str = ""
    plan: List[dict] = field(default_factory=list)
    _subscribers: List[Callable[["AgentState"], None]] = field(default_factory=list, repr=False)

    def subscribe(self, callback: Callable[["AgentState"], None]) -> None:
        """Holat o'zgarganda chaqiriladigan funksiyani qo'shadi."""
        self._subscribers.append(callback)

    def _notify(self) -> None:
        for callback in self._subscribers:
            callback(self)

    def update(
        self,
        status: Optional[AgentStatus] = None,
        current_task: Optional[str] = None,
        current_tool: Optional[str] = None,
        step: Optional[int] = None,
        last_message: Optional[str] = None,
        plan: Optional[List[dict]] = None,
    ) -> None:
        """Holatni yangilaydi va barcha obunachilarga (subscriber) xabar beradi."""
        if status is not None:
            self.status = status
        if current_task is not None:
            self.current_task = current_task
        if current_tool is not None:
            self.current_tool = current_tool
        if step is not None:
            self.step = step
        if last_message is not None:
            self.last_message = last_message
        if plan is not None:
            self.plan = plan
        self._notify()

    def to_dict(self) -> dict:
        """WebSocket orqali yuborish uchun oddiy lug'atga aylantiradi."""
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "current_task": self.current_task,
            "current_tool": self.current_tool,
            "step": self.step,
            "last_message": self.last_message,
            "plan": self.plan,
        }
