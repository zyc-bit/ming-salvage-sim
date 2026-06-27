"""事件记忆生成：把诏书与月末推演结果压成渐进式记忆卡。"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from agno.agent import Agent

from ming_sim.agents import parse_agent_json, run_agent_text
from ming_sim.db import GameDB
from ming_sim.models import GameState
from ming_sim.token_stats import tlog


def _short(text: object, limit: int = 80) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _title(text: object, limit: int = 20) -> str:
    s = _short(text, limit)
    return s or "旧事记忆"


def _tags(*values: object) -> List[str]:
    out: List[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            items = value
        else:
            items = [value]
        for item in items:
            tag = str(item or "").strip()
            if tag and tag not in out:
                out.append(tag[:40])
    return out


_SOURCE_KINDS = {
    "directive",
    "decree",
    "simulation_narrative",
    "extractor_output",
    "issue",
    "chat_message",
    "turn_report",
    "system",
}

_TURN_SOURCE_KINDS = {"decree", "simulation_narrative", "extractor_output", "turn_report"}
_TURN_SOURCE_SENTINELS = {
    "",
    "decree",
    "simulation_narrative",
    "extractor_output",
    "turn_report",
    "narrative",
    "current_turn",
    "turn",
}


def _normalize_source_kind(value: object) -> str:
    source_kind = str(value or "system").strip()
    return source_kind if source_kind in _SOURCE_KINDS else "system"


def _normalize_source_id(source_kind: str, source_id: object, state: GameState) -> str:
    raw = str(source_id or "").strip()
    if source_kind in _TURN_SOURCE_KINDS and raw in _TURN_SOURCE_SENTINELS:
        return str(state.turn)
    if source_kind == "directive" and raw.startswith("#"):
        raw = raw[1:]
    if source_kind == "issue" and raw.startswith("#"):
        raw = raw[1:]
    return raw or str(state.turn)


def _normalize_locator(locator: object, source_kind: str, source_id: str, state: GameState) -> Dict[str, object]:
    loc = locator if isinstance(locator, dict) else {}
    out: Dict[str, object] = {}
    if source_kind in _TURN_SOURCE_KINDS:
        out["turn"] = int(source_id) if str(source_id).isdigit() else state.turn
    elif source_kind == "directive":
        out["directive_id"] = int(source_id) if str(source_id).isdigit() else source_id
    elif source_kind == "issue":
        out["issue_id"] = int(source_id) if str(source_id).isdigit() else source_id
    elif source_kind == "chat_message":
        out["chat_id"] = source_id
    allowed_fields = {
        "directive": {"text", "notes", "status"},
        "decree": {"decree_text"},
        "simulation_narrative": {"narrative"},
        "extractor_output": {
            "extractor_output",
            "issue_summary",
            "office_changes",
            "character_status_changes",
            "region_changes",
            "army_changes",
            "faction_delta",
        },
        "issue": {"issue", "issue_summary", "advances", "new_issues", "closes"},
        "turn_report": {"report"},
        "chat_message": {"content"},
        "system": {"system"},
    }
    field = str(loc.get("field") or "").strip()
    if field in allowed_fields.get(source_kind, set()):
        out["field"] = field
    elif source_kind == "decree":
        out["field"] = "decree_text"
    elif source_kind == "simulation_narrative":
        out["field"] = "narrative"
    elif source_kind == "extractor_output":
        out["field"] = "extractor_output"
    return out


def _normalize_memory_item(item: object, state: GameState) -> Optional[Dict[str, object]]:
    if not isinstance(item, dict):
        return None
    subject_type = str(item.get("subject_type") or "").strip()
    subject_id = str(item.get("subject_id") or "").strip()
    event_type = str(item.get("event_type") or "").strip()
    source_kind = _normalize_source_kind(item.get("source_kind"))
    source_id = _normalize_source_id(source_kind, item.get("source_id"), state)
    if not subject_type or not subject_id or not event_type or not source_id:
        return None
    try:
        importance = int(item.get("importance") or 3)
    except (TypeError, ValueError):
        importance = 3
    expires_raw = item.get("expires_turn")
    try:
        expires_turn = int(expires_raw) if expires_raw not in (None, "", "null") else None
    except (TypeError, ValueError):
        expires_turn = None
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    sources = item.get("sources") if isinstance(item.get("sources"), list) else []
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "event_type": event_type,
        "title": _title(item.get("title")),
        "cause": _short(item.get("cause")),
        "process": _short(item.get("process")),
        "outcome": _short(item.get("outcome")),
        "sentiment": str(item.get("sentiment") or "neutral"),
        "importance": max(1, min(5, importance)),
        "tags": _tags(tags),
        "source_kind": source_kind,
        "source_id": source_id,
        "expires_turn": expires_turn,
        "sources": sources,
    }


def _write_llm_memories(db: GameDB, state: GameState, data: Dict[str, object]) -> int:
    count = 0
    for raw in data.get("memories") or []:
        item = _normalize_memory_item(raw, state)
        if not item:
            continue
        memory_id = db.upsert_event_memory(
            state,
            subject_type=str(item["subject_type"]),
            subject_id=str(item["subject_id"]),
            event_type=str(item["event_type"]),
            title=str(item["title"]),
            cause=str(item["cause"]),
            process=str(item["process"]),
            outcome=str(item["outcome"]),
            sentiment=str(item["sentiment"]),
            importance=int(item["importance"]),
            tags=list(item["tags"]),
            source_kind=str(item["source_kind"]),
            source_id=str(item["source_id"]),
            expires_turn=item["expires_turn"],  # type: ignore[arg-type]
        )
        if not memory_id:
            continue
        tlog(f"[memory/write] id={memory_id} subject={item['subject_id']} event={item['event_type']} "
             f"title={item['title']!r} importance={item['importance']} source={item['source_kind']}:{item['source_id']}")
        for src in item["sources"]:  # type: ignore[index]
            if not isinstance(src, dict):
                continue
            source_kind = _normalize_source_kind(src.get("source_kind") or item["source_kind"])
            source_id = _normalize_source_id(source_kind, src.get("source_id") or item["source_id"], state)
            db.add_event_memory_source(
                memory_id,
                source_kind=source_kind,
                source_id=source_id,
                excerpt=_short(src.get("excerpt"), 200),
                locator=_normalize_locator(src.get("locator"), source_kind, source_id, state),
            )
        count += 1
    db.prune_event_memories_for_turn(state.turn, per_subject=3)
    tlog(f"[memory/extractor] llm_written={count}")
    return count


def extract_chat_memories_for_minister(
    agent: Agent,
    db: GameDB,
    state: GameState,
    minister_name: str,
    chat_history: List[Dict[str, str]],
) -> int:
    """用 LLM 从单个大臣当月召对提取承诺/建议/情报记忆，写入 event_memory。"""
    if not chat_history:
        return 0
    tlog(f"[chat-memory] minister={minister_name} msgs={len(chat_history)} turn={state.turn}")
    payload = {
        "turn": {"year": state.year, "period": state.period, "turn": state.turn},
        "minister_name": minister_name,
        "chat_history": chat_history,
        "instruction": "提取本次召对的结构化记忆卡，只写有实质内容的承诺/建议/情报，闲聊跳过。",
    }
    raw = run_agent_text(agent, json.dumps(payload, ensure_ascii=False, sort_keys=False), tag="chat-memory")
    tlog(f"[chat-memory] raw_output({len(raw)}字): {raw[:300]}")
    data = parse_agent_json(raw, "对话记忆抽取")
    mem_list = data.get("memories") or []
    tlog(f"[chat-memory] parsed memories={len(mem_list)}: "
         + str([(m.get("event_type"), m.get("title")) for m in mem_list if isinstance(m, dict)]))
    # source_kind 强制为 chat_message，source_id 强制为 minister_name:turn
    for item in mem_list:
        if isinstance(item, dict):
            item["source_kind"] = "chat_message"
            item["source_id"] = f"{minister_name}:{state.turn}"
    return _write_llm_memories(db, state, data)


def extract_all_chat_memories(agent: Agent, db: GameDB, state: GameState) -> int:
    """对当月所有有过召对的大臣各跑一次记忆提取，单个失败不阻断。"""
    chat_by_minister = db.get_chat_messages_for_turn(state.turn)
    total = 0
    for minister_name, history in chat_by_minister.items():
        try:
            n = extract_chat_memories_for_minister(agent, db, state, minister_name, history)
            total += n
        except Exception as exc:
            tlog(f"[chat-memory] minister={minister_name} 失败，跳过：{exc}")
    tlog(f"[chat-memory] total_written={total}")
    return total
