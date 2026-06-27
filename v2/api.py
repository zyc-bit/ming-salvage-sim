"""《明末》v2 — FastAPI 薄壳后端。

启动:
  set -a; source .env; set +a
  uvicorn v2.api:app --reload --port 8000
"""
from __future__ import annotations

import datetime
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .content import new_game
from .engine import apply_effects
from .events import next_from_pool
from . import llm
from .save import save, load, SAVE_DIR

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 服务器内存状态 (MVP 单玩家,无 DB) ─────────────────────────────────────
_state = None
_summon_log: list = []
_month_decree: str | None = None
_history: dict = {}   # name → [(role, text)] 跨月召对历史


def _state_payload(state) -> dict[str, Any]:
    """白名单投影:显式构造只该让玩家看到的字段。
    绝不 asdict(整局)再删——避免泄露 secret/truth/adjudicator_notes/cast/persona。
    """
    cr = state.active_crisis()
    return {
        "year": state.year,
        "month": state.month,
        "slice_id": state.slice_id,
        "metrics": dict(state.metrics),
        "factions": [
            {
                "name": f.name,
                "satisfaction": f.satisfaction,
                "leverage": f.leverage,
                "note": f.note,
            }
            for f in state.factions.values()
        ],
        "characters": [
            {
                "name": ch.name,
                "office": ch.office,
                "faction": ch.faction,
                "stance": ch.stance,
                "active": ch.active,
            }
            for ch in state.characters.values()
        ],
        "active_crisis": {"title": cr.title, "brief": cr.brief} if cr else None,
        "chronicle": list(state.chronicle),
        "month_decree": _month_decree,
    }


# ── 请求模型 ──────────────────────────────────────────────────────────────

class NewGameReq(BaseModel):
    slice_id: str = "dingwei"


class SummonReq(BaseModel):
    name: str
    message: str


class DecreeReq(BaseModel):
    text: str


class LlmConfigReq(BaseModel):
    api_key: str = ""
    model: str = ""
    base_url: str = ""


# ── 端点 ──────────────────────────────────────────────────────────────────

@app.post("/api/v2/game/new")
async def api_new_game(req: NewGameReq):
    global _state, _summon_log, _month_decree, _history
    if req.slice_id not in ("dingwei", "liaodong"):
        raise HTTPException(400, f"未知切片「{req.slice_id}」")
    _state = new_game(req.slice_id)
    _summon_log = []
    _month_decree = None
    _history = {}
    return _state_payload(_state)


@app.get("/api/v2/game/state")
async def api_game_state():
    if _state is None:
        raise HTTPException(404, "尚无进行中的局。")
    return _state_payload(_state)


@app.post("/api/v2/game/summon")
async def api_summon(req: SummonReq):
    global _summon_log, _history
    if _state is None:
        raise HTTPException(404, "尚无进行中的局。")
    if _state.active_crisis() is None:
        raise HTTPException(400, "局已结束。")
    if req.name not in _state.characters:
        raise HTTPException(404, f"人物「{req.name}」不存在。")
    if not _state.characters[req.name].active:
        raise HTTPException(400, f"「{req.name}」已不在朝。")
    hist = _history.setdefault(req.name, [])
    try:
        reply = llm.summon(_state, req.name, hist, req.message)
    except Exception as exc:
        raise HTTPException(502, f"召对失败:{exc}") from exc
    hist += [("帝", req.message), (req.name, reply)]
    _summon_log += [(f"帝问{req.name}", req.message), (req.name, reply)]
    return {"reply": reply}


@app.post("/api/v2/game/decree")
async def api_decree(req: DecreeReq):
    global _month_decree
    if _state is None:
        raise HTTPException(404, "尚无进行中的局。")
    _month_decree = req.text.strip() or None
    return {"ok": True, "month_decree": _month_decree}


@app.post("/api/v2/game/advance")
async def api_advance():
    global _summon_log, _month_decree
    if _state is None:
        raise HTTPException(404, "尚无进行中的局。")
    if _state.active_crisis() is None:
        raise HTTPException(400, "局已结束,无需推演。")
    decree = _month_decree or "(本月未下处置之旨,留中观望)"
    try:
        res = llm.adjudicate(_state, decree, _summon_log)
    except Exception as exc:
        raise HTTPException(502, f"推演失败:{exc}") from exc
    notes = apply_effects(_state, res.get("effects", []))
    _state.chronicle.append(res.get("narrative", ""))
    if res.get("resolved"):
        cr = _state.active_crisis()
        if cr:
            cr.resolved = True
            nxt = next_from_pool(_state)
            if nxt:
                _state.crises.append(nxt)
    _month_decree = None
    _summon_log = []
    _state.month += 1
    return {
        "narrative": res.get("narrative", ""),
        "resolved": res.get("resolved", False),
        "effects": res.get("effects", []),
        "notes": notes,
        "state": _state_payload(_state),
    }


@app.get("/api/v2/saves")
async def api_list_saves():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    slots = [p.stem for p in sorted(SAVE_DIR.glob("*.json"))]
    return {"slots": slots}


@app.post("/api/v2/saves/{slot}")
async def api_save(slot: str):
    if _state is None:
        raise HTTPException(404, "尚无进行中的局。")
    save(_state, slot)
    return {"slot": slot, "saved_at": datetime.datetime.now().isoformat()}


@app.post("/api/v2/saves/{slot}/load")
async def api_load(slot: str):
    global _state, _summon_log, _month_decree, _history
    state = load(slot)
    if state is None:
        raise HTTPException(404, f"存档槽「{slot}」不存在。")
    _state = state
    _summon_log = []
    _month_decree = None
    _history = {}
    return _state_payload(_state)


@app.get("/api/v2/llm")
async def api_get_llm():
    return {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "base_url": os.environ.get("OPENAI_BASE_URL", ""),
        "has_key": bool(os.environ.get("OPENAI_API_KEY", "")),
    }


@app.post("/api/v2/llm")
async def api_set_llm(req: LlmConfigReq):
    """热更新 LLM 配置(仅内存,重启失效)。"""
    if req.api_key:
        os.environ["OPENAI_API_KEY"] = req.api_key
    if req.model:
        os.environ["OPENAI_MODEL"] = req.model
    if req.base_url:
        os.environ["OPENAI_BASE_URL"] = req.base_url
    llm._client = None  # 重置单例,下次调用重建
    return {"ok": True}
