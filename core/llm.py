"""
Anthropic, Groq va lokal Ollama LLM providerlarini bitta umumiy interfeysga
keltiruvchi qatlam. Qaysi provider ishlatilishi LLM_PROVIDER environment
o'zgaruvchisi orqali tanlanadi ("anthropic", "groq" yoki "ollama"). Agent
(core/agent.py) va boshqa kod provider'ning ichki tafsilotlarini bilishi shart
emas — faqat LLMClient.chat(...) chaqiradi.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_MAX_TOKENS = 4096


@dataclass
class ToolCall:
    """LLM tomonidan so'ralgan bitta tool chaqiruvi."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class Message:
    """Provider'dan mustaqil, umumiy suhbat xabari (agent shu formatda ishlaydi)."""
    role: str  # "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)  # assistant tool chaqirganda
    tool_call_id: str = ""  # role="tool" bo'lganda — qaysi chaqiruvga javob ekani


@dataclass
class LLMResponse:
    content: str
    tool_calls: List[ToolCall]


class _AnthropicBackend:
    def __init__(self, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model

    @staticmethod
    def _tool_schema(tools: List[dict]) -> List[dict]:
        return [
            {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
            for t in tools
        ]

    @staticmethod
    def _to_anthropic_messages(messages: List[Message]) -> List[dict]:
        result: List[dict] = []
        for msg in messages:
            if msg.role == "user":
                result.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                blocks: List[dict] = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                result.append({"role": "assistant", "content": blocks})
            elif msg.role == "tool":
                result.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": msg.tool_call_id, "content": msg.content}
                        ],
                    }
                )
        return result

    def chat(self, system_prompt: str, messages: List[Message], tools: List[dict]) -> LLMResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system_prompt,
            messages=self._to_anthropic_messages(messages),
            tools=self._tool_schema(tools) if tools else [],
        )
        text = ""
        tool_calls: List[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
        return LLMResponse(content=text, tool_calls=tool_calls)


class _GroqBackend:
    def __init__(self, model: str) -> None:
        from groq import Groq

        self._client = Groq()
        self._model = model

    @staticmethod
    def _tool_schema(tools: List[dict]) -> List[dict]:
        return [
            {
                "type": "function",
                "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
            }
            for t in tools
        ]

    @staticmethod
    def _to_openai_messages(system_prompt: str, messages: List[Message]) -> List[dict]:
        result: List[dict] = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            if msg.role == "user":
                result.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                entry: dict = {"role": "assistant", "content": msg.content or None}
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in msg.tool_calls
                    ]
                result.append(entry)
            elif msg.role == "tool":
                result.append({"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content})
        return result

    def chat(self, system_prompt: str, messages: List[Message], tools: List[dict]) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=self._to_openai_messages(system_prompt, messages),
            tools=self._tool_schema(tools) if tools else None,
        )
        choice = response.choices[0].message
        tool_calls: List[ToolCall] = []
        for tc in choice.tool_calls or []:
            tool_calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments or "{}"))
            )
        return LLMResponse(content=choice.content or "", tool_calls=tool_calls)


class _OllamaBackend:
    """Kompyuterda lokal ishlaydigan Ollama serveriga ulanadi
    (standart: http://localhost:11434). qwen3-coder:30b yoki qwen3:8b kabi
    tool-calling'ni qo'llaydigan modellar bilan ishlaydi. API kaliti kerak emas,
    hamma narsa lokal — internetsiz ham ishlaydi."""

    def __init__(self, model: str) -> None:
        import ollama

        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._client = ollama.Client(host=host)
        self._model = model

    @staticmethod
    def _tool_schema(tools: List[dict]) -> List[dict]:
        return [
            {
                "type": "function",
                "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
            }
            for t in tools
        ]

    @staticmethod
    def _to_messages(system_prompt: str, messages: List[Message]) -> List[dict]:
        result: List[dict] = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            if msg.role == "user":
                result.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                entry: dict = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    # Ollama argumentlarni lug'at (dict) ko'rinishida kutadi
                    entry["tool_calls"] = [
                        {"function": {"name": tc.name, "arguments": tc.arguments}}
                        for tc in msg.tool_calls
                    ]
                result.append(entry)
            elif msg.role == "tool":
                result.append({"role": "tool", "content": msg.content})
        return result

    @staticmethod
    def _strip_think(text: str) -> str:
        """qwen3 modellari <think>...</think> ichki mulohaza bloklarini qo'shadi —
        ularni foydalanuvchiga ko'rsatmaslik uchun olib tashlaymiz."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _coerce(value: str):
        """Matndan olingan argument qiymatini mos turga o'giradi (son/bool/matn)."""
        v = value.strip()
        if re.fullmatch(r"-?\d+", v):
            return int(v)
        if re.fullmatch(r"-?\d*\.\d+", v):
            return float(v)
        low = v.lower()
        if low in ("true", "false"):
            return low == "true"
        return v

    @classmethod
    def _parse_text_tool_calls(cls, text: str):
        """Ba'zi modellar (ayniqsa qwen-coder) tool chaqiruvini STRUKTURA emas,
        MATN sifatida chiqaradi — masalan:
            <function=open_app><parameter=app_name>chrome</parameter></function>
        yoki <tool_call>{"name": "...", "arguments": {...}}</tool_call>.
        Bunday holatda Ollama ularni tool_calls'ga solmaydi, natijada bot amalni
        bajarmasdan shu matnni qaytaradi. Shu funksiya o'sha matnni tanib olib,
        haqiqiy tool chaqiruvlariga aylantiradi va matndan tozalab beradi.

        Qaytaradi: (tozalangan_matn, [(nom, argumentlar), ...])
        """
        calls = []
        cleaned = text

        # 1) qwen-coder XML uslubi: <function=NOM> ... <parameter=KALIT>QIYMAT</parameter> ... </function>
        for m in re.finditer(r"<function\s*=\s*([^>\s]+)\s*>(.*?)</function>", text, re.DOTALL):
            name = m.group(1).strip()
            args = {}
            for pm in re.finditer(r"<parameter\s*=\s*([^>\s]+)\s*>(.*?)</parameter>", m.group(2), re.DOTALL):
                args[pm.group(1).strip()] = cls._coerce(pm.group(2))
            calls.append((name, args))
            cleaned = cleaned.replace(m.group(0), "")

        # 2) Hermes/JSON uslubi: <tool_call>{"name": "...", "arguments": {...}}</tool_call>
        for m in re.finditer(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL):
            try:
                obj = json.loads(m.group(1))
                name = obj.get("name")
                args = obj.get("arguments") or obj.get("parameters") or {}
                if name:
                    calls.append((name, args if isinstance(args, dict) else {}))
                    cleaned = cleaned.replace(m.group(0), "")
            except Exception:
                pass

        # Qolib ketgan yolg'iz teglarni tozalaymiz
        cleaned = re.sub(r"</?tool_call>", "", cleaned).strip()
        return cleaned, calls

    def chat(self, system_prompt: str, messages: List[Message], tools: List[dict]) -> LLMResponse:
        # think=False — qwen3 modellarining "thinking" (ichki mulohaza) rejimini
        # o'chiradi. Bu tool-calling vazifalarida 3 barobargacha tezlashtiradi.
        # keep_alive — modelni xotirada ushlab turadi, qayta-qayta yuklanmaydi.
        kwargs = {
            "model": self._model,
            "messages": self._to_messages(system_prompt, messages),
            "tools": self._tool_schema(tools) if tools else None,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
        }
        try:
            response = self._client.chat(think=False, **kwargs)
        except Exception as exc:
            # Model yoki eski ollama-python 'think=False' ni qo'llamasa — usiz qayta urinamiz
            if "think" not in str(exc).lower() and not isinstance(exc, TypeError):
                raise
            response = self._client.chat(**kwargs)
        message = response.message
        content = self._strip_think(message.content or "")
        tool_calls: List[ToolCall] = []
        for i, tc in enumerate(message.tool_calls or []):
            args = tc.function.arguments
            if isinstance(args, str):
                args = json.loads(args or "{}")
            tool_calls.append(ToolCall(id=f"call_{i}", name=tc.function.name, arguments=dict(args)))

        # Native tool_calls bo'sh, lekin matnda <function=...> yoki <tool_call> ko'rinishida
        # tool chaqiruvi "sizib chiqqan" bo'lsa (ba'zi qwen-coder javoblarida bo'ladi) —
        # uni tanib olib haqiqiy chaqiruvga aylantiramiz, aks holda bot amalni bajarmasdan
        # xom matnni qaytaradi.
        if not tool_calls and content and ("<function" in content or "<tool_call" in content):
            cleaned, parsed = self._parse_text_tool_calls(content)
            if parsed:
                content = cleaned
                for i, (name, args) in enumerate(parsed):
                    tool_calls.append(ToolCall(id=f"txt_{i}", name=name, arguments=dict(args)))

        return LLMResponse(content=content, tool_calls=tool_calls)


class LLMClient:
    """Anthropic/Groq/Ollama orasidagi farqni yashiruvchi umumiy klient."""

    def __init__(self, provider: Optional[str] = None) -> None:
        self.provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
        if self.provider == "anthropic":
            model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
            self._backend: Any = _AnthropicBackend(model)
        elif self.provider == "groq":
            model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            self._backend = _GroqBackend(model)
        elif self.provider == "ollama":
            model = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b")
            self._backend = _OllamaBackend(model)
        else:
            raise ValueError(
                f"Noma'lum LLM_PROVIDER: {self.provider} (anthropic, groq yoki ollama bo'lishi kerak)"
            )

    def chat(self, system_prompt: str, messages: List[Message], tools: List[dict]) -> LLMResponse:
        return self._backend.chat(system_prompt, messages, tools)
