from flask import Flask, render_template, request, session, redirect, url_for, send_from_directory
from flask_wtf.csrf import CSRFError, CSRFProtect

from database import get_connection

from werkzeug.security import generate_password_hash, check_password_hash

from werkzeug.utils import secure_filename

import psycopg
import os
import requests
import uuid
import posixpath
from urllib.parse import quote


app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("FLASK_SECRET_KEY must be configured")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv(
    "SESSION_COOKIE_SECURE", "false"
).lower() in {"1", "true", "yes"}

csrf = CSRFProtect(app)

# Check allowed ebook file types
ALLOWED_EBOOK_EXTENSIONS = {"pdf"}
ALLOWED_COVER_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


def allowed_ebook(filename):
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EBOOK_EXTENSIONS
    )


def allowed_cover(filename):
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_COVER_EXTENSIONS
    )


def valid_cover_signature(file_storage):
    file_storage.seek(0)
    signature = file_storage.read(12)
    file_storage.seek(0)
    extension = file_storage.filename.rsplit(".", 1)[-1].lower()

    if extension in {"jpg", "jpeg"}:
        return signature.startswith(b"\xff\xd8\xff")
    if extension == "png":
        return signature.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == "gif":
        return signature.startswith((b"GIF87a", b"GIF89a"))
    if extension == "webp":
        return signature.startswith(b"RIFF") and signature[8:12] == b"WEBP"
    return False


def error_response(message, status_code):
    return render_template("error.html", message=message), status_code


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_template(
        "error.html",
        message="Your form session expired or was invalid. Please try again.",
    ), 400


@app.before_request
def protect_ebook_static_files():
    if request.endpoint == "static":
        filename = (request.view_args or {}).get("filename", "")
        normalized_filename = posixpath.normpath("/" + filename).lstrip("/")
        if normalized_filename.startswith("uploads/ebooks/"):
            return "Not found", 404

# Home page
@app.route("/")
def home():

    # Connect to the database
    connection = get_connection()

    # Create a cursor and get all categories
    cursor = connection.cursor()

    cursor.execute("SELECT name FROM categories")
    categories = cursor.fetchall()

    # Get books with their category names
    cursor.execute("""
        SELECT
            books.id,
            books.title,
            books.author,
            books.price,
            categories.name
        FROM books
        JOIN categories
            ON books.category_id = categories.id
    """)

    books = cursor.fetchall()

    # Close the database connection
    cursor.close()
    connection.close()

    return render_template(
        "index.html",
        categories=categories,
        books=books
    )


# Book details page
@app.route("/books/<int:book_id>")
def book_details(book_id):

    # Connect to the database
    connection = get_connection()

    # Find the selected book
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            books.id,
            books.title,
            books.author,
            books.description,
            books.price,
            categories.name
        FROM books
        JOIN categories
            ON books.category_id = categories.id
        WHERE books.id = %s
    """, (book_id,))

    book = cursor.fetchone()

    # Check if the book exists
    if book is None:
        cursor.close()
        connection.close()
        return error_response("Book not found.", 404)

    # Close the database connection
    cursor.close()
    connection.close()

    return render_template(
        "book_details.html",
        book=book
    )


# Customer registration
@app.route("/register", methods=["GET", "POST"])
def register():

    # Check if the form was submitted
    if request.method == "POST":

        # Get data from the form
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return error_response("Name, email, and password are required.", 400)

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Save the customer to the database
        connection = get_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (name, email, password, role)
                VALUES (%s, %s, %s, %s)
            """, (name, email, hashed_password, "Customer"))

            connection.commit()

            return redirect(url_for("login", registered="1"))

        except psycopg.IntegrityError as error:

            connection.rollback()

            # Check if the email already exists
            if error.args[0] == 1062:
                return error_response(
                    "An account with this email already exists. Please use another email.",
                    409,
                )

            raise

        finally:
            # Close the database connection
            cursor.close()
            connection.close()

    # Show the registration page
    return render_template("customer/register.html")




# Customer login
@app.route("/login", methods=["GET", "POST"])
def login():

    # Check if the form was submitted
    if request.method == "POST":

        # Get data from the form
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Connect to the database
        connection = get_connection()
        cursor = connection.cursor()

        # Find the customer by email
        cursor.execute("""
            SELECT id, name, email, password, role
            FROM users
            WHERE email = %s
        """, (email,))

        user = cursor.fetchone()

        # Close the database connection
        cursor.close()
        connection.close()

        # Check if the customer exists
        if user is None:
            return error_response("Invalid email or password.", 401)

        # Check the password
        if check_password_hash(user[3], password):

            session["user_id"] = user[0]

            if user[4] == "Admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("customer_dashboard"))

        return error_response("Invalid email or password.", 401)

    # Show the login page
    return render_template("customer/login.html")



# Customer logout
@app.route("/logout", methods=["POST"])
def logout():

    # Remove the user ID from the session
    session.pop("user_id", None)

    return redirect(url_for("home"))


# Customer dashboard
@app.route("/customer")
def customer_dashboard():

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Find the logged-in customer
    cursor.execute("""
        SELECT name, email
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    # Close the database connection
    cursor.close()
    connection.close()

    # Check if the user exists
    if user is None:
        return error_response("User not found.", 404)

    return render_template(
        "customer/dashboard.html",
        user=user
    )


# Add book to cart
@app.route("/cart/add/<int:book_id>", methods=["POST"])
def add_to_cart(book_id):

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Check if the book exists
    cursor.execute("""
        SELECT id
        FROM books
        WHERE id = %s
    """, (book_id,))

    book = cursor.fetchone()

    # Check if the book exists
    if book is None:
        cursor.close()
        connection.close()
        return error_response("Book not found.", 404)

    # Check if the book is already in the cart
    cursor.execute("""
        SELECT id
        FROM cart
        WHERE user_id = %s AND book_id = %s
    """, (user_id, book_id))

    cart_item = cursor.fetchone()

    # Add the book if it is not already in the cart
    if cart_item is None:

        cursor.execute("""
            INSERT INTO cart (user_id, book_id, quantity)
            VALUES (%s, %s, %s)
        """, (user_id, book_id, 1))

        connection.commit()

        message = "Book added to cart"

    else:
        message = "Book is already in your cart"

    # Close the database connection
    cursor.close()
    connection.close()

    return render_template( "customer/cart_added.html", message=message)


# Customer cart
@app.route("/cart")
def cart():

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Get the customer's cart items
    cursor.execute("""
        SELECT
            cart.id,
            books.title,
            books.author,
            books.price,
            cart.quantity
        FROM cart
        JOIN books
            ON cart.book_id = books.id
        WHERE cart.user_id = %s
    """, (user_id,))

    cart_items = cursor.fetchall()

    # Calculate the cart total
    total = sum(item[3] * item[4] for item in cart_items)

    # Close the database connection
    cursor.close()
    connection.close()

    return render_template(
        "customer/cart.html",
        cart_items=cart_items,
        total=total
    )


# Remove book from cart
@app.route("/cart/remove/<int:cart_id>", methods=["POST"])
def remove_from_cart(cart_id):

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Remove the cart item belonging to this customer
    cursor.execute("""
        DELETE FROM cart
        WHERE id = %s AND user_id = %s
    """, (cart_id, user_id))

    connection.commit()

    # Close the database connection
    cursor.close()
    connection.close()

    return redirect(url_for("cart"))


# Update cart quantity
@app.route("/cart/update/<int:cart_id>", methods=["POST"])
def update_cart(cart_id):

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Get the new quantity from the form
    try:
        quantity = int(request.form.get("quantity", ""))
    except ValueError:
        return error_response("Enter a valid quantity.", 400)

    if quantity < 1:
        return error_response("Quantity must be at least 1.", 400)

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Update the customer's cart item
    cursor.execute("""
        UPDATE cart
        SET quantity = %s
        WHERE id = %s AND user_id = %s
    """, (quantity, cart_id, user_id))

    connection.commit()

    # Close the database connection
    cursor.close()
    connection.close()

    return redirect(url_for("cart"))


# Checkout page
@app.route("/checkout")
def checkout():

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Get the customer's cart items
    cursor.execute("""
        SELECT
            cart.book_id,
            books.title,
            books.price,
            cart.quantity
        FROM cart
        JOIN books
            ON cart.book_id = books.id
        WHERE cart.user_id = %s
    """, (user_id,))

    cart_items = cursor.fetchall()

    # Check if the cart is empty
    if not cart_items:
        cursor.close()
        connection.close()
        return error_response("Your cart is empty.", 400)

    # Calculate the total
    total = sum(item[2] * item[3] for item in cart_items)

    # Close the database connection
    cursor.close()
    connection.close()

    return render_template(
        "customer/checkout.html",
        cart_items=cart_items,
        total=total
    )


# Place customer order
@app.route("/order/place", methods=["POST"])
def place_order():

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Get the customer's cart items
    cursor.execute("""
        SELECT
            cart.book_id,
            books.price,
            cart.quantity
        FROM cart
        JOIN books
            ON cart.book_id = books.id
        WHERE cart.user_id = %s
    """, (user_id,))

    cart_items = cursor.fetchall()

    # Check if the cart is empty
    if not cart_items:
        cursor.close()
        connection.close()
        return error_response("Your cart is empty.", 400)

    # Calculate the order total
    total = sum(item[1] * item[2] for item in cart_items)

    # Create the order
    cursor.execute("""
        INSERT INTO orders (user_id, total_amount, status)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (user_id, total, "Pending"))

    # Get the new order ID
    order_id = cursor.fetchone()[0]

    # Create the order items
    for item in cart_items:

        cursor.execute("""
            INSERT INTO order_items
            (order_id, book_id, price, quantity)
            VALUES (%s, %s, %s, %s)
        """, (
            order_id,
            item[0],
            item[1],
            item[2]
        ))

    # Remove the customer's cart items
    cursor.execute("""
        DELETE FROM cart
        WHERE user_id = %s
    """, (user_id,))

    # Save all changes
    connection.commit()

    # Close the database connection
    cursor.close()
    connection.close()

    return redirect(url_for("order_details", order_id=order_id))


# Customer orders
@app.route("/orders")
def customer_orders():

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Get the customer's orders
    cursor.execute("""
        SELECT
            id,
            total_amount,
            status,
            created_at
        FROM orders
        WHERE user_id = %s
        ORDER BY created_at DESC
    """ , (user_id,))

    orders = cursor.fetchall()

    # Close the database connection
    cursor.close()
    connection.close()

    return render_template(
        "customer/orders.html",
        orders=orders
    )


# Order details page
@app.route("/orders/<int:order_id>")
def order_details(order_id):

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Get the selected order
    cursor.execute("""
        SELECT
            orders.id,
            orders.total_amount,
            orders.status,
            orders.created_at
        FROM orders
        WHERE orders.id = %s
        AND orders.user_id = %s
    """, (order_id, user_id))

    order = cursor.fetchone()

    # Check if the order exists
    if order is None:
        cursor.close()
        connection.close()
        return error_response("Order not found.", 404)

    # Get the books in the order
    cursor.execute("""
        SELECT
            books.title,
            books.author,
            order_items.price,
            order_items.quantity
        FROM order_items
        JOIN books
            ON order_items.book_id = books.id
        WHERE order_items.order_id = %s
    """, (order_id,))

    items = cursor.fetchall()

    # Close the database connection
    cursor.close()
    connection.close()

    return render_template(
        "customer/order_details.html",
        order=order,
        items=items
    )


# Pay for an order
@app.route("/pay/<int:order_id>", methods=["POST"])
def pay_order(order_id):

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Get the Paystack secret key
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        return error_response("Payment service is not configured.", 503)

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Get the customer's order
    cursor.execute("""
        SELECT
            orders.id,
            orders.total_amount,
            orders.status,
            users.email
        FROM orders
        JOIN users
            ON orders.user_id = users.id
        WHERE orders.id = %s
        AND orders.user_id = %s
    """, (order_id, user_id))

    order = cursor.fetchone()

    # Check if the order exists
    if order is None:
        cursor.close()
        connection.close()
        return error_response("Order not found.", 404)

    # Check if the order has already been paid
    if order[2] == "Paid":
        cursor.close()
        connection.close()
        return error_response("This order has already been paid.", 400)

    # Create a unique payment reference
    reference = f"ORDER-{order_id}-{uuid.uuid4().hex[:10]}"

    # Convert the order amount to kobo
    amount = int(order[1] * 100)

    # Prepare the Paystack request
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json"
    }

    data = {
        "email": order[3],
        "amount": amount,
        "reference": reference,
        "callback_url": url_for(
            "payment_callback",
            _external=True
        )
    }

    # Send the payment request to Paystack
    try:
        response = requests.post(
            "https://api.paystack.co/transaction/initialize",
            headers=headers,
            json=data,
            timeout=15,
        )
        result = response.json()
    except (requests.RequestException, ValueError):
        cursor.close()
        connection.close()
        return error_response("Unable to contact the payment service.", 502)

    # Check if Paystack accepted the request
    if not isinstance(result, dict) or not result.get("status"):
        cursor.close()
        connection.close()
        return error_response("Unable to initialize payment.", 502)

    authorization_url = (result.get("data") or {}).get("authorization_url")
    if not authorization_url:
        cursor.close()
        connection.close()
        return error_response("The payment service returned an invalid response.", 502)

    # Save the payment record
    cursor.execute("""
        INSERT INTO payments
        (order_id, reference, amount, status)
        VALUES (%s, %s, %s, %s)
    """, (
        order_id,
        reference,
        order[1],
        "Pending"
    ))

    connection.commit()

    # Close the database connection
    cursor.close()
    connection.close()

    # Send the customer to Paystack checkout
    return redirect(authorization_url)


# Verify Paystack payment
@app.route("/payment/callback")
def payment_callback():

    # Get the payment reference from Paystack
    reference = request.args.get("reference")

    # Check if a reference was provided
    if reference is None:
        return error_response("Payment reference missing.", 400)

    # Get the Paystack secret key
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        return error_response("Payment service is not configured.", 503)

    # Verify the transaction with Paystack
    headers = {
        "Authorization": f"Bearer {secret_key}"
    }

    try:
        response = requests.get(
            "https://api.paystack.co/transaction/verify/" + quote(reference, safe=""),
            headers=headers,
            timeout=15,
        )
        result = response.json()
    except (requests.RequestException, ValueError):
        return error_response("Unable to contact the payment service.", 502)

    # Check if verification was successful
    if not isinstance(result, dict) or not result.get("status"):
        return error_response("Payment verification failed.", 400)

    # Get transaction information
    transaction = result.get("data")

    # Check the payment status
    if not isinstance(transaction, dict) or transaction.get("status") != "success":
        return error_response("Payment was not successful.", 400)

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Find the payment record
    cursor.execute("""
        SELECT order_id, amount, status
        FROM payments
        WHERE reference = %s
    """, (reference,))

    payment = cursor.fetchone()

    # Check if the payment exists
    if payment is None:
        cursor.close()
        connection.close()
        return error_response("Payment record not found.", 404)

    # Verify that the Paystack amount matches our order amount
    if (
        transaction.get("reference") != reference
        or transaction.get("amount") != int(payment[1] * 100)
    ):
        cursor.close()
        connection.close()
        return error_response("Payment details did not match this order.", 400)

    # Check if the payment has already been processed
    if payment[2] == "Success":
        cursor.close()
        connection.close()

        return redirect(
            url_for(
                "order_details",
                order_id=payment[0]
            )
        )

    # Mark the payment as successful
    cursor.execute("""
        UPDATE payments
        SET status = %s,
            paid_at = NOW()
        WHERE reference = %s
    """, ("Success", reference))

    # Mark the order as paid
    cursor.execute("""
        UPDATE orders
        SET status = %s
        WHERE id = %s
    """, ("Paid", payment[0]))

    # Save the changes
    connection.commit()

    # Close the database connection
    cursor.close()
    connection.close()

    return redirect(
        url_for(
            "order_details",
            order_id=payment[0]
        )
    )


# Customer library
@app.route("/library")
def customer_library():

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Get books from paid orders
    cursor.execute("""
        SELECT
            books.id,
            books.title,
            books.author,
            books.cover_image
        FROM orders
        JOIN order_items
            ON orders.id = order_items.order_id
        JOIN books
            ON order_items.book_id = books.id
        WHERE orders.user_id = %s
        AND orders.status = %s
        GROUP BY
            books.id,
            books.title,
            books.author,
            books.cover_image
        ORDER BY MAX(orders.created_at) DESC
    """, (user_id, "Paid"))

    books = cursor.fetchall()

    # Close the database connection
    cursor.close()
    connection.close()

    return render_template(
        "customer/library.html",
        books=books
    )


# Download purchased ebook
@app.route("/library/download/<int:book_id>")
def download_ebook(book_id):

    # Get the user ID from the session
    user_id = session.get("user_id")

    # Check if the customer is logged in
    if user_id is None:
        return redirect(url_for("login"))

    # Connect to the database
    connection = get_connection()
    cursor = connection.cursor()

    # Check if the customer owns the ebook
    cursor.execute("""
        SELECT
            books.ebook_file
        FROM orders
        JOIN order_items
            ON orders.id = order_items.order_id
        JOIN books
            ON order_items.book_id = books.id
        WHERE orders.user_id = %s
        AND orders.status = %s
        AND books.id = %s
    """, (user_id, "Paid", book_id))

    book = cursor.fetchone()

    # Close the database connection
    cursor.close()
    connection.close()

    # Check if the customer owns the ebook
    if book is None:
        return error_response("You do not own this ebook.", 403)

    ebook_directory = os.path.join(
        app.root_path,
        "static",
        "uploads",
        "ebooks"
    )

    return send_from_directory(
        ebook_directory,
        book[0],
        as_attachment=True
    )

# Admin dashboard
@app.route("/admin")
def admin_dashboard():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT COUNT(*)
        FROM books
    """)

    total_books = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE role = %s
    """, ("Customer",))

    total_customers = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM orders
    """)

    total_orders = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(SUM(total_amount), 0)
        FROM orders
        WHERE status = %s
    """, ("Paid",))

    total_revenue = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return render_template(
        "admin/dashboard.html",
        user=user,
        total_books=total_books,
        total_customers=total_customers,
        total_orders=total_orders,
        total_revenue=total_revenue
    )

# Manage categories
@app.route("/admin/categories")
def manage_categories():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT id, name
        FROM categories
        ORDER BY name
    """)

    categories = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/categories.html",
        categories=categories
    )


# Add category
@app.route("/admin/categories/add", methods=["POST"])
def add_category():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    name = request.form["name"].strip()

    if not name:
        cursor.close()
        connection.close()
        return error_response("Category name is required.", 400)

    try:
        cursor.execute("""
            INSERT INTO categories (name)
            VALUES (%s)
        """, (name,))

        connection.commit()
    except psycopg.IntegrityError as error:
        connection.rollback()
        cursor.close()
        connection.close()
        if error.args[0] == 1062:
            return error_response("A category with that name already exists.", 409)
        raise

    cursor.close()
    connection.close()

    return redirect(url_for("manage_categories"))


# Admin orders
@app.route("/admin/orders")
def admin_orders():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT
            orders.id,
            users.name,
            users.email,
            orders.total_amount,
            orders.status,
            orders.created_at
        FROM orders
        JOIN users
            ON orders.user_id = users.id
        ORDER BY orders.created_at DESC
    """)

    orders = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/orders.html",
        orders=orders
    )


# Admin payments
@app.route("/admin/payments")
def admin_payments():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT
            payments.id,
            payments.order_id,
            users.name,
            users.email,
            payments.reference,
            payments.amount,
            payments.status,
            payments.paid_at
        FROM payments
        JOIN orders
            ON payments.order_id = orders.id
        JOIN users
            ON orders.user_id = users.id
        ORDER BY payments.id DESC
    """)

    payments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/payments.html",
        payments=payments
    )



# Admin customer
@app.route("/admin/customers")
def admin_customers():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            role,
            created_at
        FROM users
        WHERE role = %s
        ORDER BY created_at DESC
    """, ("Customer",))

    customers = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/customers.html",
        customers=customers
    )


# Admin customer details
@app.route("/admin/customers/<int:customer_id>")
def admin_customer_details(customer_id):

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            created_at
        FROM users
        WHERE id = %s
        AND role = %s
    """, (customer_id, "Customer"))

    customer = cursor.fetchone()

    if customer is None:
        cursor.close()
        connection.close()
        return error_response("Customer not found.", 404)

    cursor.execute("""
        SELECT
            id,
            total_amount,
            status,
            created_at
        FROM orders
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (customer_id,))

    orders = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/customer_details.html",
        customer=customer,
        orders=orders
    )

# Edit customer
@app.route("/admin/customers/edit/<int:customer_id>", methods=["GET", "POST"])
def edit_customer(customer_id):

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT
            id,
            name,
            email
        FROM users
        WHERE id = %s
        AND role = %s
    """, (customer_id, "Customer"))

    customer = cursor.fetchone()

    if customer is None:
        cursor.close()
        connection.close()
        return error_response("Customer not found.", 404)

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip()

        if not name or not email:
            cursor.close()
            connection.close()
            return error_response("Name and email are required.", 400)

        try:
            cursor.execute("""
                UPDATE users
                SET name = %s,
                    email = %s
                WHERE id = %s
                AND role = %s
            """, (name, email, customer_id, "Customer"))

            connection.commit()
        except psycopg.IntegrityError as error:
            connection.rollback()
            cursor.close()
            connection.close()
            if error.args[0] == 1062:
                return error_response("An account with this email already exists.", 409)
            raise

        cursor.close()
        connection.close()

        return redirect(
            url_for(
                "admin_customer_details",
                customer_id=customer_id
            )
        )

    cursor.close()
    connection.close()

    return render_template(
        "admin/edit_customer.html",
        customer=customer
    )




# Delete customer
@app.route("/admin/customers/delete/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT id
        FROM users
        WHERE id = %s
        AND role = %s
    """, (customer_id, "Customer"))

    customer = cursor.fetchone()

    if customer is None:
        cursor.close()
        connection.close()
        return error_response("Customer not found.", 404)

    cursor.execute("""
        SELECT id
        FROM orders
        WHERE user_id = %s
        LIMIT 1
    """, (customer_id,))

    order = cursor.fetchone()

    if order is not None:
        cursor.close()
        connection.close()
        return error_response(
            "This customer cannot be deleted because they have orders.", 400
        )

    cursor.execute("""
        DELETE FROM users
        WHERE id = %s
        AND role = %s
    """, (customer_id, "Customer"))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("admin_customers"))

# Admin order details
@app.route("/admin/orders/<int:order_id>")
def admin_order_details(order_id):

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT
            orders.id,
            users.name,
            users.email,
            orders.total_amount,
            orders.status,
            orders.created_at,
            users.id
        FROM orders
        JOIN users
            ON orders.user_id = users.id
        WHERE orders.id = %s
    """, (order_id,))

    order = cursor.fetchone()

    if order is None:
        cursor.close()
        connection.close()
        return error_response("Order not found.", 404)

    cursor.execute("""
        SELECT
            books.title,
            books.author,
            order_items.price,
            order_items.quantity
        FROM order_items
        JOIN books
            ON order_items.book_id = books.id
        WHERE order_items.order_id = %s
    """, (order_id,))

    items = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/order_details.html",
        order=order,
        items=items
    )




# Update order status
@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
def update_order_status(order_id):

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT id
        FROM orders
        WHERE id = %s
    """, (order_id,))

    order = cursor.fetchone()

    if order is None:
        cursor.close()
        connection.close()
        return error_response("Order not found.", 404)

    status = request.form["status"]

    if status not in ["Pending", "Paid", "Cancelled"]:
        cursor.close()
        connection.close()
        return error_response("Invalid order status.", 400)

    # Paid orders must have a successful payment
    if status == "Paid":

        cursor.execute("""
            SELECT id
            FROM payments
            WHERE order_id = %s
            AND status = 'Success'
        """, (order_id,))

        payment = cursor.fetchone()

        if payment is None:
            cursor.close()
            connection.close()
            return error_response(
                "This order cannot be marked as Paid without a successful payment.",
                400,
            )



    cursor.execute("""
        UPDATE orders
        SET status = %s
        WHERE id = %s
    """, (status, order_id))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(
        url_for(
            "admin_order_details",
            order_id=order_id
        )
    )


# Manage ebooks
@app.route("/admin/books")
def manage_books():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT
            books.id,
            books.title,
            books.author,
            books.price,
            books.cover_image,
            categories.name
        FROM books
        JOIN categories
            ON books.category_id = categories.id
        ORDER BY books.created_at DESC
    """)

    books = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/books.html",
        books=books
    )


# Add ebook page
@app.route("/admin/books/add", methods=["GET", "POST"])
def add_book():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT id, name
        FROM categories
        ORDER BY name
    """)

    categories = cursor.fetchall()

    cursor.close()
    connection.close()

    if request.method == "POST":

        title = request.form["title"]
        author = request.form["author"]
        description = request.form["description"]
        category_id = request.form["category_id"]
        price = request.form["price"]

        cover_image = request.files.get("cover_image")
        ebook_file = request.files.get("ebook_file")

        
        if ebook_file is None or ebook_file.filename == "":
            return error_response("Ebook PDF is required.", 400)

        # Check that the ebook is a PDF
        if not allowed_ebook(ebook_file.filename):
            return error_response("Only PDF ebook files are allowed.", 400)

        # Check that the file content is actually a PDF
        ebook_file.seek(0)
        file_signature = ebook_file.read(4)
        ebook_file.seek(0)

        if file_signature != b"%PDF":
            return error_response("The uploaded file is not a valid PDF.", 400)

        ebook_filename = secure_filename(ebook_file.filename)
        if not ebook_filename:
            return error_response("The ebook filename is invalid.", 400)

        # Give the ebook a unique filename
        ebook_filename = f"{uuid.uuid4()}_{ebook_filename[:180]}"




        if cover_image and cover_image.filename:
            if not allowed_cover(cover_image.filename):
                return error_response(
                    "Cover images must be JPG, PNG, GIF, or WebP files.", 400
                )

            if not valid_cover_signature(cover_image):
                return error_response("The uploaded cover is not a valid image.", 400)

            cover_filename = secure_filename(cover_image.filename)
            if not cover_filename:
                return error_response("The cover filename is invalid.", 400)
            cover_filename = f"{uuid.uuid4()}_{cover_filename[:180]}"
        else:
            cover_filename = None

        ebook_directory = os.path.join(
            app.root_path,
            "static",
            "uploads",
            "ebooks"
        )

        cover_directory = os.path.join(
            app.root_path,
            "static",
            "uploads",
            "covers"
        )

        os.makedirs(ebook_directory, exist_ok=True)
        os.makedirs(cover_directory, exist_ok=True)

        ebook_file.save(
            os.path.join(ebook_directory, ebook_filename)
        )

        if cover_filename:
            cover_image.save(
                os.path.join(cover_directory, cover_filename)
            )

        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO books
            (
                title,
                author,
                description,
                category_id,
                price,
                cover_image,
                ebook_file
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            title,
            author,
            description,
            category_id,
            price,
            cover_filename,
            ebook_filename
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("manage_books"))

    return render_template(
        "admin/add_book.html",
        categories=categories
    )


# Edit ebook
@app.route("/admin/books/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT
            id,
            title,
            author,
            description,
            category_id,
            price
        FROM books
        WHERE id = %s
    """, (book_id,))

    book = cursor.fetchone()

    if book is None:
        cursor.close()
        connection.close()
        return error_response("Ebook not found.", 404)

    cursor.execute("""
        SELECT id, name
        FROM categories
        ORDER BY name
    """)

    categories = cursor.fetchall()

    if request.method == "POST":

        title = request.form["title"]
        author = request.form["author"]
        description = request.form["description"]
        category_id = request.form["category_id"]
        price = request.form["price"]

        cursor.execute("""
            UPDATE books
            SET
                title = %s,
                author = %s,
                description = %s,
                category_id = %s,
                price = %s
            WHERE id = %s
        """, (
            title,
            author,
            description,
            category_id,
            price,
            book_id
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("manage_books"))

    cursor.close()
    connection.close()

    return render_template(
        "admin/edit_book.html",
        book=book,
        categories=categories
    )


# Delete ebook
@app.route("/admin/books/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT role
        FROM users
        WHERE id = %s
    """, (user_id,))

    user = cursor.fetchone()

    if user is None:
        cursor.close()
        connection.close()
        return error_response("User not found.", 404)

    if user[0] != "Admin":
        cursor.close()
        connection.close()
        return error_response("Access denied.", 403)

    cursor.execute("""
        SELECT ebook_file, cover_image
        FROM books
        WHERE id = %s
    """, (book_id,))

    book = cursor.fetchone()

    # Check if the ebook has been purchased
    cursor.execute("""
        SELECT id
        FROM order_items
        WHERE book_id = %s
        LIMIT 1
    """, (book_id,))

    purchased = cursor.fetchone()

    if purchased is not None:
        cursor.close()
        connection.close()
        return error_response("This ebook cannot be deleted because it has been purchased.", 400)

    # Check if the ebook exists
    if book is None:
        cursor.close()
        connection.close()
        return error_response("Ebook not found.", 404)

    cursor.execute("""
        DELETE FROM books
        WHERE id = %s
    """, (book_id,))

    connection.commit()

    cursor.close()
    connection.close()

    ebook_directory = os.path.join(
        app.root_path,
        "static",
        "uploads",
        "ebooks"
    )

    safe_ebook_filename = secure_filename(book[0])
    ebook_path = os.path.join(ebook_directory, safe_ebook_filename)

    if safe_ebook_filename and os.path.isfile(ebook_path):
        os.remove(ebook_path)

    if book[1]:

        cover_directory = os.path.join(
            app.root_path,
            "static",
            "uploads",
            "covers"
        )

        safe_cover_filename = secure_filename(book[1])
        cover_path = os.path.join(cover_directory, safe_cover_filename)

        if safe_cover_filename and os.path.isfile(cover_path):
            os.remove(cover_path)

    return redirect(url_for("manage_books"))


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"}
    app.run(debug=debug)
