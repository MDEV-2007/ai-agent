"""
FastAPI server — piksel-ofis KO'RSATUVCHI qatlamini (frontend) backend
agentlarga ulaydi. Bir nechta nomli agent (roster) qo'llab-quvvatlanadi:
har biri o'z deski, ismi va roliga ega. Ishlash printsipi:
  - POST /chat — vazifani qabul qiladi (agent_id bilan), agentni fon thread'da
    ishga tushiradi. Har agent mustaqil — bir vaqtda bir nechtasi ishlashi mumkin.
  - GET  /ws   — barcha agentlar holatini real vaqtda WebSocket orqali uzatadi.
  - "/"        - ui/ papkasidagi piksel-ofis frontendini xizmat qiladi.
Agent loop (core/agent.py) o'zgarishsiz qoladi — server faqat uning
holatini (AgentState) tashqariga "ko'rsatadi".
"""
import asyncio
import json
import os
import threading
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# Telegram orqali kelgan vazifalar uchun tasdiqni ham Telegramga yuborish uchun
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from core.agent import Agent  # noqa: E402
from core.state import AgentState, AgentStatus  # noqa: E402
from safety.approval import set_approval_handler  # noqa: E402
from tools.collaboration import set_delegate_handler  # noqa: E402
from tools import registry  # noqa: E402

# Foydalanuvchi UI orqali javob berguncha agent thread'i qancha kutadi (soniya).
# Bu vaqt ichida javob kelmasa, xavfsizlik yuzasidan amal RAD etiladi.
APPROVAL_TIMEOUT_SEC = 180

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_FILE = DATA_DIR / "task_history.json"
HISTORY_LIMIT = 200

# Ofis jamoasi — har agent o'z ismi va roli bilan. Frontend shu tartibda
# desklarga o'tqazadi (roster tartibi = desk indeksi).
AGENT_ROSTER = [
    {"agent_id": "aziz", "name": "Aziz", "role": "Backend dasturchi"},
    {"agent_id": "malika", "name": "Malika", "role": "Frontend dasturchi"},
    {"agent_id": "bek", "name": "Bek", "role": "DevOps muhandis"},
    {"agent_id": "nilufar", "name": "Nilufar", "role": "Tadqiqotchi"},
    {"agent_id": "timur", "name": "Timur", "role": "QA muhandis"},
]
AGENT_META = {a["agent_id"]: {"name": a["name"], "role": a["role"]} for a in AGENT_ROSTER}

_agents: Dict[str, Agent] = {}
_connections: List[WebSocket] = []
_main_loop: Optional[asyncio.AbstractEventLoop] = None

# Kutilayotgan tasdiq so'rovlari: approval_id -> {event, decision, agent_id, reason}.
# Har so'rov agent thread'ini threading.Event bilan bloklaydi; UI javob berganda
# (yoki timeout) event "set" qilinadi.
_pending_approvals: Dict[str, dict] = {}
# Qaysi agent hozir shu thread'da ishlayotganini bilish uchun (approval handler
# uchun) — asyncio.to_thread thread'lari qayta ishlatiladi, shuning uchun har
# run boshida qiymat yangilanadi.
_current_agent = threading.local()


@dataclass
class TaskJob:
    id: str
    task: str
    source: str = "web"
    chat_id: Optional[str] = None  # Telegram'dan kelgan bo'lsa — tasdiqni shu chatga yuboramiz


_agent_queues: Dict[str, Deque[TaskJob]] = {}
_agent_workers: set[str] = set()
_queue_lock = threading.Lock()
_history_lock = threading.Lock()


def _load_history() -> List[dict]:
    """Avvalgi ishga tushirishlardagi tarixni ham saqlab qoladi."""
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


_task_history: List[dict] = _load_history()


def _save_history() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(_task_history[-HISTORY_LIMIT:], ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _queue_payload(agent_id: str) -> dict:
    with _queue_lock:
        queued = [job.task for job in _agent_queues.get(agent_id, ())]
        processing = agent_id in _agent_workers
    return {"type": "queue", "agent_id": agent_id, "queued": queued, "processing": processing}


def _delegate_to_agent(agent_id: str, task: str, source_agent_id: str) -> str:
    """Tool orqali kelgan delegatsiyani belgilangan agent navbatiga qo'shadi."""
    if agent_id not in _agents:
        return f"XATO: '{agent_id}' agent topilmadi."
    delegated_task = f"[{AGENT_META.get(source_agent_id, {}).get('name', source_agent_id)} delegatsiyasi] {task}"
    job = TaskJob(id=uuid.uuid4().hex, task=delegated_task, source="delegation")
    with _queue_lock:
        if agent_id in _agent_workers:
            _agent_queues[agent_id].append(job)
            position = len(_agent_queues[agent_id])
        else:
            _agent_workers.add(agent_id)
            position = 0
            if _main_loop is None:
                _agent_workers.discard(agent_id)
                return "XATO: server event loop hali tayyor emas."
            asyncio.run_coroutine_threadsafe(
                asyncio.to_thread(_run_agent_threaded, agent_id, job), _main_loop
            )
    _emit(_queue_payload(agent_id))
    name = AGENT_META[agent_id]["name"]
    return f"{name}ga vazifa yuborildi" + (f" (navbatda {position}-o'rin)." if position else ".")


def _record_history(agent: Agent, job: TaskJob, started_at: str, result: str) -> None:
    entry = {
        "id": job.id,
        "agent_id": agent.state.agent_id,
        "agent_name": AGENT_META.get(agent.state.agent_id, {}).get("name", agent.state.agent_id),
        "task": job.task,
        "source": job.source,
        "status": agent.state.status.value,
        "result": result,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "steps": agent.state.step,
    }
    with _history_lock:
        _task_history.append(entry)
        del _task_history[:-HISTORY_LIMIT]
        _save_history()
    _emit({"type": "history", "entry": entry})


def _send_telegram_approval(chat_id: Optional[str], approval_id: str, reason: str) -> None:
    """Tasdiq so'rovini Telegramga inline 'Ha/Yo'q' tugmalari bilan yuboradi.
    Telegram tugmasi bosilganda bot /approve ni chaqiradi (srvapprove:... callback)."""
    if not (TELEGRAM_BOT_TOKEN and chat_id):
        return
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Ha, ruxsat", "callback_data": f"srvapprove:{approval_id}:ok"},
        {"text": "🚫 Yo'q", "callback_data": f"srvapprove:{approval_id}:no"},
    ]]}
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": f"⚠️ Tasdiq talab qilinadi:\n\n{reason}\n\nRuxsat berasizmi?",
                  "reply_markup": keyboard},
            timeout=15,
        )
    except Exception:
        pass  # Telegramga yuborib bo'lmasa ham web modal ishlaydi; timeout'da xavfsiz rad etiladi


def _server_approval_handler(reason: str) -> bool:
    """Tasdiqni HAM web-ofisga (WS modal), HAM Telegramga (inline tugma) yuboradi.
    Foydalanuvchi qaysi biriga javob bersa (yoki timeout) agent thread'i davom etadi.
    Timeout bo'lsa xavfsizlik uchun RAD etiladi — 'ha' bermaguncha amal bajarilmaydi."""
    if _main_loop is None:
        return False

    agent_id = getattr(_current_agent, "agent_id", None)
    chat_id = getattr(_current_agent, "chat_id", None)
    approval_id = uuid.uuid4().hex
    event = threading.Event()
    _pending_approvals[approval_id] = {
        "event": event, "decision": False, "agent_id": agent_id, "reason": reason,
    }

    _emit({
        "type": "approval_request",
        "approval_id": approval_id,
        "agent_id": agent_id,
        "agent_name": AGENT_META.get(agent_id, {}).get("name", agent_id),
        "reason": reason,
    })
    _send_telegram_approval(chat_id, approval_id, reason)

    approved = event.wait(timeout=APPROVAL_TIMEOUT_SEC)
    slot = _pending_approvals.pop(approval_id, None)
    decision = bool(slot and slot["decision"]) if approved else False

    _emit({
        "type": "approval_resolved",
        "approval_id": approval_id,
        "decision": decision,
        "timed_out": not approved,
    })
    return decision


def _emit(payload: dict) -> None:
    """Ixtiyoriy paketni barcha WebSocket klientlarga (fon thread'idan) yuboradi."""
    if _main_loop is None:
        return
    asyncio.run_coroutine_threadsafe(_send_to_all(payload), _main_loop)


def _pending_approval_payloads() -> List[dict]:
    """Yangi ulangan klientga yuborish uchun hali javob berilmagan so'rovlar."""
    return [
        {
            "type": "approval_request",
            "approval_id": aid,
            "agent_id": slot["agent_id"],
            "agent_name": AGENT_META.get(slot["agent_id"], {}).get("name", slot["agent_id"]),
            "reason": slot["reason"],
        }
        for aid, slot in _pending_approvals.items()
    ]


def _state_payload(state: AgentState) -> dict:
    """Holat + agent metasi (ism, rol) — frontendga yuboriladigan to'liq paket."""
    payload = state.to_dict()
    payload.update(AGENT_META.get(state.agent_id, {}))
    payload["type"] = "state"
    return payload


def _run_agent_threaded(agent_id: str, first_job: TaskJob) -> None:
    """Agentni fon thread'ida ishga tushiradi va joriy agent_id'ni threadlocal'ga
    yozadi — shunda approval handler qaysi agent so'raganini biladi."""
    agent = _agents[agent_id]
    job: Optional[TaskJob] = first_job
    while job is not None:
        _current_agent.agent_id = agent_id
        _current_agent.chat_id = job.chat_id  # tasdiqni shu Telegram chatiga yo'naltirish uchun
        started_at = datetime.now(timezone.utc).isoformat()
        result = agent.run(job.task)
        _record_history(agent, job, started_at, result)
        with _queue_lock:
            queue = _agent_queues[agent_id]
            job = queue.popleft() if queue else None
            if job is None:
                _agent_workers.discard(agent_id)
        _emit(_queue_payload(agent_id))


def _broadcast_state(state: AgentState) -> None:
    """AgentState o'zgarganda barcha ulangan WebSocket klientlarga yuboradi.
    Bu callback agent.run() ishlayotgan fon thread'idan chaqirilishi mumkin,
    shuning uchun asosiy asyncio event loop'ga xavfsiz tarzda topshiriladi."""
    if _main_loop is None:
        return
    asyncio.run_coroutine_threadsafe(_send_to_all(_state_payload(state)), _main_loop)


async def _send_to_all(payload: dict) -> None:
    dead: List[WebSocket] = []
    for ws in _connections:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _connections:
            _connections.remove(ws)


def _create_agent(agent_id: str) -> Agent:
    state = AgentState(agent_id=agent_id)
    state.subscribe(_broadcast_state)
    return Agent(tools=registry, state=state, role=AGENT_META[agent_id]["role"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    set_approval_handler(_server_approval_handler)
    set_delegate_handler(_delegate_to_agent)
    for entry in AGENT_ROSTER:
        _agents[entry["agent_id"]] = _create_agent(entry["agent_id"])
        _agent_queues[entry["agent_id"]] = deque()
    yield


app = FastAPI(title="AgentLab HQ — Piksel Ofis", lifespan=lifespan)


class ChatRequest(BaseModel):
    task: str
    agent_id: str = AGENT_ROSTER[0]["agent_id"]
    task_id: Optional[str] = None
    source: str = "web"
    chat_id: Optional[str] = None  # Telegram'dan kelsa — tasdiq shu chatga yuboriladi


@app.post("/chat")
async def chat(req: ChatRequest) -> dict:
    """Vazifani qabul qiladi va tanlangan agentni alohida thread'da ishga
    tushiradi. Band agentga yangi vazifa berilmaydi."""
    agent = _agents.get(req.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent topilmadi: {req.agent_id}")
    job = TaskJob(id=req.task_id or uuid.uuid4().hex, task=req.task, source=req.source, chat_id=req.chat_id)
    with _queue_lock:
        if req.agent_id in _agent_workers:
            _agent_queues[req.agent_id].append(job)
            position = len(_agent_queues[req.agent_id])
            response = {"status": "navbatga qo'shildi", "agent_id": req.agent_id, "position": position, "task_id": job.id}
        else:
            _agent_workers.add(req.agent_id)
            response = {"status": "qabul qilindi", "agent_id": req.agent_id, "position": 0, "task_id": job.id}
            asyncio.create_task(asyncio.to_thread(_run_agent_threaded, req.agent_id, job))
    _emit(_queue_payload(req.agent_id))
    return response


@app.get("/history")
async def history(limit: int = 50) -> list:
    """Eng so'nggi bajarilgan vazifalar, server qayta ishga tushsa ham saqlanadi."""
    safe_limit = max(1, min(limit, HISTORY_LIMIT))
    with _history_lock:
        return list(reversed(_task_history[-safe_limit:]))


@app.get("/tasks/{task_id}")
async def task_status(task_id: str) -> dict:
    """Telegram kabi tashqi klientlar uchun yagona vazifaning yakuniy natijasi."""
    with _history_lock:
        for entry in reversed(_task_history):
            if entry["id"] == task_id:
                return {"status": "done", "entry": entry}
    with _queue_lock:
        for queue in _agent_queues.values():
            if any(job.id == task_id for job in queue):
                return {"status": "queued"}
    return {"status": "running"}


@app.get("/queue/{agent_id}")
async def queue(agent_id: str) -> dict:
    if agent_id not in _agents:
        raise HTTPException(status_code=404, detail="Agent topilmadi")
    return _queue_payload(agent_id)


class ApproveRequest(BaseModel):
    approval_id: str
    decision: bool


@app.post("/approve")
async def approve(req: ApproveRequest) -> dict:
    """UI'dan tasdiq javobini qabul qiladi: kutayotgan agent thread'ini uyg'otadi."""
    slot = _pending_approvals.get(req.approval_id)
    if slot is None:
        return {"status": "topilmadi"}  # allaqachon javob berilgan yoki timeout
    slot["decision"] = req.decision
    slot["event"].set()
    return {"status": "ok"}


@app.get("/agents")
async def list_agents() -> list:
    return [_state_payload(agent.state) for agent in _agents.values()]


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.append(websocket)
    for agent in _agents.values():
        await websocket.send_json(_state_payload(agent.state))
        await websocket.send_json(_queue_payload(agent.state.agent_id))
    # Yangi klient ochilganda hali javob berilmagan tasdiq so'rovlarini ham yuboramiz
    for payload in _pending_approval_payloads():
        await websocket.send_json(payload)
    try:
        while True:
            await websocket.receive_text()  # klientdan xabar kutmaymiz, ulanishni ushlab turamiz
    except WebSocketDisconnect:
        if websocket in _connections:
            _connections.remove(websocket)


app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
