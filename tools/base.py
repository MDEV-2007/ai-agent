"""
Barcha tool'lar uchun bazaviy klass va ularni ro'yxatga olish (registry).
Har bir tool shu Tool klassidan meros oladi va o'zini global `registry`'ga
ro'yxatdan o'tkazadi — shundan keyin LLM uni ko'ra va chaqira oladi.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Tool(ABC):
    name: str = ""
    description: str = ""
    # JSON Schema — LLM'ga tool qanday parametr kutishini tushuntirish uchun
    parameters: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Tool'ni bajaradi va natijani matn ko'rinishida qaytaradi."""
        raise NotImplementedError

    def to_schema(self) -> Dict[str, Any]:
        """LLM uchun umumiy (provider'dan mustaqil) tool tavsifi."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """Barcha ro'yxatdan o'tgan tool'larni saqlaydigan registr."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all(self) -> List[Tool]:
        return list(self._tools.values())

    def schemas(self) -> List[Dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]


# Global registry — butun dastur davomida bitta nusxa ishlatiladi
registry = ToolRegistry()
