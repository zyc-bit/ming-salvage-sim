import os
import tempfile
import unittest

from ming_sim.models import LLMConfig
from ming_sim.session import GameSession


class LocationDispatchTests(unittest.TestCase):
    def make_session(self) -> GameSession:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return GameSession(
            path,
            LLMConfig(api_key="test", base_url="http://localhost/v1", model="dummy"),
            verify_llm=False,
        )

    def test_seed_backfills_character_locations(self) -> None:
        session = self.make_session()
        db = session.db
        try:
            rows = db.conn.execute(
                "SELECT name, location FROM characters WHERE power_id='ming' AND status='active'"
            ).fetchall()
            self.assertTrue(rows)
            self.assertTrue(all(row["location"] for row in rows))
            self.assertEqual(db.character_location("袁崇焕"), "guangdong")
            self.assertEqual(db.character_location("毕自严"), "nanzhili")
            self.assertEqual(db.character_location("张瑞图"), "beizhili")
        finally:
            session.close()

    def test_court_roster_only_includes_characters_at_court(self) -> None:
        session = self.make_session()
        try:
            names = {minister.name for minister in session.list_ministers()}
            self.assertIn("张瑞图", names)
            self.assertNotIn("袁崇焕", names)
            ok, reason = session.can_summon(session.content.characters["袁崇焕"])
            self.assertFalse(ok)
            self.assertIn("不能入殿召见", reason)
        finally:
            session.close()

    def test_letter_round_trip_uses_separate_outbound_and_inbound_turns(self) -> None:
        session = self.make_session()
        try:
            result = session.dispatch_letter("孙传庭", "问河南民情。", chat_message_id=1)
            self.assertEqual(result["outbound_days"], 2)
            self.assertEqual(result["return_days"], 2)
            self.assertEqual(result["arrival_turn"], session.state.turn + 2)
            self.assertEqual(result["earliest_reply_turn"], session.state.turn + 4)
        finally:
            session.close()

    def test_remote_secret_order_is_in_transit_until_delivery(self) -> None:
        session = self.make_session()
        db = session.db
        try:
            order_id = db.create_secret_order(session.state, "袁崇焕", "密查", "密查粤中人脉。", [], deadline_months=1)
            order = db.get_secret_order(order_id)
            self.assertEqual(order["status"], "in_transit")
            self.assertEqual(order["due_turn"], 0)
            session.state.turn += 5
            self.assertTrue(db.activate_secret_order_on_delivery(session.state, order_id))
            order = db.get_secret_order(order_id)
            self.assertEqual(order["status"], "active")
            self.assertEqual(order["due_turn"], session.state.turn + 30)
        finally:
            session.close()

    def test_office_changes_update_location(self) -> None:
        session = self.make_session()
        db = session.db
        try:
            db.set_character_office("洪承畴", "陕西巡抚", "地方", source="测试")
            self.assertEqual(db.character_location("洪承畴"), "shaanxi")
            db.set_character_office("洪承畴", "内阁大学士", "内阁", source="测试")
            self.assertEqual(db.character_location("洪承畴"), "beizhili")
        finally:
            session.close()

    def test_remote_decree_is_dispatched_not_applied_immediately(self) -> None:
        session = self.make_session()
        db = session.db
        try:
            db.add_directive(session.state, None, "命袁崇焕在广东密查海道。", "测试")
            session.last_decree = "命袁崇焕在广东密查海道。"
            report = session.resolve_turn()
            self.assertIn("诏书已发往", report)
            dispatches = db.list_dispatches(statuses=("in_transit",))
            self.assertEqual(len(dispatches), 1)
            self.assertEqual(dispatches[0]["kind"], "decree")
            self.assertEqual(dispatches[0]["destination_location"], "guangdong")
            row = db.conn.execute("SELECT COUNT(*) AS n FROM court_events WHERE source_kind='decree'").fetchone()
            self.assertEqual(int(row["n"]), 0)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
