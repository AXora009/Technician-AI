import asyncio
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

_tmp = tempfile.TemporaryDirectory()
os.environ["TECHNICIAN_AI_DB"] = str(Path(_tmp.name) / "tech.db")

from fastapi.testclient import TestClient

from technician_ai import api, database as db
from technician_ai import diagnosis, machines, retrieval, safety


class UploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_does_not_block_other_requests(self):
        started = threading.Event()
        release = threading.Event()

        def slow_ingest(_):
            started.set()
            release.wait(5)
            return 1

        upload = mock.Mock(filename="manual.pdf")
        upload.read = mock.AsyncMock(return_value=b"%PDF")
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(api, "MANUALS_DIR", Path(folder)), \
                mock.patch.object(api.ingest, "ingest_file", slow_ingest):
            task = asyncio.create_task(api.api_ingest(upload))
            await asyncio.to_thread(started.wait, 5)
            self.assertFalse(task.done())  # this line runs only if the loop is free
            release.set()
            await task


class CodeSearchTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(_tmp.name) / "codes.db"
        self.path.unlink(missing_ok=True)
        patcher = mock.patch.object(db, "DB_PATH", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        db.init_db()
        db.insert_document("manual_chunk", "A.710 Instantaneous Overload", None, {"manual_title": "Yaskawa"})
        db.insert_document("manual_chunk", "A.7100 is a part number", None, {"manual_title": "Other"})
        db.insert_document("manual_chunk", "alarm A710 cleared", None, {"manual_title": "eam_fault_worder (2)"})

    def found(self, text):
        return [d["text"] for d in db.search_exact_codes(retrieval.code_patterns(text))]

    def test_code_matches_with_or_without_the_dot(self):
        for text in ("A.710", "a710", "Servo code a710", "安川故障 710 怎么解决"):
            self.assertEqual(self.found(text)[0], "A.710 Instantaneous Overload", text)

    def test_manuals_rank_before_fault_records(self):
        self.assertEqual(self.found("A710"), ["A.710 Instantaneous Overload", "alarm A710 cleared"])

    def test_alarm_text_ranks_before_a_circuit_label(self):
        for _ in range(3):
            db.insert_document("manual_chunk", "A710 A710 A710 terminal block", None, {"manual_title": "Circuit Diagram"})
        self.assertEqual(self.found("A710")[0], "A.710 Instantaneous Overload")

    def test_longer_code_does_not_match(self):
        self.assertNotIn("A.7100 is a part number", self.found("A710"))

    def test_finds_all_real_code_shapes(self):
        for text in ("AE50", "A.b33", "E120", "AC90", "Fault code 9025"):
            self.assertTrue(retrieval.code_patterns(text), text)

    def test_ordinary_words_and_equipment_codes_are_not_codes(self):
        for text in ("W2-703", "703b", "Line 7A", "the bead face", "M96 tester", "L4 401", "0.5 MPa"):
            self.assertEqual(retrieval.code_patterns(text), [], text)

    def test_exact_hits_lead_the_results(self):
        similar = [{"id": 99, "kind": "manual_chunk", "text": "x", "metadata": {}, "score": 1}]
        merged = retrieval._add_exact_matches("A710", similar)
        self.assertEqual(merged[0]["text"], "A.710 Instantaneous Overload")
        self.assertEqual(merged[-1]["id"], 99)


class UnclearReplyTests(unittest.TestCase):
    choice = "Are the cuts off-center, or are they ragged?"

    def test_bare_yes_to_a_choice_is_unclear(self):
        for reply in ("Yes", "yes.", "有", "是的"):
            self.assertTrue(diagnosis.is_unclear_reply(reply, self.choice), reply)

    def test_no_to_a_choice_still_rules_it_out(self):
        self.assertFalse(diagnosis.is_unclear_reply("No", self.choice))

    def test_yes_to_a_plain_question_is_clear(self):
        self.assertFalse(diagnosis.is_unclear_reply("Yes", "Is the belt moving?"))

    def test_naming_the_option_is_clear(self):
        self.assertFalse(diagnosis.is_unclear_reply("Ragged", self.choice))

    def test_repeating_the_question_is_unclear(self):
        self.assertTrue(diagnosis.is_unclear_reply("焊点位置是否表现出明显的偏移", "请问焊点位置是否表现出明显的偏移？"))

    def test_only_unclear_yes_replies_cannot_earn_high_confidence(self):
        session = diagnosis.new_session("Cutting strings wrong")
        for _ in range(4):
            session = diagnosis.advance_state(session, "Next?", "Yes", self.choice)
        self.assertFalse(session["has_confirmed_evidence"])
        self.assertFalse(diagnosis.high_confidence_warranted(session))

    def test_unclear_reply_counts_as_stalled(self):
        session = {"stalled_turns": 0}
        history = [{"role": "assistant", "content": self.choice}, {"role": "user", "content": "Yes"}]
        diagnosis.record_progress(session, "Is the blade bent?", True, history)
        self.assertEqual(session["stalled_turns"], 1)


class SafetyHoldTests(unittest.TestCase):
    hazard = "pneumatic_hazard"

    def setUp(self):
        self.items = safety.init_prerequisites(self.hazard)

    def reply(self, text, listed=True):
        safety.update_prerequisites(self.hazard, self.items, text, items_were_listed=listed)

    def met(self):
        return safety.all_prerequisites_met(self.hazard, self.items)

    def test_turning_the_air_on_is_not_a_hazard(self):
        for text in ("Help me turn the air on for the edge trimmer", "Need a repair on the belt"):
            self.assertIsNone(safety.classify_safety_critical(text), text)

    def test_real_pneumatic_movement_still_triggers(self):
        self.assertEqual(safety.classify_safety_critical("The cylinder fired and the arm moved suddenly"), self.hazard)

    def test_confirmed_covers_the_list_but_not_injury(self):
        self.reply("confirmed")
        self.assertFalse(self.met())
        self.assertEqual([p["id"] for p in safety.get_unmet_prerequisites(self.hazard, self.items)], ["no_injury"])

    def test_no_clears_injury_once_it_is_the_last_question(self):
        self.reply("confirmed")
        self.reply("No")
        self.assertTrue(self.met())

    def test_yes_to_the_injury_question_stays_held(self):
        self.reply("confirmed")
        self.reply("yes")
        self.assertFalse(self.met())

    def test_no_does_not_clear_injury_while_other_items_are_open(self):
        self.reply("no")
        self.assertFalse(self.items["no_injury"])

    def test_confirmed_before_the_list_was_shown_does_nothing(self):
        self.reply("confirmed", listed=False)
        self.assertFalse(any(self.items.values()))

    def test_negated_confirmation_does_nothing(self):
        for text in ("confirmed not stopped", "I can't confirm", "还没确认"):
            self.reply(text)
            self.assertFalse(any(self.items.values()), text)

    def test_chinese_confirmation(self):
        self.reply("已确认")
        self.reply("没有")
        self.assertTrue(self.met())

    def test_spelled_out_reply_still_works_at_once(self):
        self.reply("no one is hurt, e-stop pressed, air locked out, everyone clear", listed=False)
        self.assertTrue(self.met())


class SafetyHoldFlowTests(unittest.TestCase):
    def step(self, session, replies):
        history = [{"role": "assistant", "content": "Safety alert"}]
        for text in replies:
            history.append({"role": "user", "content": text})
        with mock.patch.object(retrieval, "EMBEDDINGS_ENABLED", False):
            return retrieval.diagnose_step("The arm moved suddenly", history, session=session)

    def test_confirmation_only_counts_after_the_list_is_shown(self):
        session = diagnosis.new_session("The arm moved suddenly", True, "pneumatic_hazard")
        first = self.step(session, ["confirmed"])
        self.assertEqual(first["phase"], "safety_hold")
        self.assertFalse(session["prerequisites"]["estop_engaged"])
        self.assertTrue(session["safety_items_listed"])
        second = self.step(session, ["confirmed", "confirmed"])
        self.assertEqual(second["phase"], "safety_hold")
        self.assertTrue(session["prerequisites"]["air_isolated"])
        self.assertIn("injured", second["message"])
        self.assertNotIn("Emergency Stop", second["message"])


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
        for code in ("703b", "503B", "W2-703-B", "W1-205-A", "501B", "Line 7A", "L7a"):
            self.assertEqual(machines.detect(code), machines.SOLDERING, code)

    def test_ambiguous_codes_stay_unknown(self):
        # Unit 703 is also a laminator and a layup machine; 501B may be a glass loader.
        for code in ("703", "W2-703", "401", "L4", "703c", "707b", "Workshop 2 and line 6", "Yes"):
            self.assertIsNone(machines.detect(code), code)

    def test_number_in_front_of_a_name_is_ignored(self):
        cases = {
            "401 framing machine": "Framing Machine",
            "401Hi-pot 测试不扫码": "HiPot Tester",
            "401装框机玻璃溢胶": "Framing Machine",
            "W1-401-Labeling Machine": "Labeling Machine",
            "703 laminator": "Laminator",
            "101焊机串焊机": machines.SOLDERING,
        }
        for text, expected in cases.items():
            self.assertEqual(machines.detect(text), expected, text)

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
