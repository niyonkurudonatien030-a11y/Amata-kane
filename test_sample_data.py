import sqlite3
from pathlib import Path

from tests.helpers import Api, BaseCase

ROOT = Path(__file__).resolve().parent.parent


class SampleDataTests(BaseCase):
    def load(self):
        con = sqlite3.connect(str(self.tmp / "t.db"))
        con.executescript((ROOT / "database" / "sample_data.sql").read_text(encoding="utf-8"))
        con.close()

    def test_sample_sql_loads_and_demo_users_can_log_in(self):
        self.load()
        a = Api(self.app)
        r = a.post("/api/auth/login", {"phone": "0788000002", "password": "Demo1234!"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["user"]["role"], "farmer")
        buyer = Api(self.app)
        buyer.post("/api/auth/login", {"phone": "0788000004", "password": "Demo1234!"})
        sells = buyer.get("/api/listings?type=SELL&sort=price_asc").get_json()
        self.assertEqual(len(sells), 3)
        self.assertEqual(sells[0]["price_per_litre"], 330)

    def test_schema_can_be_applied_twice(self):
        from backend.database import init_db
        init_db(str(self.tmp / "t.db"), ROOT / "database" / "schema.sql")  # second run must not fail
