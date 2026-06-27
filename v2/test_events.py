"""事件池验收测试：gate / next_from_pool / 迷雾前缀 / world.backdrop 接棒非空。

从仓库根运行:  .venv/bin/python -m unittest v2.test_events
"""
import unittest

from . import world
from .content import new_game
from .events import DINGWEI_POOL, _gate_met, next_from_pool


class TestGateMet(unittest.TestCase):
    def test_simple_lte_passes(self):
        self.assertTrue(_gate_met({"国库": "<=24"}, {"国库": 22}))

    def test_simple_lte_fails(self):
        self.assertFalse(_gate_met({"国库": "<=24"}, {"国库": 30}))

    def test_simple_gte_passes(self):
        self.assertTrue(_gate_met({"民心": ">=40"}, {"民心": 45}))

    def test_simple_gte_fails(self):
        self.assertFalse(_gate_met({"民心": ">=40"}, {"民心": 35}))

    def test_dot_path_skipped(self):
        # 子指标点号路径视为满足，不阻断
        self.assertTrue(_gate_met({"army.guanning.arrears": ">=65"}, {}))

    def test_empty_gate_always_true(self):
        self.assertTrue(_gate_met({}, {"国库": 5}))

    def test_unknown_key_skipped(self):
        self.assertTrue(_gate_met({"不存在字段": "<=10"}, {}))


class TestNextFromPool(unittest.TestCase):
    def test_picks_highest_urgency_eligible(self):
        s = new_game("dingwei")
        c = next_from_pool(s)
        self.assertEqual(c.id, "shaanxi_unrest")   # urgency 80 > deficit 65

    def test_gate_blocks_ineligible(self):
        s = new_game("dingwei")
        s.event_pool = [{"id": "x", "title": "t", "brief": "b", "truth": "r",
                         "cast": [], "trigger_gate": {"国库": "<=5"}, "urgency": 99}]
        self.assertIsNone(next_from_pool(s))
        self.assertEqual(len(s.event_pool), 1)

    def test_removed_from_pool_after_pick(self):
        s = new_game("dingwei")
        self.assertEqual(len(s.event_pool), 2)
        next_from_pool(s)
        self.assertEqual(len(s.event_pool), 1)

    def test_empty_pool_returns_none(self):
        s = new_game("dingwei")
        s.event_pool = []
        self.assertIsNone(next_from_pool(s))


class TestFogCascade(unittest.TestCase):
    def test_fog_when_耳目_below_40(self):
        """废厂卫后耳目<40 × 陕西奏报 credibility=50 → brief 起迷雾。"""
        s = new_game("dingwei")
        s.active_crisis().resolved = True
        s.metrics["耳目"] = 30
        c = next_from_pool(s)
        self.assertEqual(c.id, "shaanxi_unrest")
        self.assertTrue(c.brief.startswith("【消息语焉不详"))

    def test_no_fog_when_耳目_normal(self):
        """留厂卫耳目正常 → 奏报如实呈现。"""
        s = new_game("dingwei")
        s.active_crisis().resolved = True
        s.metrics["耳目"] = 60
        c = next_from_pool(s)
        self.assertEqual(c.id, "shaanxi_unrest")
        self.assertFalse(c.brief.startswith("【消息语焉不详"))

    def test_full_dingwei_sequence(self):
        """定魏→陕西民变→户部亏空→池空：完整三刀全链。"""
        s = new_game("dingwei")
        s.active_crisis().resolved = True
        c1 = next_from_pool(s)
        s.crises.append(c1)
        self.assertEqual(s.active_crisis().id, "shaanxi_unrest")
        s.active_crisis().resolved = True
        c2 = next_from_pool(s)
        s.crises.append(c2)
        self.assertEqual(s.active_crisis().id, "deficit")
        s.active_crisis().resolved = True
        self.assertIsNone(next_from_pool(s))
        self.assertIsNone(s.active_crisis())

    def test_deficit_never_foggy(self):
        """户部亏空 credibility=70（非<70）→ 耳目再低也不起雾。"""
        s = new_game("dingwei")
        s.active_crisis().resolved = True
        s.metrics["耳目"] = 20
        next_from_pool(s)                 # shaanxi_unrest
        c = next_from_pool(s)             # deficit
        self.assertEqual(c.id, "deficit")
        self.assertFalse(c.brief.startswith("【消息语焉不详"))


class TestBackdrop(unittest.TestCase):
    def test_接棒危机_cast_backdrop_非空(self):
        """shaanxi_unrest 接棒后 cast 渲染出真实地区/军队/势力实况，非空串。"""
        s = new_game("dingwei")
        s.active_crisis().resolved = True
        c = next_from_pool(s)
        self.assertEqual(c.id, "shaanxi_unrest")
        bd = world.backdrop(c.cast)
        self.assertNotEqual(bd, "")
        self.assertIn("【天下实况", bd)
        for marker in ("〔地区〕陕西", "〔军队〕陕西边军", "〔势力〕流寇"):
            self.assertIn(marker, bd)

    def test_cast_uses_ids_not_names(self):
        """cast 用 id，不含人物/派系文字名称。"""
        s = new_game("dingwei")
        s.active_crisis().resolved = True
        c = next_from_pool(s)
        self.assertIn("shaanxi", c.cast)
        self.assertIn("shaanxi_army", c.cast)
        self.assertIn("bandits", c.cast)
        # 人物/派系名不在 cast 里
        for name in ("韩爌", "毕自严", "东林", "百姓"):
            self.assertNotIn(name, c.cast)


if __name__ == "__main__":
    unittest.main()
