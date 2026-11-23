from datetime import datetime, timedelta, timezone

from backend import common
from tests.helpers import BaseCase, jpeg


class MarketAndBookingTests(BaseCase):
    def test_listing_roles_and_filters(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver")
        self.assertEqual(driver.post("/api/listings", {"listing_type": "SELL", "litres": 10, "price_per_litre": 300, "location_name": "x"}).status_code, 403)
        self.assertEqual(buyer.post("/api/listings", {"listing_type": "SELL", "litres": 10, "price_per_litre": 300, "location_name": "x"}).status_code, 403)
        self.sell_listing(farmer, litres=50, price_per_litre=400, latitude=-1.70, longitude=29.45)
        self.sell_listing(farmer, litres=500, price_per_litre=300, latitude=-1.95, longitude=30.06)
        res = buyer.get("/api/listings?type=SELL&sort=price_asc").get_json()
        self.assertEqual([x["price_per_litre"] for x in res], [300, 400])
        self.assertEqual(len(buyer.get("/api/listings?min_litres=100").get_json()), 1)
        self.assertEqual(len(buyer.get("/api/listings?max_price=350").get_json()), 1)
        near = buyer.get("/api/listings?near_lat=-1.70&near_lng=29.45&sort=nearest").get_json()
        self.assertEqual(near[0]["price_per_litre"], 400)
        self.assertLess(near[0]["distance_km"], 1)
        self.assertEqual(len(buyer.get("/api/listings?near_lat=-1.70&near_lng=29.45&max_km=20").get_json()), 1)
        self.assertEqual(buyer.get("/api/listings?mine=1").get_json(), [])
        self.assertEqual(len(farmer.get("/api/listings?mine=1").get_json()), 2)

    def test_listing_validation(self):
        f = self.user("farmer")
        bad = {"listing_type": "SELL", "litres": -5, "price_per_litre": 300, "location_name": "x"}
        self.assertEqual(f.post("/api/listings", bad).status_code, 422)
        bad = {"listing_type": "SELL", "litres": 5, "price_per_litre": 300, "location_name": "x", "min_lactometer": 1.04, "max_lactometer": 1.03}
        self.assertEqual(f.post("/api/listings", bad).status_code, 422)

    def test_booking_requires_other_party_confirmation_and_records_both_timestamps(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        lst = self.sell_listing(farmer)
        r = buyer.post(f"/api/listings/{lst['id']}/book", {"litres": 40})
        tx = r.get_json()
        self.assertEqual(tx["status"], "REQUESTED")
        self.assertIsNotNone(tx["buyer_accepted_at"])
        self.assertIsNone(tx["seller_accepted_at"])
        self.assertEqual(tx["total_value"], 40 * 350)
        self.assertIn("confirm", self.tx(farmer, tx["id"])["actions"])
        self.assertNotIn("confirm", tx["actions"])  # the requester cannot confirm their own request
        self.assertEqual(buyer.post(f"/api/transactions/{tx['id']}/confirm").status_code, 409)
        done = farmer.post(f"/api/transactions/{tx['id']}/confirm").get_json()
        self.assertEqual(done["status"], "AGREED")
        self.assertIsNotNone(done["seller_accepted_at"])
        self.assertEqual(buyer.get(f"/api/listings/{lst['id']}").get_json()["litres_remaining"], 60)

    def test_booking_hold_expires_and_litres_return(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        lst = self.sell_listing(farmer, litres=100)
        tx = buyer.post(f"/api/listings/{lst['id']}/book", {"litres": 100}).get_json()["id"]
        self.assertEqual(buyer.get(f"/api/listings/{lst['id']}").get_json()["status"], "CLOSED")
        later = datetime.now(timezone.utc) + timedelta(seconds=61)
        common.set_clock(lambda: later)
        self.assertEqual(farmer.post(f"/api/transactions/{tx}/confirm").status_code, 409)
        self.assertEqual(self.tx(buyer, tx)["status"], "EXPIRED")
        lst2 = buyer.get(f"/api/listings/{lst['id']}").get_json()
        self.assertEqual((lst2["status"], lst2["litres_remaining"]), ("OPEN", 100))

    def test_cannot_overbook_or_book_own_or_wrong_role(self):
        farmer, buyer, farmer2 = self.user("farmer"), self.user("buyer"), self.user("farmer")
        lst = self.sell_listing(farmer, litres=50)
        self.assertEqual(buyer.post(f"/api/listings/{lst['id']}/book", {"litres": 51}).status_code, 409)
        self.assertEqual(farmer.post(f"/api/listings/{lst['id']}/book", {"litres": 5}).status_code, 409)
        self.assertEqual(farmer2.post(f"/api/listings/{lst['id']}/book", {"litres": 5}).status_code, 403)

    def test_buy_request_answered_by_farmer(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        r = buyer.post("/api/listings", {"listing_type": "BUY", "litres": 80, "price_per_litre": 360, "location_name": "Kigali plant"})
        tx = farmer.post(f"/api/listings/{r.get_json()['id']}/book", {"litres": 30}).get_json()
        self.assertEqual(tx["created_by_role"], "seller")
        self.assertEqual(buyer.post(f"/api/transactions/{tx['id']}/confirm").get_json()["status"], "AGREED")

    def test_decline_and_cancel_release_litres(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        lst = self.sell_listing(farmer, litres=60)
        t1 = buyer.post(f"/api/listings/{lst['id']}/book", {"litres": 20}).get_json()["id"]
        self.assertEqual(farmer.post(f"/api/transactions/{t1}/decline", {"reason": "sold"}).get_json()["status"], "DECLINED")
        t2 = buyer.post(f"/api/listings/{lst['id']}/book", {"litres": 20}).get_json()["id"]
        farmer.post(f"/api/transactions/{t2}/confirm")
        self.assertEqual(buyer.post(f"/api/transactions/{t2}/cancel", {"reason": "changed plan"}).get_json()["status"], "CANCELLED")
        self.assertEqual(buyer.get(f"/api/listings/{lst['id']}").get_json()["litres_remaining"], 60)

    def test_outsider_cannot_see_deal_or_evidence(self):
        farmer, buyer, other = self.user("farmer"), self.user("buyer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        ev = self.photo(farmer, tx, "delivery_photo")
        self.assertEqual(other.get(f"/api/transactions/{tx}").status_code, 404)
        self.assertEqual(other.get(f"/api/evidence/{ev}/file").status_code, 404)
        self.assertEqual(other.post(f"/api/transactions/{tx}/cancel").status_code, 404)
        self.assertEqual(self.tx(other, tx) if False else other.get("/api/transactions").get_json(), [])


class FullJourneyTests(BaseCase):
    def hire_driver(self, farmer, buyer, driver, tx, wage=2000):
        r = buyer.post(f"/api/transactions/{tx}/job", {"wage_rwf": wage, "contact_method": "whatsapp"})
        self.assertEqual(r.status_code, 201, r.get_json())
        job = r.get_json()["job"]["id"]
        self.assertEqual(driver.get("/api/jobs").get_json()[0]["id"], job)
        self.assertEqual(driver.post(f"/api/jobs/{job}/apply", {"proposed_wage_rwf": 2500, "message": "I have a motorcycle"}).status_code, 201)
        self.assertEqual(driver.post(f"/api/jobs/{job}/apply", {"proposed_wage_rwf": 2500}).status_code, 409)
        apps = self.tx(buyer, tx)["job"]["applications"]
        self.assertEqual(buyer.post(f"/api/jobs/{job}/select", {"application_id": apps[0]["application_id"]}).status_code, 200)
        self.assertEqual(driver.post(f"/api/jobs/{job}/accept").status_code, 200)
        return job

    def test_complete_happy_path_with_driver(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        tx = self.agreed_deal(farmer, buyer, litres=40)
        # a quality check before transport is arranged is refused
        ev0 = self.photo(farmer, tx)
        r = farmer.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": ev0, "reading_sg": 1.029})
        self.assertEqual(r.status_code, 409)
        job = self.hire_driver(farmer, buyer, driver, tx)
        # contact details are revealed to the accepted driver
        d = self.tx(driver, tx)
        self.assertTrue(d["seller"].get("phone"))
        self.assertEqual(d["job"]["agreed_wage_rwf"], 2500)
        # driver marks arrival, records a clear photo within range
        self.assertEqual(driver.post(f"/api/transactions/{tx}/driver-arrived").status_code, 200)
        ev1 = self.photo(driver, tx, "lactometer_photo")
        r = driver.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": ev1, "reading_sg": 1.029, "temperature_c": 22})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(r.get_json()["result"], "WITHIN_AGREED_RANGE")
        self.assertEqual(r.get_json()["transaction_status"], "IN_TRANSIT")
        self.assertEqual(driver.post(f"/api/transactions/{tx}/arrived").status_code, 200)
        # buyer cannot decide before recording an arrival check
        self.assertEqual(buyer.post(f"/api/transactions/{tx}/decision", {"decision": "accept"}).status_code, 409)
        ev2 = self.photo(buyer, tx, "lactometer_photo")
        r = buyer.post(f"/api/transactions/{tx}/quality", {"stage": "ARRIVAL", "evidence_id": ev2, "reading_sg": 1.03})
        self.assertEqual(r.status_code, 201, r.get_json())
        r = buyer.post(f"/api/transactions/{tx}/decision", {"decision": "accept", "accepted_litres": 38})
        self.assertEqual(r.status_code, 200, r.get_json())
        t = r.get_json()
        self.assertEqual((t["status"], t["accepted_litres"]), ("ACCEPTED", 38))
        milk = next(p for p in t["payments"] if p["purpose"] == "MILK")
        wage = next(p for p in t["payments"] if p["purpose"] == "TRANSPORT")
        self.assertEqual((milk["amount_due_rwf"], wage["amount_due_rwf"]), (38 * 350, 2500))
        self.assertEqual(t["payment_status"], "UNCONFIRMED")
        # farmer lists a payment method; buyer sees it, reports payment with a proof file
        farmer.post("/api/users/me/payment-methods", {"method_type": "momo_code", "label": "MoMo Pay", "account_value": "654321"})
        proof = self.photo(buyer, tx, "payment_receipt")
        r = buyer.post(f"/api/payments/{milk['id']}/report", {"method_type": "momo_code", "reference": "MP240001", "amount_rwf": 13300, "proof_evidence_id": proof})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["transaction"]["payment_status"], "PAYMENT_REPORTED")
        self.assertEqual(buyer.post(f"/api/payments/{milk['id']}/confirm").status_code, 409)  # payer cannot confirm own payment
        self.assertEqual(farmer.post(f"/api/payments/{milk['id']}/confirm").status_code, 200)
        t = self.tx(buyer, tx)
        self.assertEqual(t["payment_status"], "CONFIRMED_BY_BOTH")
        self.assertEqual(t["status"], "ACCEPTED")  # transport payment still open
        buyer.post(f"/api/payments/{wage['id']}/report", {"method_type": "momo_phone", "reference": "MP240002", "amount_rwf": 2500})
        self.assertEqual(driver.post(f"/api/payments/{wage['id']}/confirm").status_code, 200)
        self.assertEqual(self.tx(buyer, tx)["status"], "COMPLETED")
        stats = buyer.get("/api/dashboard").get_json()["stats"]
        self.assertEqual(stats["completed"], 1)
        # timeline is complete and the audit chain is intact
        actions = [e["action"] for e in self.tx(farmer, tx)["timeline"]]
        for a in ("TX_REQUESTED", "TX_CONFIRMED", "JOB_ACCEPTED", "QUALITY_RECORDED", "DELIVERY_RELEASED", "BUYER_ACCEPTED_DELIVERY",
                  "PAYMENT_CONFIRMED", "TX_COMPLETED"):
            self.assertIn(a, actions)
        self.assertTrue(self.make_admin().get("/api/admin/audit/verify").get_json()["ok"])

    def test_self_transport_and_out_of_range_needs_buyer_waiver(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        self.assertEqual(buyer.post(f"/api/transactions/{tx}/transport/self").status_code, 200)
        ev = self.photo(buyer, tx, "lactometer_photo")
        # buyer is the carrier but only seller/carrier may record pickup: buyer-as-carrier is allowed
        r = buyer.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": ev, "reading_sg": 1.020})
        self.assertEqual(r.get_json()["result"], "OUTSIDE_AGREED_RANGE")
        self.assertEqual(self.tx(buyer, tx)["status"], "AGREED")
        self.assertIn("waive_quality", self.tx(buyer, tx)["actions"])
        self.assertEqual(farmer.post(f"/api/transactions/{tx}/quality/waive", {"note": "ok"}).status_code, 403)
        self.assertEqual(buyer.post(f"/api/transactions/{tx}/quality/waive", {"note": "I accept this milk"}).status_code, 200)
        self.assertEqual(self.tx(buyer, tx)["status"], "IN_TRANSIT")

    def test_unclear_photo_requires_redo_and_does_not_release(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        farmer.post(f"/api/transactions/{tx}/transport/self")
        ev = self.photo(farmer, tx)
        r = farmer.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": ev, "photo_legible": False})
        self.assertEqual(r.get_json()["result"], "REDO_REQUIRED")
        self.assertEqual(self.tx(farmer, tx)["status"], "AGREED")
        ev2 = self.photo(farmer, tx)
        r = farmer.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": ev2, "reading_sg": 1.030})
        self.assertEqual(r.get_json()["transaction_status"], "IN_TRANSIT")

    def test_no_agreed_range_still_releases_but_says_so(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        lst = farmer.post("/api/listings", {"listing_type": "SELL", "litres": 20, "price_per_litre": 300, "location_name": "x"}).get_json()
        tx = buyer.post(f"/api/listings/{lst['id']}/book", {"litres": 10}).get_json()["id"]
        farmer.post(f"/api/transactions/{tx}/confirm")
        farmer.post(f"/api/transactions/{tx}/transport/self")
        ev = self.photo(farmer, tx)
        r = farmer.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": ev, "reading_sg": 1.03}).get_json()
        self.assertEqual(r["result"], "NO_AGREED_RANGE")

    def test_buyer_rejection_opens_dispute(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        farmer.post(f"/api/transactions/{tx}/transport/self")
        farmer.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": self.photo(farmer, tx), "reading_sg": 1.03})
        farmer.post(f"/api/transactions/{tx}/arrived")
        buyer.post(f"/api/transactions/{tx}/quality", {"stage": "ARRIVAL", "evidence_id": self.photo(buyer, tx), "reading_sg": 1.02})
        self.assertEqual(buyer.post(f"/api/transactions/{tx}/decision", {"decision": "reject"}).status_code, 422)
        r = buyer.post(f"/api/transactions/{tx}/decision", {"decision": "reject", "reason": "Smells sour and reading is low", "category": "quality"})
        self.assertEqual(r.get_json()["status"], "DISPUTED")
        self.assertEqual(len(r.get_json()["disputes"]), 1)


class EvidenceTests(BaseCase):
    def test_upload_metadata_hash_and_original_preserved(self):
        import hashlib
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        data = jpeg("original-bytes")
        r = farmer.upload(f"/api/transactions/{tx}/evidence", "delivery_photo", data=data, note="Milk cans", latitude="-1.7", longitude="29.4")
        self.assertEqual(r.status_code, 201, r.get_json())
        ev = r.get_json()["transaction"]["evidence"][0]
        self.assertEqual(ev["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual((ev["note"], ev["mime_type"]), ("Milk cans", "image/jpeg"))
        served = buyer.get(ev["url"])  # the other party can see it
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.data, data)
        self.assertEqual(served.headers["X-Content-Type-Options"], "nosniff")

    def test_rejects_fake_and_oversized_files(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        r = farmer.upload(f"/api/transactions/{tx}/evidence", "other_document", data=b"<script>alert(1)</script>", filename="x.jpg")
        self.assertEqual(r.status_code, 415)
        r = farmer.upload(f"/api/transactions/{tx}/evidence", "nonsense", data=jpeg())
        self.assertEqual(r.status_code, 422)
        big = jpeg() + b"0" * (9 * 1024 * 1024)
        self.assertEqual(farmer.upload(f"/api/transactions/{tx}/evidence", "other_document", data=big).status_code, 413)

    def test_evidence_is_immutable_in_database(self):
        import sqlite3
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.agreed_deal(farmer, buyer)
        self.photo(farmer, tx, "delivery_photo")
        con = sqlite3.connect(str(self.tmp / "t.db"))
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("UPDATE evidence SET note='tampered'")
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("DELETE FROM evidence")
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("DELETE FROM audit_log")
        con.close()

    def test_audit_chain_detects_tampering(self):
        import sqlite3
        farmer, buyer = self.user("farmer"), self.user("buyer")
        self.agreed_deal(farmer, buyer)
        admin = self.make_admin()
        self.assertTrue(admin.get("/api/admin/audit/verify").get_json()["ok"])
        con = sqlite3.connect(str(self.tmp / "t.db"))
        con.execute("DROP TRIGGER audit_no_update")  # an attacker with raw database access
        con.execute("UPDATE audit_log SET details_json='{\"litres\":1}' WHERE action='TX_REQUESTED'")
        con.commit()
        con.close()
        self.assertFalse(admin.get("/api/admin/audit/verify").get_json()["ok"])
