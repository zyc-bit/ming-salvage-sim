"""《明末》v2 — 最小持久层:整局状态存成一个 JSON blob。

- save(state, slot) → data/v2_saves/<slot>.json(临时文件 + 原子替换,防写一半损档)
- load(slot) → GameState | None(无档返回 None,让调用方决定读档还是开新局)

向后兼容:读回时按 dataclass 现有字段过滤——已删字段自动丢弃,
新增字段(须带默认值)由 dataclass 默认值补,无需迁移层。
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from .state import GameState, Faction, Character, Crisis

# 与 v1 的 SQLite 同在 data/ 下,但用子目录物理隔离,互不污染。
SAVE_DIR = Path(__file__).resolve().parent.parent / "data" / "v2_saves"
SCHEMA_VERSION = 1


def save(state: GameState, slot: str = "auto") -> Path:
    """整局状态 → data/v2_saves/<slot>.json,返回写入路径。"""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "_v": SCHEMA_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "state": dataclasses.asdict(state),
    }
    path = SAVE_DIR / f"{slot}.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # 同盘原子替换
    return path


def _rebuild(cls, d: dict):
    """按 cls 现有字段过滤后构造:多余字段丢弃,缺失字段交给 dataclass 默认值。"""
    keep = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in keep})


def load(slot: str = "auto") -> GameState | None:
    """读回存档;无档返回 None。dataclass 容器逐层重建,原生类型透传。"""
    path = SAVE_DIR / f"{slot}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    s = dict(payload.get("state", payload))  # 兼容无信封的裸 state,且不改原 dict
    s["factions"] = {k: _rebuild(Faction, v) for k, v in s.get("factions", {}).items()}
    s["characters"] = {k: _rebuild(Character, v) for k, v in s.get("characters", {}).items()}
    s["crises"] = [_rebuild(Crisis, c) for c in s.get("crises", [])]
    return _rebuild(GameState, s)
