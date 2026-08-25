# AI Online Voting System — Setup Guide

## 1. Install dependencies
```bash
pip install -r requirements.txt
```

## 2. Create the database
Open phpMyAdmin or the MySQL CLI and run `schema.sql`:
```bash
mysql -u root -p < schema.sql
```

## 3. Configure secrets
Copy `.env.example` to `.env` and fill in your real values:
```bash
cp .env.example .env
```
Edit `.env`:
- `MYSQL_PASSWORD` — your MySQL root password (blank if none)
- `SECRET_KEY` — any long random string
- `GEMINI_API_KEY` — your **new, rotated** Gemini API key (the old one shared earlier must be revoked in Google AI Studio)

**Never commit `.env` to GitHub.** Add it to `.gitignore`.

## 4. Create your first admin account
```bash
python create_admin.py
```
This creates:
- Email: `admin@gmail.com`
- Password: `123456`

Log in and change this password afterward (edit the ADMIN_PASSWORD in `create_admin.py` before running, or update it directly in MySQL).

## 5. Run the app
```bash
python app.py
```
Visit `http://localhost:5000`

## What was fixed from the original code
1. **API key exposure** — moved to `.env`, loaded via `config.py` + `python-dotenv`
2. **Vote page bug** — `/vote` route was querying a non-existent `parties` table; now correctly queries `candidates`
3. **Status casing bug** — election status is now consistently lowercase (`active`, `upcoming`, `completed`) everywhere
4. **Plaintext passwords** — now hashed with `werkzeug.security.generate_password_hash` / `check_password_hash`
5. **Missing dependencies** — `requirements.txt` now includes `reportlab`, `openpyxl`, `google-generativeai`, `python-dotenv`
6. **Duplicate dashboard** — removed `user_dashboard.html` (identical to `voter_dashboard.html`)
7. **Voter approval gate** — voters with `Pending`/`Rejected` status can no longer log in and vote
8. **One-vote-per-election** enforced both in the app logic and at the DB level (`UNIQUE KEY` on `votes`)
