"""Test helpers: a fresh temporary app and database for every test."""
import io
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import common
from backend.app import create_app
from backend.security import reset_throttle

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"AMATA-TEST-1"


def jpeg(tag="x"):
    return b"\xff\xd8\xff\xe0" + b"\x00" * 32 + tag.encode()


class Api:
    """A browser-like client that keeps its own login cookie."""

    def __init__(self, app):
        self.c = app.test_client()
        self.h = {"X-Requested-With": "AmataShield"}

    def get(self, path, **kw):
        return self.c.get(path, headers=self.h, **kw)

    def post(self, path, json=None, **kw):
        return self.c.post(path, json=json if json is not None else {}, headers=self.h, **kw)

    def patch(self, path, json=None):
        return self.c.patch(path, json=json, headers=self.h)

    def put(self, path, json=None):
        return self.c.put(path, json=json, headers=self.h)

    def delete(self, path):
        return self.c.delete(path, headers=self.h)

    def upload(self, path, category, data=None, filename="photo.jpg", **extra):
        form = {"category": category, "file": (io.BytesIO(data if data is not None else JPEG), filename), **extra}
        return self.c.post(path, data=form, headers=self.h, content_type="multipart/form-data")


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.app = create_app({"DATA_DIR": self.tmp, "DATABASE_PATH": str(self.tmp / "t.db"),
                               "EVIDENCE_DIR": self.tmp / "evidence", "SECRET_KEY": "test-secret", "TESTING": True,
                               "GEMINI_API_KEY": ""})
        reset_throttle()
        common.set_clock(None)
        self.phones = iter(range(788000001, 788000999))

    def tearDown(self):
        common.set_clock(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def user(self, role, name=None, **extra):
        api = Api(self.app)
        phone = "0" + str(next(self.phones))
        body = {"full_name": name or f"{role.title()} Test", "phone": phone, "password": "Secret123", "role": role,
                "district": "Nyabihu", "consent": True, **extra}
        if role == "coop_admin":
            body.setdefault("cooperative_name", "Test Coop")
        r = api.post("/api/auth/register", body)
        self.assertEqual(r.status_code, 201, r.get_json())
        api.phone = phone
        api.me = r.get_json()["user"]
        return api

    def make_admin(self):
        from backend.database import connect
        from backend.security import hash_password
        con = connect(str(self.tmp / "t.db"))
        con.execute("INSERT INTO users (public_id, full_name, phone, password_hash, role, consent_at, created_at, updated_at) "
                    "VALUES ('U-ADMIN001','Admin','+250788999999',?,'admin','x','x','x')", (hash_password("Admin12345"),))
        con.close()
        api = Api(self.app)
        r = api.post("/api/auth/login", {"phone": "0788999999", "password": "Admin12345"})
        self.assertEqual(r.status_code, 200, r.get_json())
        return api

    def sell_listing(self, farmer, **kw):
        body = {"listing_type": "SELL", "litres": 100, "price_per_litre": 350, "location_name": "Mukamira MCC road",
                "district": "Nyabihu", "min_lactometer": 1.026, "max_lactometer": 1.034, "terms": "Morning pickup", **kw}
        r = farmer.post("/api/listings", body)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def agreed_deal(self, farmer, buyer, litres=40, **listing_kw):
        lst = self.sell_listing(farmer, **listing_kw)
        r = buyer.post(f"/api/listings/{lst['id']}/book", {"litres": litres})
        self.assertEqual(r.status_code, 201, r.get_json())
        tx = r.get_json()["id"]
        r = farmer.post(f"/api/transactions/{tx}/confirm")
        self.assertEqual(r.status_code, 200, r.get_json())
        return tx

    def tx(self, api, pid):
        return api.get(f"/api/transactions/{pid}").get_json()

    def photo(self, api, tx, category="lactometer_photo", tag=None):
        r = api.upload(f"/api/transactions/{tx}/evidence", category, data=jpeg(tag or category + str(id(object()))))
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["id"]
