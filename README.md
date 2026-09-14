# Freelance Project Manager + Invoice Generator

A single-user Flask + Supabase app for tracking freelance projects, payments,
and generating professional PDF invoices with a UPI QR code.

## Stack

Python, Flask, Supabase (PostgreSQL via `supabase-py`), Jinja2, hand-written
CSS (no Bootstrap/Tailwind), vanilla JavaScript, and ReportLab for PDFs.

## 1. Setup

```bash
# 1. Create and enter the project directory (skip if you already have it)
cd freelance_manager

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

## 2. Create the Supabase project & table

1. Create a project at https://supabase.com.
2. Open **SQL Editor** and run the contents of `schema.sql` (also pasted in
   the setup notes below). This creates the `projects` table with the right
   columns, CHECK constraints, and Row Level Security enabled.
3. Go to **Project Settings -> API** and copy the **Project URL** and the
   **service_role** key (not the `anon` key - the service role key is what
   lets the Flask backend bypass RLS from the server).

## 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_KEY=your_service_role_key
FLASK_SECRET_KEY=some_long_random_string
Username=your_login_username
Password=your_login_password
BUSINESS_NAME=Your Business Name
BUSINESS_OWNER=Your Name
SUPPORT_EMAIL=you@example.com
SUPPORT_PHONE=+91 0000 000 000
UPI_ID=your-upi-id@bank
```

Never commit `.env` - it's already listed in `.gitignore`.

## 4. Configure login and business details

Set these values in `.env`; no changes to `app.py` are required:

| Variable | What it controls |
|---|---|
| `Username`, `Password` | Your login credentials |
| `BUSINESS_NAME`, `BUSINESS_OWNER` | Shown in the sidebar and on invoices |
| `SUPPORT_EMAIL`, `SUPPORT_PHONE` | Shown on invoices |
| `UPI_ID` | Used to build the UPI QR code and payment link |

`REFUND_POLICY` is currently defined in `app.py` and is printed on every
invoice.

## 5. Run it

```bash
python app.py
```

Open http://127.0.0.1:5000 and log in with the credentials you set above.

## Notes

- **Authentication is intentionally hard-coded** for a single, private user.
  It is not a real user system (no hashing, no registration, no rate
  limiting) and should not be exposed on the public internet as-is. If you
  ever deploy this beyond your own machine, put it behind proper auth
  (or at minimum HTTPS + a strong password + a reverse-proxy IP allowlist).
- Every generated invoice is also saved to `invoices/` on disk for your own
  records (these are gitignored).
- Invoice numbers (`INV-00001`, `INV-00002`, ...) are assigned the first
  time you generate a project's invoice and then reused on later downloads.
