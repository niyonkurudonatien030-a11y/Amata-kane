import json
from unittest import mock

from tests.helpers import BaseCase, jpeg


class Fixture(BaseCase):
    def accepted_deal(self, with_driver=False):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer, litres=20)
        farmer.post(f"/api/transactions/{tx}/transport/self")
        farmer.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": self.photo(farmer, tx), "reading_sg": 1.03})
        farmer.post(f"/api/transactions/{tx}/arrived")
        buyer.post(f"/api/transactions/{tx}/quality", {"stage": "ARRIVAL", "evidence_id": self.photo(buyer, tx), "reading_sg": 1.03})
        r = buyer.post(f"/api/transactions/{tx}/decision", {"decision": "accept"})
        self.assertEqual(r.get_json()["status"], "ACCEPTED", r.get_json())
        return farmer, buyer, tx, r.get_json()["payments"][0]["id"]


class PaymentTests(Fixture):
    def test_rejected_payment_flags_both_and_opens_dispute_then_recovers(self):
        farmer, buyer, tx, pay = self.accepted_deal()
        buyer.post(f"/api/payments/{pay}/report", {"method_type": "momo_phone", "reference": "R1", "amount_rwf": 7000})
        r = farmer.post(f"/api/payments/{pay}/reject", {"reason": "Nothing arrived in my wallet"})
        self.assertEqual(r.status_code, 200, r.get_json())
        t = r.get_json()["transaction"]
        self.assertEqual((t["status"], t["payment_status"]), ("DISPUTED", "DISPUTED"))
        did = t["disputes"][0]["id"]
        # payments are frozen while disputed
        self.assertEqual(buyer.post(f"/api/payments/{pay}/report", {"method_type": "bank", "reference": "R2", "amount_rwf": 7000}).status_code, 409)
        # resolution needs a proposal accepted by the other side
        self.assertEqual(buyer.post(f"/api/disputes/{did}/resolve", {"outcome": "done"}).status_code, 409)
        self.assertEqual(buyer.post(f"/api/disputes/{did}/events", {"event_type": "PROPOSAL", "body": "I will pay by bank today"}).status_code, 200)
        ev_id = buyer.get(f"/api/disputes/{did}").get_json()["events"][-1]["event_id"]
        self.assertEqual(buyer.post(f"/api/disputes/{did}/proposals/{ev_id}/respond", {"accept": True}).status_code, 403)  # not own proposal
        self.assertEqual(farmer.post(f"/api/disputes/{did}/proposals/{ev_id}/respond", {"accept": True}).status_code, 200)
        r = farmer.post(f"/api/disputes/{did}/resolve", {"outcome": "Buyer pays 7000 RWF by bank transfer today"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["status"], "RESOLVED")
        t = self.tx(buyer, tx)
        self.assertEqual((t["status"], t["payment_status"]), ("ACCEPTED", "UNCONFIRMED"))
        buyer.post(f"/api/payments/{pay}/report", {"method_type": "bank", "reference": "R2", "amount_rwf": 7000})
        farmer.post(f"/api/payments/{pay}/confirm")
        self.assertEqual(self.tx(buyer, tx)["status"], "COMPLETED")

    def test_amount_mismatch_warning_and_rules(self):
        farmer, buyer, tx, pay = self.accepted_deal()
        r = buyer.post(f"/api/payments/{pay}/report", {"method_type": "momo_code", "reference": "R1", "amount_rwf": 5000})
        self.assertTrue(r.get_json()["amount_mismatch"])
        codes = [f["code"] for f in farmer.get(f"/api/transactions/{tx}/checks").get_json()["findings"]]
        self.assertIn("PAYMENT_AMOUNT_DIFFERS", codes)
        self.assertIn("PAYMENT_NO_PROOF", codes)

    def test_third_party_cannot_touch_payment(self):
        farmer, buyer, tx, pay = self.accepted_deal()
        other = self.user("buyer")
        self.assertEqual(other.post(f"/api/payments/{pay}/report", {"method_type": "bank", "reference": "x", "amount_rwf": 1}).status_code, 404)


class DisputeTests(Fixture):
    def test_open_comment_evidence_withdraw(self):
        farmer, buyer, tx, pay = self.accepted_deal()
        r = farmer.post(f"/api/transactions/{tx}/disputes", {"category": "price", "description": "Price was 350 not 340"})
        self.assertEqual(r.status_code, 201)
        did = r.get_json()["id"]
        self.assertEqual(farmer.post(f"/api/transactions/{tx}/disputes", {"category": "price", "description": "again"}).status_code, 409)
        ev = self.photo(buyer, tx, "other_document")
        d = buyer.post(f"/api/disputes/{did}/events", {"event_type": "EVIDENCE", "evidence_id": ev, "body": "Our chat"}).get_json()
        self.assertTrue(any(e["type"] == "EVIDENCE" for e in d["events"]))
        self.assertGreaterEqual(len(d["evidence"]), 3)  # both parties' evidence is visible to both
        self.assertEqual(buyer.post(f"/api/disputes/{did}/withdraw").status_code, 409)  # only the opener can withdraw
        self.assertEqual(farmer.post(f"/api/disputes/{did}/withdraw").status_code, 200)
        self.assertEqual(self.tx(buyer, tx)["status"], "ACCEPTED")
        self.assertEqual(len(farmer.get("/api/disputes").get_json()), 1)

    def test_outsider_blocked_and_events_immutable(self):
        farmer, buyer, tx, pay = self.accepted_deal()
        did = farmer.post(f"/api/transactions/{tx}/disputes", {"category": "other", "description": "Something"}).get_json()["id"]
        self.assertEqual(self.user("buyer").get(f"/api/disputes/{did}").status_code, 404)
        import sqlite3
        con = sqlite3.connect(str(self.tmp / "t.db"))
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("UPDATE dispute_events SET body='edited'")
        con.close()

    def test_coop_admin_can_observe_and_comment_only(self):
        farmer, buyer, tx, pay = self.accepted_deal()
        coop = self.user("coop_admin", cooperative_name="Nyabihu Coop")
        # member joins the cooperative via profile? (set directly) -> coop admin sees only member deals
        import sqlite3
        con = sqlite3.connect(str(self.tmp / "t.db"))
        con.execute("UPDATE users SET cooperative_id=(SELECT cooperative_id FROM users WHERE role='coop_admin') WHERE role='farmer'")
        con.commit()
        con.close()
        did = farmer.post(f"/api/transactions/{tx}/disputes", {"category": "other", "description": "x"}).get_json()["id"]
        self.assertEqual(coop.get(f"/api/transactions/{tx}").status_code, 200)
        self.assertEqual(coop.get(f"/api/transactions/{tx}").get_json()["actions"], [])
        self.assertEqual(coop.post(f"/api/disputes/{did}/events", {"event_type": "COMMENT", "body": "Let us meet at the MCC"}).status_code, 200)
        self.assertEqual(coop.post(f"/api/disputes/{did}/events", {"event_type": "PROPOSAL", "body": "x"}).status_code, 403)
        self.assertEqual(coop.post(f"/api/transactions/{tx}/confirm").status_code, 404)


GEMINI_IMAGE_REPLY = {"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps({
    "document_type": "lactometer_photo", "legible": True,
    "lactometer": {"reading_sg": 1.028, "temperature_c": 21, "confidence": "medium"},
    "receipt": {}, "visible_text": "28", "uncertainties": ["slight glare"], "notes": "A lactometer floating in milk."}) + "\n```"}]}}]}


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


class AiTests(Fixture):
    """Gemini is MOCKED here: these tests prove our wiring, safety rules and parsing, not Gemini's accuracy."""

    def setUp(self):
        super().setUp()
        self.app.config["GEMINI_API_KEY"] = "fake-key-for-tests"

    def test_unconfigured_returns_503_not_crash(self):
        self.app.config["GEMINI_API_KEY"] = ""
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        ev = self.photo(farmer, tx)
        r = farmer.post(f"/api/evidence/{ev}/analyze", {"language": "en"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["code"], "AI_UNAVAILABLE")
        s = farmer.post(f"/api/transactions/{tx}/ai-summary", {}).get_json()
        self.assertFalse(s["ai_available"])
        self.assertIsInstance(s["findings"], list)

    def test_extraction_is_a_suggestion_until_a_person_confirms(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        ev = self.photo(farmer, tx)
        with mock.patch("backend.ai.gemini_client.requests.post", return_value=FakeResp(GEMINI_IMAGE_REPLY)) as post:
            r = farmer.post(f"/api/evidence/{ev}/analyze", {"language": "rw"})
        self.assertEqual(r.status_code, 201, r.get_json())
        a = r.get_json()
        self.assertEqual(a["status"], "SUGGESTED")
        self.assertEqual(a["extracted"]["lactometer"]["reading_sg"], 1.028)
        self.assertIn("suggestion", a["disclaimer"].lower())
        call = post.call_args
        self.assertEqual(call.kwargs["headers"]["x-goog-api-key"], "fake-key-for-tests")   # key in header, server side only
        self.assertNotIn("fake-key", call.args[0])                                           # never in the URL
        self.assertIn("never state or imply that milk is safe", json.dumps(call.kwargs["json"]).lower())
        # nothing is treated as true until confirmed
        self.assertEqual(self.tx(farmer, tx)["ai"][0]["confirmed"], None)
        self.assertEqual(farmer.post(f"/api/ai/{a['id']}/confirm", {"values": {}}).status_code, 422)
        c = farmer.post(f"/api/ai/{a['id']}/confirm", {"values": {"reading_sg": "1.029", "evil_field": "x"}})
        self.assertEqual(c.status_code, 200, c.get_json())
        self.assertEqual(c.get_json()["confirmed"], {"reading_sg": 1.029})  # unknown fields dropped, number validated
        self.assertEqual(farmer.post(f"/api/ai/{a['id']}/reject").status_code, 409)  # already handled

    def test_reading_mismatch_between_ai_and_tester_is_flagged(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        farmer.post(f"/api/transactions/{tx}/transport/self")
        ev = self.photo(farmer, tx)
        farmer.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": ev, "reading_sg": 1.033})
        with mock.patch("backend.ai.gemini_client.requests.post", return_value=FakeResp(GEMINI_IMAGE_REPLY)):
            a = farmer.post(f"/api/evidence/{ev}/analyze", {}).get_json()
        farmer.post(f"/api/ai/{a['id']}/confirm", {"values": {"reading_sg": 1.028}})
        codes = [f["code"] for f in buyer.get(f"/api/transactions/{tx}/checks").get_json()["findings"]]
        self.assertIn("READING_MISMATCH", codes)

    def test_gemini_errors_are_handled(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        ev = self.photo(farmer, tx)
        with mock.patch("backend.ai.gemini_client.requests.post", return_value=FakeResp({}, 429)):
            r = farmer.post(f"/api/evidence/{ev}/analyze", {})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("fake-key", r.get_data(as_text=True))
        with mock.patch("backend.ai.gemini_client.requests.post", return_value=FakeResp({"candidates": []})):
            self.assertEqual(farmer.post(f"/api/evidence/{ev}/analyze", {}).status_code, 503)

    def test_summary_sends_no_names_or_phones(self):
        farmer, buyer = self.user("farmer", "Uniquename Farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        reply = {"candidates": [{"content": {"parts": [{"text": json.dumps({"summary": "Deal agreed.", "missing_information": []})}]}}]}
        with mock.patch("backend.ai.gemini_client.requests.post", return_value=FakeResp(reply)) as post:
            r = farmer.post(f"/api/transactions/{tx}/ai-summary", {"language": "rw"}).get_json()
        sent = json.dumps(post.call_args.kwargs["json"])
        self.assertNotIn("Uniquename", sent)
        self.assertNotIn(farmer.phone[1:], sent)
        self.assertIn("Kinyarwanda", sent)
        self.assertEqual(r["ai"]["summary"], "Deal agreed.")

    def test_outsider_cannot_analyse(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        ev = self.photo(farmer, tx)
        self.assertEqual(self.user("buyer").post(f"/api/evidence/{ev}/analyze", {}).status_code, 404)


class RulesAndSecurityTests(Fixture):
    def test_duplicate_file_flagged(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        farmer.upload(f"/api/transactions/{tx}/evidence", "delivery_photo", data=jpeg("same"))
        buyer.upload(f"/api/transactions/{tx}/evidence", "payment_receipt", data=jpeg("same"))
        codes = [f["code"] for f in farmer.get(f"/api/transactions/{tx}/checks").get_json()["findings"]]
        self.assertIn("DUPLICATE_FILE", codes)

    def test_security_headers_and_static_pages(self):
        a = self.user("farmer")
        r = a.get("/api/health")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(self.app.test_client().get("/").status_code, 200)

    def test_path_traversal_blocked(self):
        from backend.services.storage import resolve_path
        from backend.common import ApiError
        with self.assertRaises(ApiError):
            resolve_path(self.tmp / "evidence", "../../etc/passwd")

    def test_dashboard_for_each_role(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        driver, coop, admin = self.user("driver"), self.user("coop_admin"), self.make_admin()
        self.agreed_deal(farmer, buyer)
        for who in (farmer, buyer, driver, coop, admin):
            r = who.get("/api/dashboard")
            self.assertEqual(r.status_code, 200)
        self.assertEqual(farmer.get("/api/dashboard").get_json()["stats"]["pending_delivery"], 1)
        self.assertIn("open_jobs", driver.get("/api/dashboard").get_json()["driver"])
        self.assertIn("users", admin.get("/api/dashboard").get_json()["admin"])
        self.assertGreater(farmer.get("/api/dashboard").get_json()["unread_notifications"] + 1, 0)
