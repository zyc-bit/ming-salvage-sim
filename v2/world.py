"""《明末》v2 — 从 v1 content/ 加载真实人物/派系基线。

只读 content/characters.json,把「人物身份基线」映射成 v2 极简 dataclass;
切片(content.py)在此基线上覆盖戏剧字段(stance/secret/persona、以及游戏化微调的
office/ability/loyalty/faction)。

刻意不 import ming_sim:v1 内核已冻结,v2 边界须自洽。这里只用标准库读 JSON。
"""
from __future__ import annotations

import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from .state import Character, Faction


def content_dir() -> Path:
    """content/ 目录定位的唯一缝。若 v2 日后被打包安装,只改此处即可。"""
    return Path(__file__).resolve().parents[1] / "content"


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads((content_dir() / "characters.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_v1_characters() -> "dict[str, Character]":
    """v1 characters.json → {name: v2 Character 基线}。

    stance/secret 留空、persona 以 v1 style 作种子、active 由 status 折算;丢弃 v1 的
    office_type/aliases/personal_skills/integrity/courage/power_id/location/历史年份/
    portrait_id 等极简内核不需要的字段。切片再行覆盖。
    """
    out: "dict[str, Character]" = {}
    for item in _raw().get("characters", []):
        name = str(item["name"])
        out[name] = Character(
            name=name,
            office=str(item.get("office", "")),
            faction=str(item.get("faction", "中立")),
            loyalty=int(item.get("loyalty", 0)),
            ability=int(item.get("ability", 0)),
            stance="",
            persona=str(item.get("style", "")),
            secret="",
            active=(str(item.get("status", "active")) == "active"),
        )
    return out


@lru_cache(maxsize=1)
def load_v1_factions() -> "dict[str, Faction]":
    """v1 characters.json.factions → {name: v2 Faction 基线}(note <- agenda)。"""
    out: "dict[str, Faction]" = {}
    for item in _raw().get("factions", []):
        name = str(item["name"])
        out[name] = Faction(
            name=name,
            satisfaction=int(item.get("satisfaction", 0)),
            leverage=int(item.get("leverage", 0)),
            note=str(item.get("agenda", "")),
        )
    return out


def character(name: str, **override) -> Character:
    """取 v1 人物基线 + 切片覆盖。name 必须存在于 content/characters.json。"""
    base = load_v1_characters().get(name)
    if base is None:
        raise KeyError(f"content/characters.json 无此人物:{name!r}")
    return replace(base, **override)


def faction(name: str, **override) -> Faction:
    """取 v1 派系基线 + 切片覆盖。name 必须存在于 content/characters.json.factions。"""
    base = load_v1_factions().get(name)
    if base is None:
        raise KeyError(f"content/characters.json.factions 无此派系:{name!r}")
    return replace(base, **override)


# —— 只读世界盘面:地区/军队/势力作为「事实背景」,绝不进玩家仪表盘、绝不被 apply_effects 改动 ——

@lru_cache(maxsize=None)
def _doc(filename: str) -> dict:
    """读 content/<filename> JSON。只读世界盘面共用此口。"""
    return json.loads((content_dir() / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_regions() -> "dict[str, dict]":
    """content/regions.json → {id: 精简只读投影};丢弃 fiscal/land/tax 等重字段。"""
    out: "dict[str, dict]" = {}
    for r in _doc("regions.json")["regions"]:
        dis = "、".join(s for s in (r.get("natural_disaster"), r.get("human_disaster")) if s)
        out[r["id"]] = {"name": r["name"], "kind": r["kind"],
                        "public_support": r["public_support"], "unrest": r["unrest"],
                        "disaster": dis or "—"}
    return out


@lru_cache(maxsize=1)
def load_armies() -> "dict[str, dict]":
    """content/armies.json → {id: 精简只读投影};丢弃 theater/supply/training 等重字段。"""
    return {a["id"]: {"name": a["name"], "station": a["station"], "commander": a["commander"],
                      "morale": a["morale"], "arrears": a["arrears"], "loyalty": a["loyalty"]}
            for a in _doc("armies.json")["armies"]}


@lru_cache(maxsize=1)
def load_powers() -> "dict[str, dict]":
    """content/powers.json → {id: 精简只读投影};丢弃 leverage/cohesion/last_action 等重字段。"""
    return {p["id"]: {"name": p["name"], "leader": p["leader"], "stance": p["stance"],
                      "agenda": p["agenda"]}
            for p in _doc("powers.json")["powers"]}


def _resolve(key: str):
    """按 id 优先、name 兜底,在地区/军队/势力中定位一个只读实体。"""
    for kind, loader in (("地区", load_regions), ("军队", load_armies), ("势力", load_powers)):
        store = loader()
        hit = store.get(key) or next((v for v in store.values() if v["name"] == key), None)
        if hit:
            return kind, hit
    return None, None


def _fmt(kind: str, p: dict) -> str:
    if kind == "地区":
        return f"〔地区〕{p['name']}({p['kind']}) 民心{p['public_support']} 民乱{p['unrest']} 灾情:{p['disaster']}"
    if kind == "军队":
        return f"〔军队〕{p['name']} 驻{p['station']} 帅{p['commander']} 士气{p['morale']} 欠饷{p['arrears']}万两 忠诚{p['loyalty']}"
    return f"〔势力〕{p['name']} 首领{p['leader']} 态度{p['stance']} 图谋:{p['agenda']}"


def backdrop(cast) -> str:
    """危机点名(cast: 一组 id 或 name)→ 紧凑只读「天下实况」事实表,供 llm._scene 注入。
    无 cast 或全部无法解析时返回空串,危机行为完全不变。"""
    lines = [_fmt(k, p) for k, p in (_resolve(x) for x in (cast or [])) if p]
    return "\n【天下实况(只读背景)】\n" + "\n".join(lines) if lines else ""
