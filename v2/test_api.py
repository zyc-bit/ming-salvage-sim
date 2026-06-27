"""验证 advance 端点的 Phase-2 危机续接逻辑与白名单安全。

从仓库根运行:  .venv/bin/python -m unittest v2.test_api
全量 discover:  .venv/bin/python -m unittest discover -t . -s v2 -p 'test_*.py'
"""
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import v2.api as _api_mod
from v2.api import app

_FAKE_RESOLVED   = {"narrative": "推演完毕", "resolved": True,  "effects": []}
_FAKE_UNRESOLVED = {"narrative": "暂无定论", "resolved": False, "effects": []}


class _ApiBase(unittest.TestCase):
    """公共 setUp/tearDown:每条测试重置服务器全局状态。"""

    def setUp(self):
        _api_mod._state        = None
        _api_mod._summon_log   = []
        _api_mod._month_decree = None
        _api_mod._history      = {}
        self.client = TestClient(app)

    def tearDown(self):
        _api_mod._state        = None
        _api_mod._summon_log   = []
        _api_mod._month_decree = None
        _api_mod._history      = {}

    def _new_game(self, slice_id="dingwei"):
        r = self.client.post("/api/v2/game/new", json={"slice_id": slice_id})
        self.assertEqual(r.status_code, 200)
        return r.json()

    def _advance(self, resolved: bool):
        fake = _FAKE_RESOLVED if resolved else _FAKE_UNRESOLVED
        with patch("v2.llm.adjudicate", return_value=fake):
            r = self.client.post("/api/v2/game/advance")
        self.assertEqual(r.status_code, 200)
        return r.json()


class TestAdvanceChaining(_ApiBase):
    def test_chains_crises_in_urgency_order(self):
        """处置完定魏后依 urgency 续接:陕西民变(80)→户部亏空(65)→None。"""
        s = self._new_game()
        self.assertEqual(s["active_crisis"]["title"], "如何处置魏忠贤")

        body = self._advance(resolved=True)
        self.assertTrue(body["resolved"])
        self.assertIsNotNone(body["state"]["active_crisis"],
                             "解决定魏后应续接下一个危机,而非 None")
        self.assertEqual(body["state"]["active_crisis"]["title"], "陕西民变苗头")

        body = self._advance(resolved=True)
        self.assertEqual(body["state"]["active_crisis"]["title"], "户部亏空")

        body = self._advance(resolved=True)
        self.assertIsNone(body["state"]["active_crisis"],
                          "池空后 active_crisis 应为 None")

    def test_unresolved_does_not_advance_to_next(self):
        """resolved=False 时不续接,当前危机保持。"""
        self._new_game()
        body = self._advance(resolved=False)
        self.assertFalse(body["resolved"])
        self.assertEqual(body["state"]["active_crisis"]["title"], "如何处置魏忠贤")

    def test_month_increments(self):
        """每次 advance 月份 +1。"""
        s = self._new_game()
        start_month = s["month"]
        body = self._advance(resolved=False)
        self.assertEqual(body["state"]["month"], start_month + 1)


class TestWhitelist(_ApiBase):
    _FORBIDDEN = ("secret", "truth", "adjudicator_notes", "cast", "event_pool", "persona")

    def test_new_game_payload_no_hidden_fields(self):
        """POST /new 返回的 StatePayload 不含任何隐藏字段。"""
        r = self.client.post("/api/v2/game/new", json={"slice_id": "dingwei"})
        payload_str = r.text
        for kw in self._FORBIDDEN:
            self.assertNotIn(f'"{kw}"', payload_str,
                             f"白名单泄露: '{kw}' 出现在 new_game StatePayload")

    def test_advance_nested_state_no_hidden_fields(self):
        """advance 返回的嵌套 state 同样不含隐藏字段。"""
        self._new_game()
        body = self._advance(resolved=True)
        state_str = json.dumps(body["state"], ensure_ascii=False)
        for kw in self._FORBIDDEN:
            self.assertNotIn(f'"{kw}"', state_str,
                             f"advance.state 白名单泄露: '{kw}'")


if __name__ == "__main__":
    unittest.main()
