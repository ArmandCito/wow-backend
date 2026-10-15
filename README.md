# WOW Quick Bites — API

Backend of the WOW Quick Bites website: the restaurant's online ordering in Kigali. Customers browse the
menu, order for pickup or delivery (with an account or as a guest) and follow their order; managers run
the order register; the owner manages the menu, homepage campaigns, managers and their temporary rights.

Django 5.2 · Django REST Framework · Simple JWT · drf-spectacular · PostgreSQL (Neon) · Render · Brevo.

| Document | For |
|---|---|
| [docs/HANDOVER.md](docs/HANDOVER.md) | **Start here**: what changed, how to deploy, how the code is organised |
| [docs/API.md](docs/API.md) | Endpoints, rules and workflows |
| `/api/docs/` (Swagger), `/api/redoc/`, `/api/schema/` | Exact request and response fields, try the API |

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                   # optional: works without it (SQLite, emails in the console)
python manage.py migrate
python manage.py seed --demo-accounts  # the website's menu + sample accounts
python manage.py runserver
```

Open http://127.0.0.1:8000/api/docs/ and sign in with `owner@wowquickbites.rw` / `WowStaff#2026`
(`POST /auth/sign-in`, then **Authorize** with the access token).

## Commands

| Command | Does |
|---|---|
| `python manage.py test` | Runs the 37 API tests (SQLite, no external service) |
| `python manage.py seed` | Loads or refreshes the catalogue, promotions and business details from `core/seed/catalogue.json` |
| `python manage.py seed --if-empty` | Same, only when the menu is empty (used at every deploy) |
| `python manage.py seed --demo-accounts` | Also creates the sample staff and clients (staging only) |
| `python manage.py ensure_superadmin` | Creates the owner from `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` if missing |
| `python manage.py spectacular --file schema.yml --validate` | Exports and checks the OpenAPI schema |

## Project structure

| App | Area |
|---|---|
| `accounts` | Users and roles, sign-up with email code, sign-in, tokens, password, Google, permissions |
| `menu` | Catalogue (public) and menu editing with drafts (portal) |
| `orders` | Checkout, client orders, staff register |
| `notifications` | Order updates for clients |
| `promotions` | Homepage campaigns |
| `business` | Business details and fees |
| `staff` | Managers, invitations, content grants, overview |
| `audit` | Audit trail |
| `core` | Shared pieces: errors, bilingual fields, emails, uploads, rate limits, seed |

## Team

Backend: Umurerwa Iris, Cyusa Prince. Frontend: see the website repository.
