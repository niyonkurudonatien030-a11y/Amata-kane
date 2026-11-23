# What has and has not been tested (honest status)

Run `python -m unittest discover -s tests -t .` and `node tests/frontend_unit.mjs`.

## Tested automatically (passes in the build environment)
| Area | How |
|---|---|
| Database creation, schema re-run, sample data load | unit tests |
| Registration, login/logout, password hashing, login throttling, CSRF header | API tests |
| Role permissions (listing/booking rules, admin-only, coop read-only, outsider gets 404) | API tests |
| Listing filters, price/litres/distance sorting | API tests |
| Booking hold: two-party acceptance with timestamps, expiry after the hold, litres returned | API tests with a simulated clock |
| Driver job: post, apply, choose, accept, arrive; contact revealed after acceptance | API tests |
| Lactometer gate: within range, outside range (buyer decision), unclear photo (redo), no range agreed | API tests |
| Evidence upload: file type checked by content, size limit, SHA-256, immutability triggers, other party can view | API tests |
| Payments: report, confirm, reject opens dispute and flags both, recovery after resolution, amount mismatch | API tests |
| Disputes: open, comment, evidence, proposal accept/reject, final outcome, withdraw, mediator limits | API tests |
| Audit hash chain and tamper detection | API tests |
| Trip time: Google request shape (key in header, TWO_WHEELER/DRIVE/BICYCLE), fallback to DRIVE then rough estimate, 5-minute cache, personal pace learned after 3 trips and clamped, actual time recorded on arrival, over-limit and deadline warnings, drop-off permissions | API tests with **mocked** Google and simulated clock |
| Gemini wiring (request shape, key only in a header, parsing, human confirmation, error handling, no names/phones sent) | **mocked** Gemini responses only |
| Front end / back end consistency: every URL the JavaScript calls exists; every button has a handler; no inline styles | contract tests |
| JavaScript escaping helpers (XSS) | node unit test |
| Server starts; all pages and assets return 200; security headers present | live `curl` smoke test |

## NOT tested (needs a real phone/browser or credentials)
- Real **Google Maps** calls and accuracy on Rwandan roads. Steps: enable Routes API, set `GOOGLE_MAPS_API_KEY`, create a deal with GPS pickup/drop-off, press *Trip time*, compare with the Google Maps app, then compare predicted and actual minutes on 20+ real trips.
- Real **Gemini** calls (no API key or internet in the build environment). Steps: set `GEMINI_API_KEY`, upload a lactometer photo, press **AI read**.
- **Browser rendering** and **mobile responsiveness** (no browser available). Steps: open the site on an Android phone and walk through the demo script.
- **Camera capture** (`capture` input and `getUserMedia` live camera). Needs HTTPS or localhost on a real device.
- Real **SMS / USSD / mobile money** (not implemented; see roadmap).
- Load, performance and concurrency beyond SQLite's single writer.
