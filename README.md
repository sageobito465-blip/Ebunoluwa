# Ebook Shop

A Flask and MariaDB application for selling ebooks, recording orders and payments, and managing the catalogue and customers.

## Features

- Customer registration, login, shopping cart, checkout, and order history
- Paystack payment initialization and server-side payment verification
- A customer library with downloads restricted to ebooks in that customer's paid orders
- Admin pages for ebooks, categories, customers, orders, and payment records
- PDF upload checks, optional cover image validation, and CSRF protection for form submissions

## Technologies

Python, Flask, MariaDB/MySQL, PyMySQL, Flask-WTF, Werkzeug password hashing, HTML, and CSS. Paystack is used for payment processing.

## Project structure

- `app.py` — Flask routes, checkout, payment, uploads, and access checks
- `database.py` — database connection configuration
- `database/schema.sql` — database and table definitions
- `templates/` — customer and admin pages
- `static/css/style.css` — application styling
- `static/uploads/` — uploaded ebook and cover files (local runtime data)
- `test_database.py` — a basic database connection check

## Setup

1. Create a MariaDB database and tables by running `database/schema.sql` with a database account that can create databases and tables.
2. Create and activate a Python virtual environment, then install packages:

   ```sh
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set the database and application settings below. Generate a unique `FLASK_SECRET_KEY`; do not use the example placeholder.
4. Start the application:

   ```sh
   python app.py
   ```

   `FLASK_DEBUG` defaults to `false`. Set it to `true` only for local development. The app reads `.env` through `python-dotenv`.

## Environment variables

- `FLASK_SECRET_KEY` — required, random secret used to sign sessions and CSRF tokens
- `FLASK_DEBUG` — optional; enables Flask debug mode only when set to `true`, `1`, or `yes`
- `SESSION_COOKIE_SECURE` — set to `true` when serving the application over HTTPS; leave `false` for local HTTP development
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` — MariaDB/MySQL connection settings
- `PAYSTACK_SECRET_KEY` — Paystack test or live secret key; required for payment actions

## Customer workflow

Customers register and log in, browse ebook details, add ebooks to their cart, and place orders. An unpaid order can be paid through Paystack. After the callback, the app verifies the transaction with Paystack before marking the payment and order as successful. Paid purchases appear in the customer's library.

## Admin workflow

Register an account, then have a trusted database administrator promote that account by setting its `users.role` to `Admin`. Admin users can manage the catalogue and categories, review orders and payment records, and view or edit customers. Customers cannot access these routes.

## Paystack setup

Configure `PAYSTACK_SECRET_KEY` with a key from the Paystack dashboard. Use test credentials for local development. Configure the deployed application's public HTTPS URL as the callback URL where required by your Paystack setup. A live payment cannot be verified using local placeholder credentials.

## Security and operations

- Keep `.env` private and never commit real database, Flask, or Paystack secrets.
- Enable HTTPS in deployment and set `SESSION_COOKIE_SECURE=true` there.
- All state-changing application forms use CSRF tokens. Cart changes, deletions, and logout use POST requests.
- Ebook files are kept out of direct static-file access. Downloads are served only after checking the signed-in customer's paid purchases.
- Ebook uploads accept PDF extensions and check the PDF signature. Cover uploads accept common raster image types and check their file signatures.
- Back up the database and the upload directories together. The SQL schema is not a migration system and should not be re-run against production data without review.

## Checks

Run `python test_database.py` to check database connectivity. Application routes can also be inspected with `flask --app app routes`. Payment initialization and callbacks require a reachable Paystack API and valid credentials for an end-to-end check.
