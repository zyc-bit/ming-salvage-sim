"""只读世界盘面(regions/armies/powers)loader + 危机 cast 背景注入测试。

从仓库根运行:  .venv/bin/python -m unittest v2.test_world_backdrop
"""
import unittest

from . import world
from .content import new_game


class TestLoaders(unittest.TestCase):
    def test_projections_are_minimal(self):
        # set 精确相等即证明:只取约定字段、重字段(fiscal/theater/last_action…)全丢弃
        ld = world.load_regions()["liaodong"]
        self.assertEqual(set(ld), {"name", "kind", "public_support", "unrest", "disaster"})
        self.assertEqual(ld["public_support"], 28)
        self.assertIn("辽民流离", ld["disaster"])              # 天灾+人祸已合并为一项
        gn = world.load_armies()["guanning"]
        self.assertEqual(set(gn), {"name", "station", "commander", "morale", "arrears", "loyalty"})
        self.assertEqual((gn["commander"], gn["arrears"]), ("袁崇焕", 60))
        hj = world.load_powers()["houjin"]
        self.assertEqual(set(hj), {"name", "leader", "stance", "agenda"})
        self.assertEqual(hj["leader"], "皇太极")


class TestBackdrop(unittest.TestCase):
    def test_empty_or_none_is_silent(self):
        self.assertEqual(world.backdrop([]), "")
        self.assertEqual(world.backdrop(None), "")

    def test_resolves_three_types_by_id_and_name(self):
        out = world.backdrop(["guanning", "liaodong", "houjin"])
        self.assertIn("【天下实况(只读背景)】", out)
        for s in ("〔军队〕关宁军", "〔地区〕辽东", "〔势力〕后金"):
            self.assertIn(s, out)
        self.assertIn("首领皇太极", world.backdrop(["后金"]))   # 用 name 而非 id 也能命中

    def test_unknown_key_skipped_good_kept(self):
        self.assertEqual(world.backdrop(["查无此地"]), "")
        self.assertIn("关宁军", world.backdrop(["查无此地", "guanning"]))


class TestCastWiring(unittest.TestCase):
    def test_liaodong_has_cast_dingwei_unchanged(self):
        self.assertEqual(new_game("liaodong").crises[0].cast, ["guanning", "liaodong", "houjin"])
        dw = new_game("dingwei").crises[0]
        self.assertEqual(dw.cast, [])
        self.assertEqual(world.backdrop(dw.cast), "")          # 无 cast 危机不追加任何事实


if __name__ == "__main__":
    unittest.main()
