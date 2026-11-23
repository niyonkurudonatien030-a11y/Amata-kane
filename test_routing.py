"""Google Maps timing: Google is MOCKED here (no key or internet in the build environment).
These tests prove our request shape, fallbacks, caching, per-driver pace learning and deadline checks."""
from datetime import datetime, timedelta, timezone
from unittest import mock

from backend import common
from tests.helpers import BaseCase

PICK = (-1.6500, 29.5000)
DROP = (-1.7000, 29.5500)          # about 7-8 km away


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


def google(seconds=1200, metres=9000):
    return FakeResp({"routes": [{"duration": f"{seconds}s", "distanceMeters": metres}]})


class RoutingBase(BaseCase):
    def setUp(self):
        super().setUp()
        self.base = datetime.now(timezone.utc)
        self.offset = timedelta()
        common.set_clock(lambda: self.base + self.offset)

    def advance(self, minutes):
        self.offset += timedelta(minutes=minutes)

    def setup_deal(self, farmer, buyer, max_transit=60, drop=True):
        lst = self.sell_listing(farmer, latitude=PICK[0], longitude=PICK[1], max_transit_minutes=max_transit)
        if drop:
            buyer.patch("/api/users/me", {"latitude": DROP[0], "longitude": DROP[1], "business_name": "Test Dairy"})
        tx = buyer.post(f"/api/listings/{lst['id']}/book", {"litres": 20}).get_json()["id"]
        farmer.post(f"/api/transactions/{tx}/confirm")
        return tx

    def hire(self, buyer, driver, tx):
        job = buyer.post(f"/api/transactions/{tx}/job", {"wage_rwf": 1500}).get_json()["job"]["id"]
        driver.post(f"/api/jobs/{job}/apply", {"proposed_wage_rwf": 1500})
        app_id = self.tx(buyer, tx)["job"]["applications"][0]["application_id"]
        buyer.post(f"/api/jobs/{job}/select", {"application_id": app_id})
        driver.post(f"/api/jobs/{job}/accept")
        driver.post(f"/api/transactions/{tx}/driver-arrived")

    def pickup(self, driver, tx):
        ev = self.photo(driver, tx)
        r = driver.post(f"/api/transactions/{tx}/quality", {"stage": "PICKUP", "evidence_id": ev, "reading_sg": 1.03})
        self.assertEqual(r.get_json()["transaction_status"], "IN_TRANSIT", r.get_json())


class EtaTests(RoutingBase):
    def test_places_copied_from_listing_and_buyer_profile(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.tx(farmer, self.setup_deal(farmer, buyer))
        self.assertEqual((tx["trip"]["pickup"]["latitude"], tx["trip"]["dropoff"]["latitude"]), (PICK[0], DROP[0]))
        self.assertEqual(tx["trip"]["max_transit_minutes"], 60)

    def test_google_request_shape_and_motorcycle_mode(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        self.app.config["GOOGLE_MAPS_API_KEY"] = "maps-key-for-tests"
        tx = self.setup_deal(farmer, buyer)
        self.hire(buyer, driver, tx)
        with mock.patch("backend.services.routing.requests.post", return_value=google(1500, 9000)) as post:
            r = driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]})
        e = r.get_json()
        self.assertEqual((r.status_code, e["source"], e["maps_minutes"], e["personal_minutes"], e["distance_km"]), (201, "google", 25, 25, 9.0))
        self.assertEqual(e["travel_mode"], "TWO_WHEELER")
        call = post.call_args
        self.assertEqual(call.kwargs["headers"]["X-Goog-Api-Key"], "maps-key-for-tests")
        self.assertNotIn("maps-key", call.args[0])
        body = call.kwargs["json"]
        self.assertEqual((body["travelMode"], body["routingPreference"]), ("TWO_WHEELER", "TRAFFIC_AWARE"))
        self.assertEqual(body["destination"]["location"]["latLng"]["latitude"], DROP[0])

    def test_bicycle_has_no_traffic_preference(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="bicycle")
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        tx = self.setup_deal(farmer, buyer)
        self.hire(buyer, driver, tx)
        with mock.patch("backend.services.routing.requests.post", return_value=google(2400, 9000)) as post:
            driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]})
        self.assertNotIn("routingPreference", post.call_args.kwargs["json"])
        self.assertEqual(post.call_args.kwargs["json"]["travelMode"], "BICYCLE")

    def test_two_wheeler_falls_back_to_drive_then_to_rough_estimate(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        tx = self.setup_deal(farmer, buyer)
        self.hire(buyer, driver, tx)
        with mock.patch("backend.services.routing.requests.post", side_effect=[FakeResp({}, 400), google(1000, 8000)]) as post:
            e = driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]}).get_json()
        self.assertEqual((e["source"], e["travel_mode"], post.call_count), ("google", "DRIVE", 2))
        self.advance(10)  # leave the 5-minute cache
        with mock.patch("backend.services.routing.requests.post", return_value=FakeResp({}, 403)):
            e = driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]}).get_json()
        self.assertEqual(e["source"], "estimate")
        self.assertIn("Rough estimate", e["label"])

    def test_no_key_uses_clearly_labelled_estimate(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        tx = self.setup_deal(farmer, buyer)
        self.hire(buyer, driver, tx)
        with mock.patch("backend.services.routing.requests.post") as post:
            e = driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]}).get_json()
        post.assert_not_called()
        self.assertEqual(e["source"], "estimate")
        self.assertGreater(e["personal_minutes"], 5)
        self.assertLess(e["personal_minutes"], 60)

    def test_cache_saves_repeat_calls_for_five_minutes(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver")
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        tx = self.setup_deal(farmer, buyer)
        self.hire(buyer, driver, tx)
        body = {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]}
        with mock.patch("backend.services.routing.requests.post", return_value=google()) as post:
            driver.post(f"/api/transactions/{tx}/eta", body)
            r = driver.post(f"/api/transactions/{tx}/eta", body)
            self.assertTrue(r.get_json()["cached"])
            self.assertEqual(post.call_count, 1)
            self.advance(6)
            driver.post(f"/api/transactions/{tx}/eta", body)
            self.assertEqual(post.call_count, 2)

    def test_validation_and_access(self):
        farmer, buyer, driver, other = self.user("farmer"), self.user("buyer"), self.user("driver"), self.user("buyer")
        lst = self.sell_listing(farmer, latitude=PICK[0], longitude=PICK[1])
        tx = buyer.post(f"/api/listings/{lst['id']}/book", {"litres": 5}).get_json()["id"]
        self.assertEqual(buyer.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF"}).status_code, 409)   # not agreed yet
        farmer.post(f"/api/transactions/{tx}/confirm")
        self.assertEqual(buyer.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF"}).status_code, 422)   # buyer has no GPS drop-off
        self.assertEqual(buyer.post(f"/api/transactions/{tx}/eta", {"leg": "TO_PICKUP"}).status_code, 422)    # needs my location
        self.assertEqual(buyer.post(f"/api/transactions/{tx}/eta", {"leg": "BAD"}).status_code, 422)
        self.assertEqual(other.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF"}).status_code, 404)

    def test_buyer_sets_dropoff_seller_cannot(self):
        farmer, buyer = self.user("farmer"), self.user("buyer")
        tx = self.setup_deal(farmer, buyer, drop=False)
        self.assertIsNone(self.tx(buyer, tx)["trip"]["dropoff"]["latitude"])
        put = lambda who, **b: who.put(f"/api/transactions/{tx}/dropoff", b)
        self.assertEqual(put(farmer, latitude=-1.7, longitude=29.5).status_code, 409)
        r = put(buyer, name="Plant gate", latitude=-1.7, longitude=29.55)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["trip"]["dropoff"]["name"], "Plant gate")
        self.assertIn("DROPOFF_SET", [e["action"] for e in r.get_json()["timeline"]])


class PaceLearningAndDeadlineTests(RoutingBase):
    def run_trip(self, farmer, buyer, driver, actual_minutes, maps_seconds=1200, max_transit=60):
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        tx = self.setup_deal(farmer, buyer, max_transit=max_transit)
        self.hire(buyer, driver, tx)
        with mock.patch("backend.services.routing.requests.post", return_value=google(maps_seconds, 9000)):
            driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]})
        self.pickup(driver, tx)
        self.advance(actual_minutes)
        self.assertEqual(driver.post(f"/api/transactions/{tx}/arrived").status_code, 200)
        return tx

    def test_personal_pace_is_learned_after_three_trips(self):
        """Maps says 20 min but this rider needs 25 every time: after 3 trips the app predicts 25."""
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        for _ in range(3):
            self.run_trip(farmer, buyer, driver, actual_minutes=25)
            self.advance(10)
        tx = self.setup_deal(farmer, buyer)
        self.hire(buyer, driver, tx)
        with mock.patch("backend.services.routing.requests.post", return_value=google(1200, 9000)):
            e = driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]}).get_json()
        self.assertEqual((e["maps_minutes"], e["personal_factor"], e["personal_minutes"], e["trips_used"]), (20, 1.25, 25, 3))

    def test_no_personal_adjustment_before_three_trips_and_factor_is_clamped(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        self.run_trip(farmer, buyer, driver, actual_minutes=70)
        self.advance(10)
        tx = self.setup_deal(farmer, buyer)
        self.hire(buyer, driver, tx)
        with mock.patch("backend.services.routing.requests.post", return_value=google(1200, 9000)):
            e = driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]}).get_json()
        self.assertEqual((e["personal_factor"], e["trips_used"]), (1.0, 1))
        from backend.services.routing import personal_factor, FACTOR_LIMITS
        for _ in range(2):
            self.run_trip(farmer, buyer, driver, actual_minutes=70)
            self.advance(10)
        from backend.database import connect
        con = connect(str(self.tmp / "t.db"))
        f, n = personal_factor(con, con.execute("SELECT id FROM users WHERE role='driver'").fetchone()["id"])
        con.close()
        self.assertEqual((f, n), (FACTOR_LIMITS[1], 3))      # 70/20 = 3.5 is clamped to 1.6

    def test_arrival_records_actual_time_and_flags_overrun(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        tx = self.run_trip(farmer, buyer, driver, actual_minutes=75, max_transit=60)
        t = self.tx(buyer, tx)
        self.assertEqual((t["trip"]["actual_minutes"], t["trip"]["within_limit"]), (75, False))
        self.assertEqual(t["trip"]["estimates"]["TO_DROPOFF"]["actual_minutes"], 75)
        recorded = next(e for e in t["timeline"] if e["action"] == "TRANSIT_TIME_RECORDED")
        self.assertEqual((recorded["details"]["actual_minutes"], recorded["details"]["over_limit"]), (75, True))
        codes = [f["code"] for f in farmer.get(f"/api/transactions/{tx}/checks").get_json()["findings"]]
        self.assertIn("TRANSIT_TIME_EXCEEDED", codes)

    def test_within_limit_is_reported_as_fine(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        tx = self.run_trip(farmer, buyer, driver, actual_minutes=22, max_transit=60)
        self.assertTrue(self.tx(buyer, tx)["trip"]["within_limit"])
        codes = [f["code"] for f in buyer.get(f"/api/transactions/{tx}/checks").get_json()["findings"]]
        self.assertIn("TRANSIT_WITHIN_LIMIT", codes)
        self.assertNotIn("TRANSIT_TIME_EXCEEDED", codes)

    def test_release_warns_when_expected_trip_is_longer_than_agreed(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        self.app.config["GOOGLE_MAPS_API_KEY"] = "k"
        tx = self.setup_deal(farmer, buyer, max_transit=30)
        self.hire(buyer, driver, tx)
        with mock.patch("backend.services.routing.requests.post", return_value=google(3000, 30000)):      # 50 minutes expected
            driver.post(f"/api/transactions/{tx}/eta", {"leg": "TO_DROPOFF", "latitude": PICK[0], "longitude": PICK[1]})
        self.pickup(driver, tx)
        actions = [e["action"] for e in self.tx(buyer, tx)["timeline"]]
        self.assertIn("TRANSIT_ETA_EXCEEDS_LIMIT", actions)
        notes = " ".join(n["message"] for n in buyer.get("/api/notifications").get_json())
        self.assertIn("longer than the agreed limit", notes)

    def test_deadline_passed_while_in_transit(self):
        farmer, buyer, driver = self.user("farmer"), self.user("buyer"), self.user("driver", vehicle_type="motorcycle")
        tx = self.setup_deal(farmer, buyer, max_transit=30)
        self.hire(buyer, driver, tx)
        self.pickup(driver, tx)
        t = self.tx(buyer, tx)
        self.assertIsNotNone(t["trip"]["deadline_at"])
        self.assertIsNotNone(t["trip"]["estimates"]["TO_DROPOFF"])        # a rough estimate was created automatically at release
        self.advance(45)
        codes = [f["code"] for f in buyer.get(f"/api/transactions/{tx}/checks").get_json()["findings"]]
        self.assertIn("TRANSIT_DEADLINE_PASSED", codes)
