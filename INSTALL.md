# AmataShield installation guide

## 1. What you need
- A computer with **Python 3.10 or newer** (check with `python --version`).
- Optional: **Node.js** (only to run `tests/frontend_unit.mjs`).
- Optional: a Gemini API key and a Google Maps Platform key.
- An Android phone on the same Wi-Fi for phone testing.


## 2. Install and run
```bash
cd AmataShield
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
python scripts/init_db.py --sample   # creates data/amatashield.db with fictional demo users and listings
python run.py                        # open http://127.0.0.1:8000
```

Demo password for every demo user: `Demo1234!`. Admin 0788000001, farmer 0788000002, buyer 0788000004, driver 0788000006, collector 0788000008, cooperative 0788000009. All fictional.

Optional demo deals with drawn placeholder photos: `python scripts/seed_demo.py` (run once on a fresh database).


## 3. Turn on Gemini (AI suggestions)
1. Open Google AI Studio and create an API key.
2. Put it in `.env`: `GEMINI_API_KEY=your-key`.
3. Restart `python run.py`.
4. Open a deal, Evidence tab, press **AI read** on a photo. Check and confirm the values yourself.


## 4. Turn on Google Maps trip times
1. In Google Cloud Console create a project and enable billing (Google Maps Platform needs it).
2. Enable **Routes API**.
3. Create an API key. Restrict it to the **Routes API** and, once you have a fixed server address, to that address.
4. Put it in `.env`: `GOOGLE_MAPS_API_KEY=your-key` and restart.
5. In a deal tab **Delivery** press **Trip time to drop-off**. The label must say 'Google Maps traffic-aware time'; 'Rough estimate' means the key is missing or not accepted.
6. Read Google's current pricing and terms (including rules on storing results) before real use.

> Never put API keys in JavaScript, screenshots, chat messages or git. If a key leaks, delete it in the console and create a new one.


## 5. Test on an Android phone
- Find your computer's address on the Wi-Fi (e.g. 192.168.1.20). Set `HOST=0.0.0.0` in `.env`, restart.
- On the phone open `http://192.168.1.20:8000`. The **Take photo** button opens the phone camera and works over plain HTTP.
- The in-page **Live camera** and secure cookies need HTTPS: use a tunnelling tool or a proxy, and set `SESSION_COOKIE_SECURE=1`.
- If the phone cannot connect, check the computer's firewall.


## 6. Run the tests
```bash
python -m unittest discover -s tests -t .
node tests/frontend_unit.mjs
```


## 7. Backups and updates
- Everything that matters is in the `data/` folder (database and evidence). Copy it every day while the app is running; stop the app or use SQLite's backup tool for a consistent copy.
- After a code update that changes `database/schema.sql`, development databases must be recreated; for a live database, write a migration first.
- Never delete files from `data/evidence/`: the database keeps their fingerprints.


## 8. Troubleshooting
| Problem | Fix |
|---|---|
| `pip` not found | Use `python -m pip install -r requirements.txt` |
| Port 8000 busy | Set `PORT=8001` in `.env` |
| Login blocked (429) | Wait 10 minutes or restart |
| 403 'Missing X-Requested-With' | Add that header to curl/Postman calls |
| 'no such column' after updating | Delete `data/amatashield.db` (development only) and run `init_db.py --sample` |
| AI or Maps messages say unavailable | Check keys in `.env`, internet, and that the Routes API is enabled |
