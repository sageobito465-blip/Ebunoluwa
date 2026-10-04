# Windows setup

These instructions prepare the Ebook Shop for local development on Windows 10 or Windows 11 using PowerShell.

## 1. Install prerequisites

Install the following before opening the project:

1. Python 3.10 or newer. Python 3.11 is recommended for this project.
2. MariaDB Server and its command-line client. During installation, record the administrative password and make sure the MariaDB service is installed.
3. Git, if the project will be cloned from a repository.

Confirm Python is available:

```powershell
py --version
```

If the MariaDB client is not on `PATH`, use the full path to `mariadb.exe` in the commands below, or add the MariaDB `bin` directory to the Windows `PATH`. Some installers expose the client as `mysql.exe`; substitute that command if necessary.

## 2. Open the project

Clone or copy the project, then open PowerShell in the project root. For a cloned repository, the commands are typically:

```powershell
git clone <repository-url>
Set-Location .\ebook_shop
```

The project root is the directory containing `app.py`, `database.py`, and `database\schema.sql`.

## 3. Create and activate a Windows virtual environment

Create a new environment for this machine. Do not reuse a `venv` created on Linux or macOS.

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

The execution-policy command applies only to the current PowerShell process. If Python 3.11 is not installed, replace `-3.11` with an installed Python 3.10+ version.

Install the application dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PyMySQL is a pure-Python MariaDB/MySQL driver, so this setup does not require compiling `mysqlclient` or installing Visual C++ build tools for the database driver.

## 4. Start MariaDB and create the database

Start MariaDB from the Windows Services application. If the service is registered with the usual name, PowerShell can also use:

```powershell
Get-Service MariaDB
Start-Service MariaDB
```

The exact service name can differ by installer or version. If `Get-Service MariaDB` does not find it, search for MariaDB/MySQL in Services and start the matching service there.

Run the checked-in schema as a MariaDB administrative user:

```powershell
Get-Content .\database\schema.sql | mariadb -u root -p
```

Enter the MariaDB root password when prompted. This creates the `ebook_shop` database and its tables. The schema creates tables in dependency order and preserves these relationships:

- `books.category_id` references `categories.id`
- `cart.user_id` references `users.id`
- `cart.book_id` references `books.id`
- `orders.user_id` references `users.id`
- `order_items.order_id` references `orders.id`
- `order_items.book_id` references `books.id`
- `payments.order_id` references `orders.id`

For a separate application account, connect as an administrator and run SQL like this, replacing the placeholder password with a strong private password:

```sql
CREATE USER 'ebook_app'@'localhost' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT ALL PRIVILEGES ON ebook_shop.* TO 'ebook_app'@'localhost';
FLUSH PRIVILEGES;
```

If the account is created for a different host, the host part of the MariaDB account must match the host used by the connection. Keep `DB_HOST=localhost` unless there is a specific reason to use another host.

## 5. Configure environment variables

Create a private `.env` file from the example:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set these values:

```dotenv
FLASK_SECRET_KEY=generate-a-long-random-value
FLASK_DEBUG=false
SESSION_COOKIE_SECURE=false

DB_HOST=localhost
DB_USER=ebook_app
DB_PASSWORD=the-password-created-for-ebook_app
DB_NAME=ebook_shop

PAYSTACK_SECRET_KEY=your-paystack-test-secret-key
```

Required values are `FLASK_SECRET_KEY`, `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, and `PAYSTACK_SECRET_KEY`. Do not use the placeholders in a real environment, and do not commit or share `.env`.

For local HTTP development, keep `SESSION_COOKIE_SECURE=false`. Set it to `true` only when the application is served over HTTPS. The current database connection uses PyMySQL’s default TCP port 3306; a MariaDB installation using another port requires a corresponding application-code configuration change because `DB_PORT` is not currently read.

## 6. Verify the database connection

With `.venv` still active and the project root as the current directory, run:

```powershell
python test_database.py
```

The expected result is:

```text
Database connected successfully!
```

If the connection fails, verify that MariaDB is running, that `DB_HOST` is correct, that the account has privileges on `ebook_shop`, and that the password in `.env` has no accidental surrounding spaces or quotes.

## 7. Configure Paystack payments

Create or retrieve test credentials from the Paystack dashboard and place the secret key only in `.env` as `PAYSTACK_SECRET_KEY`. Never put it in source code, `README.md`, screenshots, or Git history.

Local browsing can exercise the shop and order flow without a successful payment. A complete payment test must reach the Paystack API and return to the callback route at `/payment/callback`. For deployed or live payments, use a public HTTPS URL and the appropriate Paystack test/live credentials. A private `localhost` URL cannot be used by external services as a deployed callback endpoint.

## 8. Start and access the application

Start the development server from the project root:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

Use `Ctrl+C` in PowerShell to stop the server. `FLASK_DEBUG` is read from `.env`; leave it `false` unless actively debugging local code.

Register a customer from the site. To create an administrator, promote the account in MariaDB after registration:

```sql
UPDATE ebook_shop.users
SET role = 'Admin'
WHERE email = 'admin@example.com';
```

## 9. Windows-specific file and backup notes

- The repository’s existing `venv` directory contains Unix-style launchers and is not portable. The Windows `.venv` should remain local and is ignored by Git.
- Application upload paths are built with `os.path.join`, so Windows drive letters and backslashes are handled by the existing code.
- The application creates `static\uploads\ebooks` and `static\uploads\covers` when an admin uploads files. The two sample ebook files already in the repository are separate from future uploaded content.
- Back up the MariaDB database and `static\uploads\` together. The schema file is for initial setup and is not a production migration tool.
