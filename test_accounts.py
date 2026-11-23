import sqlite3

from tests.helpers import Api, BaseCase


class AccountTests(BaseCase):
    def test_register_login_logout_me(self):
        a = self.user("farmer", "Alice N")
        self.assertEqual(a.get("/api/auth/me").get_json()["user"]["full_name"], "Alice N")
        self.assertEqual(a.post("/api/auth/logout").status_code, 200)
        self.assertEqual(a.get("/api/auth/me").status_code, 401)
        r = a.post("/api/auth/login", {"phone": a.phone, "password": "Secret123"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(a.get("/api/auth/me").status_code, 200)

    def test_password_is_hashed_in_database(self):
        a = self.user("farmer")
        con = sqlite3.connect(str(self.tmp / "t.db"))
        stored = con.execute("SELECT password_hash FROM users").fetchone()[0]
        con.close()
        self.assertNotIn("Secret123", stored)
        self.assertTrue(stored.startswith(("scrypt:", "pbkdf2:")))

    def test_registration_validation(self):
        api = Api(self.app)
        base = {"full_name": "Bob", "phone": "0788111222", "password": "Secret123", "role": "buyer", "consent": True}
        self.assertEqual(api.post("/api/auth/register", {**base, "password": "short"}).status_code, 422)
        self.assertEqual(api.post("/api/auth/register", {**base, "phone": "12345"}).status_code, 422)
        self.assertEqual(api.post("/api/auth/register", {**base, "consent": False}).status_code, 422)
        self.assertEqual(api.post("/api/auth/register", {**base, "role": "admin"}).status_code, 422)
        self.assertEqual(api.post("/api/auth/register", base).status_code, 201)
        self.assertEqual(Api(self.app).post("/api/auth/register", base).status_code, 409)  # duplicate phone

    def test_phone_formats_normalised(self):
        a = self.user("farmer")
        r = Api(self.app).post("/api/auth/login", {"phone": "+250" + a.phone[1:], "password": "Secret123"})
        self.assertEqual(r.status_code, 200)

    def test_login_throttle(self):
        a = self.user("farmer")
        api = Api(self.app)
        for _ in range(5):
            self.assertEqual(api.post("/api/auth/login", {"phone": a.phone, "password": "bad"}).status_code, 401)
        self.assertEqual(api.post("/api/auth/login", {"phone": a.phone, "password": "Secret123"}).status_code, 429)

    def test_csrf_header_required(self):
        c = self.app.test_client()
        r = c.post("/api/auth/login", json={"phone": "0788000000", "password": "x"})
        self.assertEqual(r.status_code, 403)

    def test_profile_and_password_change(self):
        a = self.user("buyer")
        r = a.patch("/api/users/me", {"business_name": "Kigali Dairy", "district": "Gasabo"})
        self.assertEqual(r.get_json()["user"]["business_name"], "Kigali Dairy")
        self.assertEqual(a.post("/api/users/me/password", {"current_password": "bad", "new_password": "NewSecret1"}).status_code, 403)
        self.assertEqual(a.post("/api/users/me/password", {"current_password": "Secret123", "new_password": "NewSecret1"}).status_code, 200)
        self.assertEqual(Api(self.app).post("/api/auth/login", {"phone": a.phone, "password": "NewSecret1"}).status_code, 200)

    def test_payment_methods(self):
        a = self.user("farmer")
        r = a.post("/api/users/me/payment-methods", {"method_type": "momo_code", "label": "MoMo Pay", "account_value": "123456"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(a.get("/api/users/me/payment-methods").get_json()), 1)
        a.delete(f"/api/users/me/payment-methods/{r.get_json()['id']}")
        self.assertEqual(a.get("/api/users/me/payment-methods").get_json(), [])

    def test_admin_only_endpoints(self):
        f = self.user("farmer")
        self.assertEqual(f.get("/api/admin/users").status_code, 403)
        adm = self.make_admin()
        users = adm.get("/api/admin/users").get_json()
        self.assertGreaterEqual(len(users), 2)
        target = next(u for u in users if u["role"] == "farmer")
        self.assertEqual(adm.post(f"/api/admin/users/{target['public_id']}/verify").status_code, 200)
        self.assertTrue(f.get("/api/auth/me").get_json()["user"]["is_verified"])
        adm.post(f"/api/admin/users/{target['public_id']}/deactivate")
        self.assertEqual(f.get("/api/auth/me").status_code, 401)
        self.assertTrue(adm.get("/api/admin/audit/verify").get_json()["ok"])
