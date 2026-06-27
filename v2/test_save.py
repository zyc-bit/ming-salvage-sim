"""v2 持久层 round-trip 测试(stdlib unittest,与仓库现有测试同约定)。

从仓库根运行:  .venv/bin/python -m unittest v2.test_save

刻意自建合成 GameState、不 import content.py/new_game:持久层不该依赖切片定义,
这样与并行修改 content.py/world.py 的队友零竞争。
"""
from __future__ import annotations

import json
import unittest

from v2.save import SAVE_DIR, load, save
from v2.state import Character, Crisis, Faction, GameState

SLOT = "__test__"


def _synthetic_state() -> GameState:
    return GameState(
        year=1628,
        month=4,
        metrics={"国库": 22, "皇威": 28, "民心": 45, "朝堂": 33, "耳目": 60, "边事": 50},
        factions={
            "甲党": Faction("甲党", satisfaction=48, leverage=78, note="把持朝政"),
            "乙党": Faction("乙党", satisfaction=62, leverage=38),  # note 取默认值
        },
        characters={
            "张三": Character("张三", office="首辅", faction="甲党", loyalty=40,
                            ability=70, stance="主和", persona="圆滑", secret="私通边将"),
            "李四": Character("李四", office="兵部尚书", faction="乙党", loyalty=66,
                            ability=82, stance="主战", persona="刚直"),
            "王五": Character("王五", office="司礼监", faction="甲党", loyalty=20,
                            ability=55, stance="自保", persona="阴鸷",
                            secret="贪墨军饷", active=False),
        },
        crises=[
            Crisis(id="c1", title="边关告急", brief="边军请饷",
                   truth="实为虚报冒领", adjudicator_notes="核查粮册"),
        ],
        slice_id="dingwei",
        chronicle=["开局即位", "诛除阉党"],
    )


class SaveRoundTripTests(unittest.TestCase):
    def tearDown(self) -> None:
        (SAVE_DIR / f"{SLOT}.json").unlink(missing_ok=True)

    def test_roundtrip_field_equal(self) -> None:
        state = _synthetic_state()
        save(state, slot=SLOT)
        loaded = load(SLOT)
        self.assertIsNotNone(loaded)
        # 标量
        self.assertEqual(loaded.year, state.year)
        self.assertEqual(loaded.month, state.month)
        self.assertEqual(loaded.slice_id, state.slice_id)
        # 原生容器透传
        self.assertEqual(loaded.metrics, state.metrics)
        self.assertEqual(loaded.chronicle, state.chronicle)
        # dataclass 容器:dataclass 自带逐字段 __eq__
        self.assertEqual(loaded.factions, state.factions)
        self.assertEqual(loaded.characters, state.characters)
        self.assertEqual(loaded.crises, state.crises)
        # 确认重建为 dataclass 实例,而非残留 dict
        self.assertTrue(all(isinstance(f, Faction) for f in loaded.factions.values()))
        self.assertTrue(all(isinstance(c, Character) for c in loaded.characters.values()))
        self.assertTrue(all(isinstance(c, Crisis) for c in loaded.crises))

    def test_load_missing_returns_none(self) -> None:
        self.assertIsNone(load("__nonexistent_slot__"))

    def test_backward_compat_extra_and_missing_fields(self) -> None:
        """旧档多了已删字段、少了新增字段,应平滑读回(过滤 + 默认值)。"""
        save(_synthetic_state(), slot=SLOT)
        path = SAVE_DIR / f"{SLOT}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        li = payload["state"]["characters"]["李四"]
        li["obsolete_field"] = "应被丢弃"  # 模拟未来已删除的字段
        li.pop("active")                  # 模拟新增(有默认值)字段在旧档中缺失
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        loaded = load(SLOT)
        self.assertIsNotNone(loaded)
        rebuilt = loaded.characters["李四"]
        self.assertIs(rebuilt.active, True)               # 缺失字段用默认值补
        self.assertFalse(hasattr(rebuilt, "obsolete_field"))  # 多余字段被过滤


if __name__ == "__main__":
    unittest.main()
