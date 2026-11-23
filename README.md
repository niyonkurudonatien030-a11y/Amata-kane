# AmataShield

**Transparent dairy deals, shared evidence.** A mobile-first web app where farmers, buyers, drivers/riders, collectors and cooperatives in Rwanda record a milk deal from listing to payment: agreed litres and price, lactometer-test evidence, delivery acceptance or dispute, and payment status.

> **What it is not.** AmataShield does not hold or send money, is not escrow or a bank, and never certifies milk as safe. It is a shared, time-stamped record. AI only *suggests*; people confirm.

## Features (implemented in this MVP)
- Roles: farmer, buyer, driver/rider, supplier/collector, cooperative admin, system admin. Registration, login, logout, profile, password change, role-based permissions.
- Marketplace: sell offers and buy requests; filters by price, litres, district and nearest (GPS).
- Booking with a **confirmation window** (default 60 s, from your field notes). Both acceptances are time-stamped. Expired holds release the litres.
- **Driver jobs**: post a job with a wage, drivers apply, the poster chooses, the driver accepts; call/SMS/WhatsApp links appear after acceptance.
- **Lactometer gate**: photo + reading at pickup compared with the range the parties agreed. Unclear photo = redo. Out of range = the buyer must decide. The buyer repeats the check on arrival, then accepts or rejects.
- **Trip time with Google Maps**: the server asks Google Routes for the carrier's travel time (key only on the server), multiplies it by that carrier's own learned pace (median of past actual/predicted trips, after 3 trips, limited 0.6-1.6), records pickup and arrival times, and warns when a trip exceeds the longest time the parties agreed. Without a key a labelled rough estimate is used.
- Evidence vault: originals stored untouched with SHA-256, metadata and history; both parties see all evidence.
- Payment **tracking**: unconfirmed, reported, confirmed by both, or rejected (both flagged and a dispute opens).
- Disputes: open, comment, attach evidence, propose, accept/reject, record the final outcome; immutable timeline.
- Gemini (server side): read lactometer/receipt photos and summarise a deal (English, Kinyarwanda or French). Without a key, rule-based consistency checks still run.
- Tamper-evident audit log (hash chain) with admin verification.

## Quick start (Windows, macOS, Linux). Needs Python 3.10+
```bash
cd AmataShield
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env  (then edit it)
python scripts/init_db.py --sample # creates data/amatashield.db with fictional demo users and listings
python run.py                      # open http://127.0.0.1:8000
```
Demo logins (password `Demo1234!`): admin `0788000001`, farmer `0788000002`, buyer `0788000004`, driver `0788000006`, collector `0788000008`, cooperative `0788000009`. All demo people are fictional.

Optional demo journeys (completed, in transit, disputed, waiting deals with drawn placeholder photos) on a fresh database: `python scripts/seed_demo.py`.

## Turn on Gemini
1. Get a key at https://aistudio.google.com/ .
2. Put it in `.env` as `GEMINI_API_KEY=...` (never in JavaScript, never in git).
3. Restart. Open a deal, Evidence tab, press **AI read** on a photo. Check the values, correct them, then confirm.

## Turn on Google Maps trip times
1. In Google Cloud Console create a project, enable billing and the **Routes API**.
2. Create an API key restricted to the Routes API (and to your server address when it has one).
3. Put it in `.env` as `GOOGLE_MAPS_API_KEY=...` and restart.
4. In a deal open the **Delivery** tab and press **Trip time to drop-off**. The label must say *Google Maps traffic-aware time*; *Rough estimate* means no usable key.
5. Read Google's current pricing and terms (including rules about storing results) before real use.

## Test on your phone
- Same Wi-Fi: set `HOST=0.0.0.0` in `.env`, run `python run.py`, open `http://<computer-ip>:8000` on the phone. The **Take photo** button (phone camera app) works over plain HTTP. The in-page **Live camera** needs HTTPS or localhost.
- For HTTPS use a tunnel (Cloudflare Tunnel, ngrok) or a reverse proxy, and set `SESSION_COOKIE_SECURE=1`.

## Run the tests
```bash
python -m unittest discover -s tests -t .      # 62 tests
node tests/frontend_unit.mjs
```
See `documentation/TEST_STATUS.md` for exactly what is and is not tested.

## Project layout
```
backend/   app.py config.py database.py security.py audit.py common.py
           routes/    thin HTTP layer (auth, listings, transactions, payments, disputes, ai, dashboard, admin)
           services/  business rules (transactions = state machine, workflow, delivery, payments, disputes, quality, evidence, storage, routing)
           ai/        gemini_client.py prompts.py rules.py
frontend/  index.html login.html register.html app.html   css/style.css   js/*.js   assets/ (logo)
database/  schema.sql sample_data.sql
scripts/   init_db.py make_sample_data.py make_api_docs.py seed_demo.py
tests/     unittest suites + frontend_unit.mjs          documentation/  API.md ARCHITECTURE.md TEST_STATUS.md
```

## Design decisions
- **Flask + SQLite** (the first prototype used FastAPI): runs anywhere with no database server, and could be fully tested here. Business rules live in `services/`, so moving to FastAPI/PostgreSQL later changes only the thin route layer and `database.py`.
- No JavaScript framework: plain ES modules a student can read end to end.
- A Content-Security-Policy forbids inline scripts and styles; all user text is escaped.

## Limitations
Google Maps and Gemini were tested only with mocked responses; live accuracy on Rwandan roads is unproven; single-server SQLite; no SMS/USSD/mobile-money; notifications are in-app only; the UI is English only (AI replies can be requested in Kinyarwanda); quality ranges are written by the deal parties, not taken from a Rwandan standard; legal review is needed before real money or contracts are involved.
