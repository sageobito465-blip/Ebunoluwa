# Ebook Shop

A Flask application for selling ebooks, recording orders and payments, and managing the catalogue and customers.

## Features

* Customer registration, login, shopping cart, checkout, and order history
* Paystack payment initialization and server-side payment verification
* A customer library with downloads restricted to paid purchases
* Admin pages for ebooks, categories, customers, orders, and payment records
* PDF upload checks, optional cover-image validation, and CSRF protection

## Technology and project layout

* `app.py` — Flask routes, authentication, checkout, payments, uploads, and downloads
* `database.py` — PostgreSQL/Neon database connection
* `database/schema.sql` — PostgreSQL table definitions
* `templates/` — customer and admin Jinja templates
* `static/css/` — application styling
* `static/uploads/` — ebook and cover files
* `test_database.py` — database connectivity check

The application uses Python 3.10 or newer, Flask, Flask-WTF, Werkzeug, psycopg, `python-dotenv`, `requests`, and Gunicorn. Exact versions are recorded in `requirements.txt`.

## Quick setup

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file from the template:

```bash
cp .env.example .env
```

If you already have a `.env` file, do not run the copy command again. Edit your existing file instead.

Configure the following values in `.env`:

* `FLASK_SECRET_KEY` — a strong, unique secret key
* `DATABASE_URL` — your Neon PostgreSQL connection string
* `PAYSTACK_SECRET_KEY` — your Paystack test or live secret key

Never commit `.env` or share its values.

## Database

The application uses PostgreSQL. The production database is hosted on Neon.

The schema in `database/schema.sql` creates these tables:

* `users`
* `categories`
* `books`
* `cart`
* `orders`
* `order_items`
* `payments`

The application connects using the `DATABASE_URL` environment variable.

## Environment variables

* `FLASK_SECRET_KEY` — required secret for sessions and CSRF tokens
* `FLASK_DEBUG` — optional; set to `true`, `1`, or `yes` only for local development
* `SESSION_COOKIE_SECURE` — use `false` for local HTTP; set to `true` when served over HTTPS
* `DATABASE_URL` — PostgreSQL/Neon connection string
* `PAYSTACK_SECRET_KEY` — Paystack test or live secret key

`database.py` loads `.env` from the project directory. Run commands from the project root.

## Running locally

Start the Flask development server:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

Check the database connection:

```bash
python test_database.py
```

## Production deployment

The application can be served with Gunicorn:

```bash
gunicorn app:app
```

The current deployment architecture uses:

* Render for the Flask web service
* Neon for PostgreSQL
* Paystack for payments

Configure the required environment variables on your hosting platform.

For production, use HTTPS and set:

```text
SESSION_COOKIE_SECURE=true
FLASK_DEBUG=false
```

## Paystack

Use a Paystack test secret key in `PAYSTACK_SECRET_KEY` during development.

The application initializes payments through Paystack and verifies the returned transaction server-side.

For deployment, ensure the payment callback uses your public HTTPS application URL.

## File storage

Ebooks and cover images are stored under `static/uploads/`.

The application works with files included in the repository. Hosting platforms with ephemeral filesystems may require external storage for files uploaded after deployment.

## Security

* Never commit `.env`
* Never expose database passwords or API secret keys
* Use a strong `FLASK_SECRET_KEY`
* Use Paystack test keys during development
* Use HTTPS and secure session cookies in production
