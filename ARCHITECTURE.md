# Architecture in one page

```
Phone browser (HTML/CSS/JS modules) --fetch JSON + cookie--> Flask routes --> services (rules) --> SQLite
      |                                                          |                 |
 camera / GPS                                             audit hash chain   evidence files (data/evidence)
                                                                 |
                                                       Gemini REST API (server only)
```
**Request life cycle.** `before_request` checks the CSRF header, opens `BEGIN IMMEDIATE` for writes and loads the user from the signed session cookie. The route validates input (`common.field`), calls a service and returns JSON. `after_request` commits on success or rolls back on any error, so a failed request never half-saves.

**Deal state machine** (`services/transactions.py`): REQUESTED -> AGREED -> IN_TRANSIT -> DELIVERED -> ACCEPTED -> COMPLETED. DISPUTED returns to the previous state. EXPIRED, DECLINED, CANCELLED are terminal. The server tells each viewer which `actions` they may take; the front end only draws those buttons.

**Evidence.** Uploaded bytes are type-checked by their first bytes, hashed (SHA-256) and written once. Database triggers forbid UPDATE/DELETE on evidence, audit and dispute-event rows.

**AI boundary.** The browser never sees the key. Gemini output is stored as a SUGGESTION; only values a person confirms are used. Prompts forbid safety or payment claims, and summary prompts exclude names and phone numbers.

**Trip timing.** `services/routing.py` asks the Google Routes API (server side) for the baseline time, multiplies it by the carrier's median past actual/predicted ratio (3+ trips, limited 0.6-1.6) and stores the prediction in `trip_estimates`. `pickup_at` and `arrived_at` give the actual time, which is written back to teach the next prediction. The slow Google call happens before the short database write so the database is not locked while waiting.
