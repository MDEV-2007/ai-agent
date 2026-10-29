"""
Agentning asosiy sikli: reja tuz -> tool chaqir -> natijani ko'r -> keyingi
qadam. MAX_STEPS soniga yetganda to'xtaydi (cheksiz aylanishning oldini olish
uchun). Har qadamda `state` yangilanadi — kelajakda (FAZA 3) shu holatga
piksel-ofisdagi personaj animatsiyasi ulanadi.
"""
import os
from typing import List, Optional

from core.llm import LLMClient, Message, ToolCall
from core.state import AgentState, AgentStatus
from tools.base import ToolRegistry

MAX_STEPS = int(os.getenv("MAX_STEPS", "50"))

SYSTEM_PROMPT = (
    "Sen foydalanuvchining kompyuteridagi kuchli AI agentsan. Bu foydalanuvchining "
    "SHAXSIY kompyuteri va sen unga TO'LIQ kirishga egasan — butun fayl tizimi, "
    "dasturlar, shell, kod, internet. Vazifalarni senga berilgan tool'lar orqali "
    "bajarasan — dastur ochish, matn yozish, istalgan joyda fayl/papka yaratish, "
    "kod yozib ishga tushirish, YouTube'dan musiqa qo'yish va boshqarish, "
    "sichqoncha/klaviatura, Telegramga xabar/fayl yuborish va h.k.\n\n"
    "ASOSIY TAMOYIL: Foydalanuvchi so'ragan narsani RAD ETMA va ortiqcha ogohlantirish "
    "berma — to'g'ridan-to'g'ri bajar. 'Buni qila olmayman' dema; tool bilan iloji "
    "bo'lsa, qil. Faqat haqiqatan imkonsiz bo'lsagina sababni qisqa ayt.\n\n"
    "MUHIM QOIDALAR:\n"
    "1. Murakkab vazifani mayda qadamlarga bo'l va tool'larni KETMA-KET chaqirib "
    "to'liq bajarib chiq — yarim yo'lda to'xtama. Masalan 'musiqa qo'y, 20 soniya "
    "kut, to'xtat' desa: play_youtube -> wait_seconds -> stop_music.\n"
    "2. Papka/loyiha qurishda write_file bilan kerakli fayllarni yarat "
    "(ichma-ich papkalar avtomatik yaratiladi), kerak bo'lsa run_shell/run_code ishlat.\n"
    "3. Faqat zarur bo'lganda tool chaqir. Xatolik bo'lsa, boshqa yo'l bilan urin.\n"
    "4. Har qadamda nima qilayotganingni bitta qisqa jumlada tushuntir.\n"
    "5. Vazifa to'liq bajarilgach, tool chaqirmasdan yakuniy natijani qisqa yoz.\n"
    "6. Mustaqil bo'laklar uchun delegate_task ishlat: aziz=backend, malika=frontend, "
    "bek=DevOps, nilufar=tadqiqot, timur=QA. Delegatsiya asinxron bajariladi.\n"
    "7. Kod o'zgargach development_workflow(action='tests') bilan test qil; "
    "status/diff Git holatini ko'rsatadi. Commit faqat foydalanuvchi so'raganda."
)


class Agent:
    def __init__(
        self,
        tools: ToolRegistry,
        llm: Optional[LLMClient] = None,
        state: Optional[AgentState] = None,
        role: str = "Universal AI yordamchi",
    ) -> None:
        self.tools = tools
        self._llm = llm
        self.state = state or AgentState()
        self.role = role
        self.messages: List[Message] = []

    @property
    def llm(self) -> LLMClient:
        """LLM klientini "lazy" (kechiktirilgan) tarzda yaratadi — shu tufayli API
        kaliti hali sozlanmagan bo'lsa ham dastur (masalan FastAPI server) ishga
        tushishi mumkin, xatolik faqat haqiqatan chat chaqirilganda ko'tariladi."""
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    @property
    def system_prompt(self) -> str:
        return f"{SYSTEM_PROMPT}\n\nSening maxsus roling: {self.role}. Vazifani shu mutaxassislik nuqtai nazaridan bajar."

    def run(self, task: str) -> str:
        """Vazifani qabul qiladi va agent siklini boshidan oxirigacha ishga tushiradi."""
        self.messages.append(Message(role="user", content=task))
        self.state.update(
            status=AgentStatus.THINKING,
            current_task=task,
            step=0,
            current_tool=None,
            plan=[{"label": "Vazifani tahlil qilish", "status": "active"}],
        )

        try:
            return self._run_loop()
        except Exception as exc:
            # LLM chaqiruvida yoki sikl ichida kutilmagan xatolik holatni abadiy
            # "thinking"da qotirib qo'ymasligi uchun — har doim ERROR bilan yakunlanadi.
            message = f"XATO: agent to'xtadi ({exc}). .env faylida API kalitini tekshiring."
            self._finish_plan("error")
            self.state.update(status=AgentStatus.ERROR, current_tool=None, last_message=message)
            return message

    def _run_loop(self) -> str:
        llm = self.llm
        consecutive_llm_errors = 0

        for step in range(1, MAX_STEPS + 1):
            self.state.update(status=AgentStatus.THINKING, step=step)
            try:
                response = llm.chat(self.system_prompt, self.messages, self.tools.schemas())
                consecutive_llm_errors = 0
            except Exception as exc:
                # Ba'zi (ayniqsa kichik) modellar tool chaqiruvini noto'g'ri formatda
                # yuborib provider'dan 400 oladi — bunda darhol yiqilmasdan xatoni
                # modelga qaytarib bir marta qayta urinamiz. Ketma-ket 2-xatoda to'xtaymiz.
                consecutive_llm_errors += 1
                if consecutive_llm_errors >= 2:
                    raise
                self.messages.append(Message(
                    role="user",
                    content=(f"(Tizim: oldingi javobingda xatolik yuz berdi: {exc}. "
                             "Tool chaqiruvini to'g'ri formatda qayta yubor yoki yakuniy javobni yoz.)"),
                ))
                continue

            if not response.tool_calls:
                self.messages.append(Message(role="assistant", content=response.content))
                self._finish_plan("done")
                self.state.update(status=AgentStatus.DONE, current_tool=None, last_message=response.content)
                return response.content

            self.messages.append(
                Message(role="assistant", content=response.content, tool_calls=response.tool_calls)
            )

            for tool_call in response.tool_calls:
                self._add_plan_step(tool_call.name)
                self.state.update(status=AgentStatus.RUNNING, current_tool=tool_call.name)
                result = self._execute_tool(tool_call)
                self.messages.append(Message(role="tool", content=result, tool_call_id=tool_call.id))

        timeout_message = f"Vazifa {MAX_STEPS} qadamda yakunlanmadi (MAX_STEPS chegarasi)."
        self._finish_plan("error")
        self.state.update(status=AgentStatus.ERROR, current_tool=None, last_message=timeout_message)
        return timeout_message

    def _add_plan_step(self, tool_name: str) -> None:
        """UI uchun bajarilayotgan amallar ro'yxatini yangilaydi."""
        plan = [dict(item) for item in self.state.plan]
        for item in plan:
            if item["status"] == "active":
                item["status"] = "done"
        plan.append({"label": tool_name, "status": "active"})
        self.state.update(plan=plan)

    def _finish_plan(self, status: str) -> None:
        plan = [dict(item) for item in self.state.plan]
        for item in plan:
            if item["status"] == "active":
                item["status"] = status
        self.state.update(plan=plan)

    def _execute_tool(self, tool_call: ToolCall) -> str:
        tool = self.tools.get(tool_call.name)
        if tool is None:
            return f"XATO: '{tool_call.name}' nomli tool topilmadi."
        try:
            if tool_call.name == "delegate_task":
                from tools.collaboration import set_delegation_source
                set_delegation_source(self.state.agent_id)
            return tool.run(**tool_call.arguments)
        except Exception as exc:  # tool ichidagi kutilmagan xatolik agent siklini to'xtatmasin
            return f"XATO: tool ishga tushganda muammo yuzaga keldi: {exc}"
