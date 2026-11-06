import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_tmp = tempfile.TemporaryDirectory()
os.environ["TECHNICIAN_AI_DB"] = str(Path(_tmp.name) / "tech.db")

from fastapi.testclient import TestClient

from technician_ai import api, database as db
from technician_ai import diagnosis, machines, retrieval


class MachineDetectionTests(unittest.TestCase):
    def test_names_and_terms_from_real_sessions(self):
        cases = {
            "Line 3 labeling machine": "Labeling Machine",
            "How to solve if nameplate didn't pick": "Labeling Machine",
            "Ribbon holder unload randomly dropping ribbon holder": machines.SOLDERING,
            "The soldering machine belt was misaligned": machines.SOLDERING,
            "Busbar soldering head is cold": "Busbar Soldering Machine",
            "Hipot machine keeps disconnecting": "HiPot Tester",
            "铭牌机不吸": "Labeling Machine",
            "叠焊机报警": "Busbar Soldering Machine",
            "Labeling": "Labeling Machine",
            "Line 1 framer": "Framing Machine",
            "D step axis fault on the tape remover": "Tape Removal Machine",
            "L5 jbox glue machine": "Junction Box Gluing Machine",
            "Barcode not placed": "Labeling&EPE Placing Machine",
            "封边胶带机": "Edge Taping Machine",
            "On the vertical strapping machine": "Strapping Machine",
            "Panel isn't being picked up on curing line loader": "Curing Line Loader Machine",
            "一体化焊机": machines.SOLDERING,
        }
        for text, expected in cases.items():
            self.assertEqual(machines.detect(text), expected, text)

    def test_side_letter_identifies_soldering_on_units_02_to_06(self):
        for code in ("703b", "503B", "W2-703-B", "W1-205-A"):
            self.assertEqual(machines.detect(code), machines.SOLDERING, code)

    def test_ambiguous_codes_stay_unknown(self):
        # Unit 703 is also a laminator and a layup machine; 501B may be a glass loader.
        for code in ("703", "W2-703", "401", "501B", "Workshop 2 and line 6", "Yes"):
            self.assertIsNone(machines.detect(code), code)

    def test_word_inside_another_word_does_not_match(self):
        self.assertIsNone(machines.detect("keeps repeating the fault"))


class StallTests(unittest.TestCase):
    def setUp(self):
        self.session = {"stalled_turns": 2}
        self.history = [{"role": "assistant", "content": "Does the magnet click when it drops?"}]

    def test_progress_resets_the_count(self):
        diagnosis.record_progress(self.session, "Is the holder bent?", True, self.history)
        self.assertEqual(self.session["stalled_turns"], 0)

    def test_no_progress_adds_to_the_count(self):
        diagnosis.record_progress(self.session, "Is the holder bent?", False, self.history)
        self.assertEqual(self.session["stalled_turns"], 3)

    def test_no_information_reply_counts_as_stalled_even_if_agent_claims_progress(self):
        for reply in ("I don't know", "idk", "not sure", "不知道"):
            session = {"stalled_turns": 0}
            history = self.history + [{"role": "user", "content": reply}]
            diagnosis.record_progress(session, "Is the holder bent?", True, history)
            self.assertEqual(session["stalled_turns"], 1, reply)

    def test_plain_no_is_progress(self):
        history = self.history + [{"role": "user", "content": "No"}]
        diagnosis.record_progress(self.session, "Is the holder bent?", True, history)
        self.assertEqual(self.session["stalled_turns"], 0)

    def test_repeated_question_counts_as_stalled_even_if_agent_claims_progress(self):
        diagnosis.record_progress(self.session, "Does the magnet click when it drops", True, self.history)
        self.assertEqual(self.session["stalled_turns"], 3)


def decision(message="Is the holder bent?", progress=True, machine=None):
    return json.dumps({
        "identified_machine": machine,
        "reasoning": "x",
        "made_progress": progress,
        "action": "ask",
        "message": message,
        "resolution": None,
    })


class DiagnoseStepTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.insert_document("manual_chunk", "Ribbon holder magnets", None, {"manual_title": "Solder Ribbon Holder SOP"})

    def run_step(self, history, session, **kwargs):
        with mock.patch.object(retrieval, "EMBEDDINGS_ENABLED", False), \
                mock.patch.object(retrieval.llm_client, "chat", return_value=decision()) as chat, \
                mock.patch.object(retrieval.db, "search_by_keywords", wraps=db.search_by_keywords) as search:
            retrieval.diagnose_step(
                "Holder drops", history, session=session, machine_options=machines.names(), **kwargs
            )
        return chat.call_args.kwargs, search.call_args.args[0]

    def test_replies_join_the_search(self):
        session = diagnosis.new_session("Holder drops")
        history = [
            {"role": "assistant", "content": "Vacuum gauge?"},
            {"role": "user", "content": "It uses magnets"},
        ]
        _, query = self.run_step(history, session)
        self.assertIn("magnets", query)

    def test_machine_is_only_asked_once(self):
        session = diagnosis.new_session("Holder drops")
        first, _ = self.run_step([], session)
        self.assertIn("MACHINE FIRST", first["system"])
        self.assertTrue(session["machine_asked"])
        history = [
            {"role": "assistant", "content": "Which machine?"},
            {"role": "user", "content": "Not sure"},
        ]
        second, _ = self.run_step(history, session)
        self.assertNotIn("MACHINE FIRST", second["system"])
        self.assertIn("unknown, do not ask", second["user_message"])

    def test_stalled_session_stays_open_and_the_count_restarts(self):
        session = diagnosis.new_session("Holder drops")
        session["stalled_turns"] = 3
        history = [
            {"role": "assistant", "content": "Any noise?"},
            {"role": "user", "content": "No idea"},
        ]
        kwargs, _ = self.run_step(history, session, escalate=True)
        self.assertIn("[STALLED]", kwargs["system"])
        self.assertEqual(session["stalled_turns"], 0)
        self.assertEqual(session["state"], diagnosis.STATE_SYMPTOM_GATHERING)


class GuessedMachineTests(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def post(self, answer, identified):
        client = TestClient(api.app)
        turn = {
            "message": "Is the holder bent?", "is_resolved": False, "resolution": None,
            "identified_machine": identified,
        }
        with mock.patch.object(api.rag, "diagnose_step", return_value=dict(turn, identified_machine=None)):
            session_id = client.post("/api/diagnose", data={"question": "Holder drops"}).json()["session_id"]
        with mock.patch.object(api.rag, "diagnose_step", return_value=turn):
            return client.post("/api/diagnose/step", data={"session_id": session_id, "answer": answer}).json()

    def test_guess_after_not_sure_is_ignored(self):
        self.assertIsNone(self.post("not sure", machines.SOLDERING)["machine"])

    def test_agent_can_place_a_described_machine(self):
        self.assertEqual(self.post("The big one after the stack", "Laminator")["machine"], "Laminator")


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(_tmp.name) / "search.db"
        self.path.unlink(missing_ok=True)
        patcher = mock.patch.object(db, "DB_PATH", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        db.init_db()
        vec = [1.0] + [0.0] * (db.EMBED_DIM - 1)
        near = [0.99, 0.14] + [0.0] * (db.EMBED_DIM - 2)
        for i in range(6):
            db.insert_document("manual_chunk", f"record {i}", vec, {"manual_title": "eam_fault_worder (2)"})
        db.insert_document("manual_chunk", "other", near, {"manual_title": "Laminator Manual"})
        db.insert_document("manual_chunk", "holder", near, {"manual_title": "Solder Ribbon Holder SOP"})
        self.query = vec

    def test_fault_records_cannot_crowd_out_manuals(self):
        titles = [d["metadata"]["manual_title"] for d in db.search_similar(self.query, k=4, max_fault_records=2)]
        self.assertEqual(titles.count("eam_fault_worder (2)"), 2)
        self.assertIn("Solder Ribbon Holder SOP", titles)

    def test_machine_manuals_rank_first(self):
        top = db.search_similar(self.query, k=1, title_terms=("solder ribbon",))[0]
        self.assertEqual(top["metadata"]["manual_title"], "Solder Ribbon Holder SOP")

    def test_keyword_search_keeps_manuals_for_a_known_machine(self):
        found = db.search_by_keywords("holder", k=3, title_terms=("solder ribbon",))
        self.assertEqual([d["text"] for d in found], ["holder"])


if __name__ == "__main__":
    unittest.main()
