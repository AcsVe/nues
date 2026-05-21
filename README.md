# nues — ACS Booking

A Flask port of the original Google Apps Script venue booking system for the
Arab Cultural Society (الجمعية الثقافية العربية). Bilingual (Arabic / English)
calendar, booking form, and admin console.

- **Live URL:** _to be filled in after first Render deploy_
- **Repo:** https://github.com/AcsVe/nues

## Local development

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Opens on http://localhost:5000 with a local SQLite database (`booking.db`).

Routes:

- `/` — public calendar
- `/book` — booking form (create / lookup / amend / cancel)
- `/admin` — admin console (login required)
- `/api/halls`, `/api/month_data`, etc. — JSON API

## Deploy to Render (Blueprint)

This repo ships a `render.yaml` blueprint that provisions a free Python web
service `nues` in the **Frankfurt** region running `gunicorn app:app`. The
Postgres database is created separately (manually) on Render.

Steps:

1. Create the Postgres database in the Render dashboard (free plan,
   Frankfurt region, e.g. `nues_db`).
2. Click **New +** → **Blueprint** and connect the `AcsVe/nues` repository.
   Render reads `render.yaml` and creates the web service.
3. Open the web service → **Environment** tab and paste the **Internal**
   Postgres URL as `DATABASE_URL`.
4. Set `ADMIN_PASSWORD` to a strong value. `SECRET_KEY` is generated for you.
5. Click **Manual Deploy** → first build ~3 minutes.

On the free tier the dyno sleeps after inactivity; the first request after a
sleep takes ~30 seconds to wake.

## Environment variables

| Name             | Purpose                                       | Default                  |
|------------------|-----------------------------------------------|--------------------------|
| `DATABASE_URL`   | Postgres connection string (set manually)      | local SQLite `booking.db`|
| `SECRET_KEY`     | Flask session secret                          | dev fallback             |
| `ADMIN_PASSWORD` | Admin console password                        | `acs2024` (local only)   |
| `ADMIN_USER`     | Admin console username                        | `admin`                  |
| `BREVO_API_KEY`  | Brevo transactional email API key             | dev key                  |
| `SENDER_EMAIL`   | From-address for outbound mail                 | `acsvenues@gmail.com`    |
| `PYTHON_VERSION` | Python runtime (set by `render.yaml`)         | `3.11.9`                 |

## Admin login

Default credentials are `admin` / `acs2024` for local dev. **Always set a
strong `ADMIN_PASSWORD` env var in production** — the default is only meant
for local testing.
