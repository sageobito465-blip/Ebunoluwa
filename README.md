# Ebook Shop

A Flask and MariaDB application for selling ebooks, recording orders and payments, and managing the catalogue and customers.

## Features

- Customer registration, login, shopping cart, checkout, and order history
- Paystack payment initialization and server-side payment verification
- A customer library with downloads restricted to paid purchases
- Admin pages for ebooks, categories, customers, orders, and payment records
- PDF upload checks, optional cover-image validation, and CSRF protection

## Technology and project layout

- `app.py` — Flask routes, authentication, checkout, payments, uploads, and downloads
- `database.py` — MariaDB/MySQL connection setup using environment variables
- `database/schema.sql` — database and table definitions
- `templates/` — customer and admin Jinja templates
- `static/css/` — application styling
- `static/uploads/` — local ebook and cover files
- `test_database.py` — database connectivity check

The application uses Python 3.10 or newer, Flask, Flask-WTF, Werkzeug, PyMySQL, `python-dotenv`, and `requests`. Exact versions are recorded in `requirements.txt`.

For the complete Windows procedure, see [WINDOWS_SETUP.md](WINDOWS_SETUP.md).

## Quick setup

From the project directory in Windows PowerShell:

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Use any installed Python version supported by the packages if `py -3.11` is unavailable; Python 3.11 is the recommended example.

Edit `.env` with a unique `FLASK_SECRET_KEY`, the MariaDB account details, and a Paystack test secret key. Never commit `.env` or share its values.

Create the database and tables with the MariaDB client:

```powershell
Get-Content .\database\schema.sql | mariadb -u root -p
```

The schema creates the `ebook_shop` database. The account in `.env` must have access to that database. The application uses the default MariaDB/MySQL TCP port, 3306; `DB_HOST=localhost` is suitable for a local Windows installation. If the client is named `mysql.exe` on that machine, substitute `mysql` for `mariadb` in the command.

Start the application:

```powershell
python app.py
```

Open <http://127.0.0.1:5000/> in a browser. Check the database connection with:

```powershell
python test_database.py
```

## Environment variables

- `FLASK_SECRET_KEY` — required random secret for sessions and CSRF tokens
- `FLASK_DEBUG` — optional; set to `true`, `1`, or `yes` only for local development
- `SESSION_COOKIE_SECURE` — leave `false` for local HTTP; set to `true` only behind HTTPS
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` — MariaDB/MySQL connection settings
- `PAYSTACK_SECRET_KEY` — Paystack test or live secret key; required for payment actions

`database.py` loads `.env` from the working directory. Run commands from the project root.

## Database and admin setup

The schema preserves the relationships between users, categories, books, carts, orders, order items, and payments. `order_items.quantity` is included because the application stores and displays the quantity for each ordered book.

To create a separate application account, first run the schema as an administrative MariaDB user, then run SQL similar to the following with a strong password of your own:

```sql
CREATE USER 'ebook_app'@'localhost' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT ALL PRIVILEGES ON ebook_shop.* TO 'ebook_app'@'localhost';
FLUSH PRIVILEGES;
```

Set that account in `.env`. Register a normal account through the application, then have a trusted database administrator promote it if admin access is needed:

```sql
UPDATE ebook_shop.users
SET role = 'Admin'
WHERE email = 'admin@example.com';
```

Do not rerun the schema against production data without reviewing the existing tables first. The SQL file is an initial schema, not a migration system.

## Paystack

Put a Paystack test secret key in `PAYSTACK_SECRET_KEY` for local testing. The application initializes payments through Paystack and verifies the returned transaction server-side. For a deployed or live environment, use the public HTTPS application URL for the callback flow and set `SESSION_COOKIE_SECURE=true`.

## Windows notes

- Do not copy or activate the repository's Unix-style `venv`; create a fresh `.venv` on Windows.
- MariaDB must be running as a Windows service and listening on port 3306, unless the application code is extended to support another port.
- Upload directories are created automatically when an admin uploads a book. Keep the database and `static/uploads/` files backed up together.
- The development server is intended for local use, not production hosting.
