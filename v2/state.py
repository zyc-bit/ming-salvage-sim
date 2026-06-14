"""《明末》v2 — 状态模型。

新架构三铁律(见 README):
1) 极简底层:几个国势 + 几股势力 + 人物 + 危机,深度来自联动不来自维度。
2) LLM 只当「嘴」与「裁判」,代码管状态机与数值,边界清晰、不互相翻译。
3) 信息不全 / 君命直贯 / 没有最优解 / 后果连锁,从第一刀就缝在一起。
"""
from __future__ import annotations
from dataclasses import dataclass, field

# 五个国势(0-100)。「耳目」= 皇帝的情报获取力,诛厂卫会掉它 → 信息迷雾机制化。
METRIC_KEYS = ["国库", "皇威", "民心", "朝堂", "耳目"]


@dataclass
class Faction:
    name: str
    satisfaction: int   # 对当前局面/皇帝的态度
    leverage: int       # 在朝堂与天下的实际能量
    note: str = ""


@dataclass
class Character:
    name: str
    office: str
    faction: str
    loyalty: int        # 对皇帝的忠诚
    ability: int
    stance: str         # 当前主张(玩家可见)
    persona: str        # 性格与说话方式(供 LLM 扮演)
    secret: str = ""    # 皇帝未必知道的底细(信息不全的来源之一)
    active: bool = True


@dataclass
class Crisis:
    id: str
    title: str
    brief: str          # 皇帝所知(可能不全/被粉饰)
    truth: str          # 真相(隐藏;只喂给裁判 LLM,不直接示玩家)
    resolved: bool = False


@dataclass
class GameState:
    year: int
    month: int
    energy: int
    metrics: dict
    factions: dict
    characters: dict
    crises: list
    chronicle: list = field(default_factory=list)

    def metric_line(self) -> str:
        return "   ".join(f"{k}{self.metrics[k]:>3}" for k in METRIC_KEYS)

    def active_crisis(self):
        for c in self.crises:
            if not c.resolved:
                return c
        return None
