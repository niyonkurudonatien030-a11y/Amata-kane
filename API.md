# AmataShield API reference

Generated from the running code by `scripts/make_api_docs.py`. All endpoints are under `/api`, return JSON, and (except health, register, login and the cooperative list) need a logged-in session cookie.
Every POST/PATCH/DELETE must send the header `X-Requested-With: AmataShield`. Errors look like `{"error": "message"}` with an HTTP status (401 not logged in, 403 not allowed, 404 not found or not yours, 409 wrong state, 422 invalid input, 503 AI unavailable).

## admin

| Method | Path | Handler | Note |
|---|---|---|---|
| GET | `/api/admin/audit/verify` | `audit_verify` |  |
| GET | `/api/admin/users` | `users` |  |
| POST | `/api/admin/users/<pid>/activate` | `activate` |  |
| POST | `/api/admin/users/<pid>/deactivate` | `deactivate` |  |
| POST | `/api/admin/users/<pid>/verify` | `verify` |  |

## ai

| Method | Path | Handler | Note |
|---|---|---|---|
| POST | `/api/ai/<aid>/confirm` | `confirm` |  |
| POST | `/api/ai/<aid>/reject` | `reject` |  |
| GET | `/api/ai/status` | `ai_status` |  |
| POST | `/api/evidence/<ev_pid>/analyze` | `analyze` |  |
| POST | `/api/transactions/<pid>/ai-summary` | `ai_summary` |  |
| GET | `/api/transactions/<pid>/checks` | `checks` | Rule-based consistency checks. Works without any AI service. |

## auth

| Method | Path | Handler | Note |
|---|---|---|---|
| POST | `/api/auth/login` | `login` |  |
| POST | `/api/auth/logout` | `logout` |  |
| GET | `/api/auth/me` | `me` |  |
| POST | `/api/auth/register` | `register` |  |
| GET | `/api/cooperatives` | `cooperatives` |  |
| PATCH | `/api/users/me` | `update_me` |  |
| POST | `/api/users/me/password` | `change_password` |  |
| GET | `/api/users/me/payment-methods` | `list_methods` |  |
| POST | `/api/users/me/payment-methods` | `add_method` |  |
| DELETE | `/api/users/me/payment-methods/<int:mid>` | `delete_method` |  |

## dashboard

| Method | Path | Handler | Note |
|---|---|---|---|
| GET | `/api/dashboard` | `dashboard` |  |
| GET | `/api/notifications` | `notifications` |  |
| POST | `/api/notifications/read` | `mark_read` |  |

## disputes

| Method | Path | Handler | Note |
|---|---|---|---|
| GET | `/api/disputes` | `list_disputes` |  |
| GET | `/api/disputes/<pid>` | `get_dispute` |  |
| POST | `/api/disputes/<pid>/events` | `add_event` |  |
| POST | `/api/disputes/<pid>/proposals/<int:event_id>/respond` | `respond` |  |
| POST | `/api/disputes/<pid>/resolve` | `resolve` |  |
| POST | `/api/disputes/<pid>/withdraw` | `withdraw` |  |

## transactions

| Method | Path | Handler | Note |
|---|---|---|---|
| GET | `/api/evidence/<ev_pid>/file` | `evidence_file` |  |
| GET | `/api/jobs` | `open_jobs` |  |
| POST | `/api/jobs/<jpid>/accept` | `accept_job` |  |
| POST | `/api/jobs/<jpid>/apply` | `apply_job` |  |
| POST | `/api/jobs/<jpid>/cancel` | `cancel_job` |  |
| POST | `/api/jobs/<jpid>/decline` | `decline_job` |  |
| POST | `/api/jobs/<jpid>/select` | `select_driver` |  |
| GET | `/api/jobs/mine` | `my_jobs` |  |
| GET | `/api/routing/status` | `routing_status` |  |
| GET | `/api/transactions` | `list_transactions` |  |
| GET | `/api/transactions/<pid>` | `get_transaction` |  |
| POST | `/api/transactions/<pid>/arrived` | `arrived` |  |
| POST | `/api/transactions/<pid>/cancel` | `cancel` |  |
| POST | `/api/transactions/<pid>/confirm` | `confirm` |  |
| POST | `/api/transactions/<pid>/decision` | `decision` |  |
| POST | `/api/transactions/<pid>/decline` | `decline` |  |
| POST | `/api/transactions/<pid>/disputes` | `open_dispute` |  |
| POST | `/api/transactions/<pid>/driver-arrived` | `driver_arrived` |  |
| PUT | `/api/transactions/<pid>/dropoff` | `set_dropoff` |  |
| POST | `/api/transactions/<pid>/eta` | `trip_eta` | Arrival time for a leg: Google Maps baseline x the carrier's own learned pace. |
| POST | `/api/transactions/<pid>/evidence` | `upload_evidence` |  |
| GET | `/api/transactions/<pid>/evidence` | `list_evidence` |  |
| POST | `/api/transactions/<pid>/job` | `post_job` |  |
| POST | `/api/transactions/<pid>/quality` | `quality` |  |
| POST | `/api/transactions/<pid>/quality/waive` | `waive` |  |
| POST | `/api/transactions/<pid>/transport/self` | `transport_self` |  |

## health

| Method | Path | Handler | Note |
|---|---|---|---|
| GET | `/api/health` | `health` |  |

## listings

| Method | Path | Handler | Note |
|---|---|---|---|
| POST | `/api/listings` | `create_listing` |  |
| GET | `/api/listings` | `search_listings` |  |
| GET | `/api/listings/<pid>` | `get_listing` |  |
| POST | `/api/listings/<pid>/book` | `book` |  |
| POST | `/api/listings/<pid>/cancel` | `cancel_listing` |  |

## payments

| Method | Path | Handler | Note |
|---|---|---|---|
| POST | `/api/payments/<pid>/confirm` | `confirm` |  |
| POST | `/api/payments/<pid>/reject` | `reject` |  |
| POST | `/api/payments/<pid>/report` | `report` |  |
