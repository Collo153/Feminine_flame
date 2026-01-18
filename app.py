from flask import Flask,request, jsonify, render_template, request, redirect, url_for, session, current_app
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime 
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import uuid
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from bson.errors import InvalidId
import stripe
import ssl


# Load environment variables
load_dotenv()

# === STRIPE CONFIGURATION ===
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
stripe_pub_key = os.getenv("STRIPE_PUBLISHABLE_KEY")

# === UTILITY: Make MongoDB docs JSON-safe ===
def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    doc['_id'] = str(doc['_id'])
    return doc

# Initialize Flask app
app = Flask(__name__, template_folder='Templates')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-secret-key-change-in-production")

# === EMAIL CONFIGURATION ===
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')
mail = Mail(app)

# === IMAGE/EBOOK UPLOAD CONFIG ===
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'epub', 'mobi'}
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'ebooks'), exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# === MONGODB CONNECTION (CORRECT SSL CONFIG FOR ATLAS) ===
MONGO_URI = os.getenv("MONGO_URI")

if MONGO_URI and "mongodb.net" in MONGO_URI:
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsCAFile=None,
        ssl_context=ssl_context
    )
else:
    client = MongoClient(MONGO_URI or "mongodb://localhost:27017")

db = client.Feminine_flame

# === CREATE ADMIN USER ===
admin_exists = db.users.find_one({"email": "feminineflame19@gmail.com"})
if not admin_exists:
    admin_user = {
        "email": "feminineflame19@gmail.com",
        "password_hash": generate_password_hash("MaAlma26."),
        "role": "admin",
        "is_active": True
    }
    db.users.insert_one(admin_user)
    print("✅ Admin user created!")

# === SEED SAMPLE DATA ===
if db.products.count_documents({}) == 0:
    db.products.insert_many([
        {
            "name": "Velvet Bloom",
            "description": "A rich floral blend with notes of rose, amber, and vanilla.",
            "category": "perfume",
            "price": 89.00,
            "stock": 25,
            "image_url": "",
            "is_active": True,
            "created_at": datetime.utcnow()
        },
        {
            "name": "Midnight Whisper",
            "description": "Mysterious and sensual — oud, sandalwood, and musk.",
            "category": "perfume",
            "price": 75.00,
            "stock": 15,
            "image_url": "",
            "is_active": True,
            "created_at": datetime.utcnow()
        },
        {
            "name": "The Silent Poet",
            "description": "A soul-stirring eBook about love, loss, and rebirth.",
            "category": "ebook",
            "price": 9.99,
            "stock": -1,
            "image_url": "",
            "is_active": True,
            "created_at": datetime.utcnow()
        }
    ])
    print("✅ Sample products added!")


# === STRIPE CHECKOUT SESSION ===
@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        data = request.get_json()
        name = data.get('name')
        phone = data.get('phone')
        address = data.get('address')
        country = data.get('country')
        email = data.get('email', '')

        if not all([name, phone, address, country]):
            return jsonify(error="All fields are required"), 400

        cart = session.get('cart', [])
        if not cart:
            return jsonify(error="Cart is empty"), 400

        total = sum(item['price'] * item['quantity'] for item in cart)

        # ✅ CREATE ORDER IN DB FIRST
        order = {
            "customer_name": name,
            "phone": phone,
            "address": address,
            "country": country,
            "email": email,
            "payment_method": "stripe",
            "items": cart,
            "total": total,
            "status": "pending",
            "created_at": datetime.utcnow()
        }
        result = db.orders.insert_one(order)
        order_id = str(result.inserted_id)
        session['order_id'] = order_id  # Save for webhook

        # Create Stripe session
        session_obj = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "gbp",
                    "product_data": {"name": "Feminine Flame Order"},
                    "unit_amount": int(total * 100),  # Convert to pence
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=url_for("payment_success", _external=True),
            cancel_url=url_for("checkout", _external=True),
            customer_email=email,
            client_reference_id=order_id,  # Critical for webhook
        )
        return jsonify({"id": session_obj.id})
    
    except Exception as e:
        print("Stripe error:", str(e))
        return jsonify(error=str(e)), 400


# === STRIPE WEBHOOK ===
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        if session_obj["payment_status"] == "paid":
            order_id = session_obj.get("client_reference_id")
            if order_id:
                db.orders.update_one(
                    {"_id": ObjectId(order_id)},
                    {"$set": {"status": "paid", "payment_status": "completed"}}
                )

    return jsonify({"status": "success"})


# === PAYMENT SUCCESS ===
@app.route("/payment-success")
def payment_success():
    session.pop('cart', None)
    session.pop('order_id', None)
    return render_template("Customer/success.html")


# === M-PESA DARAJA ROUTES ===
@app.route("/initiate-mpesa", methods=["POST"])
def initiate_mpesa():
    try:
        data = request.get_json()
        phone = data["phone"]
        amount = data["amount"]
        order_id = data["order_id"]

        from mpesa_daraja import send_stk_push
        response = send_stk_push(
            phone=phone,
            amount=amount,
            account_reference=order_id,
            transaction_desc="Feminine Flame Order"
        )
        return jsonify({"success": True, "message": "M-Pesa prompt sent!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/mpesa-callback", methods=["POST"])
def mpesa_callback():
    try:
        data = request.get_json()
        result_code = data["Body"]["stkCallback"]["ResultCode"]
        callback_metadata = data["Body"]["stkCallback"].get("CallbackMetadata", {}).get("Item", [])
        order_id = None
        for item in callback_metadata:
            if item.get("Name") == "AccountReference":
                order_id = item.get("Value")
                break

        if result_code == 0 and order_id:
            db.orders.update_one(
                {"_id": ObjectId(order_id)},
                {"$set": {"status": "paid", "payment_status": "completed"}}
            )
        elif order_id:
            db.orders.update_one(
                {"_id": ObjectId(order_id)},
                {"$set": {"status": "failed", "payment_status": "failed"}}
            )

        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})
    except Exception as e:
        current_app.logger.error(f"M-Pesa callback error: {str(e)}")
        return jsonify({"ResultCode": 1, "ResultDesc": "Error occurred"}), 500


# === HOMEPAGE ===
@app.route('/')
def home():
    all_products = list(db.products.find({"is_active": True}))
    perfumes = [serialize_doc(p) for p in all_products if p.get('category') == 'perfume']
    ebooks = [serialize_doc(p) for p in all_products if p.get('category') == 'ebook']
    return render_template('Customer/index.html', perfumes=perfumes, ebooks=ebooks)


# === CART MANAGEMENT ===
@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    return render_template('Customer/cart.html', cart=cart_items, total=total)

@app.route('/update-cart', methods=['POST'])
def update_cart():
    cart = session.get('cart', [])
    data = request.get_json()
    product_id = data['product_id']
    change = data['change']
    
    for item in cart:
        if item['id'] == product_id:
            item['quantity'] = max(1, item['quantity'] + change)
            if item['quantity'] == 0:
                cart = [i for i in cart if i['id'] != product_id]
            break
    
    session['cart'] = cart
    total = sum(item['price'] * item['quantity'] for item in cart)
    return jsonify({"success": True, "total": total})

@app.route('/remove-from-cart', methods=['POST'])
def remove_from_cart():
    cart = session.get('cart', [])
    data = request.get_json()
    product_id = data['product_id']
    
    cart = [item for item in cart if item['id'] != product_id]
    session['cart'] = cart
    total = sum(item['price'] * item['quantity'] for item in cart)
    return jsonify({"success": True, "total": total})

@app.route('/sync-cart', methods=['POST'])
def sync_cart():
    data = request.get_json()
    session['cart'] = data['cart']
    return jsonify({"success": True})


# === CHECKOUT ===
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        country = request.form.get('country')
        email = request.form.get('email')

        if not all([name, phone, address, country]):
            return "All fields are required", 400

        cart = session.get('cart', [])
        if not cart:
            return "Cart is empty", 400

        total = sum(item['price'] * item['quantity'] for item in cart)

        order = {
            "customer_name": name,
            "phone": phone,
            "address": address,
            "country": country,
            "email": email,
            "payment_method": 'mpesa' if country == 'Kenya' else 'stripe',
            "items": cart,
            "total": total,
            "status": "pending",
            "created_at": datetime.utcnow()
        }
        result = db.orders.insert_one(order)
        order_id = str(result.inserted_id)

        # === EMAIL NOTIFICATIONS ===
        try:
            admin_msg = Message(
                subject="🆕 New Order - Feminine Flame",
                recipients=[os.getenv('MAIL_USERNAME')]
            )
            admin_msg.html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px;">
                <h2 style="color: #c25e7d;">New Order Received!</h2>
                <p><strong>Order ID:</strong> {order_id}</p>
                <p><strong>Customer:</strong> {name}</p>
                <p><strong>Email:</strong> {email or 'Not provided'}</p>
                <p><strong>Phone:</strong> {phone}</p>
                <p><strong>Country:</strong> {country}</p>
                <p><strong>Address:</strong> {address}</p>
                <p><strong>Total:</strong> {"KES" if country=="Kenya" else "GBP"} {total:.2f}</p>
                <p><strong>Payment Method:</strong> {"M-Pesa" if country=="Kenya" else "Stripe"}</p>
                <p><a href="http://127.0.0.1:5000/admin?tab=orders" style="background: #c25e7d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">View in Admin</a></p>
            </div>
            """
            mail.send(admin_msg)
        except Exception as e:
            print(f"📧 Admin email failed: {str(e)}")

        if email:
            try:
                customer_msg = Message(
                    subject="Feminine Flame - Order Confirmation",
                    recipients=[email]
                )
                customer_msg.html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px;">
                    <h2 style="color: #c25e7d;">Thank You, {name}!</h2>
                    <p>Your order has been received.</p>
                    <p><strong>Payment:</strong> {"You'll receive an M-Pesa prompt shortly" if country=="Kenya" else "You'll be redirected to secure payment"}</p>
                    <p>We'll contact you soon at <strong>{phone}</strong>.</p>
                </div>
                """
                mail.send(customer_msg)
            except Exception as e:
                print(f"📧 Customer email failed: {str(e)}")

        session['order_id'] = order_id

        if country == "Kenya":
            try:
                from mpesa_daraja import send_stk_push
                send_stk_push(
                    phone=phone,
                    amount=total,
                    account_reference=order_id,
                    transaction_desc="Feminine Flame Order"
                )
                session.pop('cart', None)
                return f"""
                <div style="max-width: 600px; margin: 3rem auto; padding: 2rem; text-align: center; font-family: Arial, sans-serif;">
                    <h2>✅ M-Pesa Prompt Sent!</h2>
                    <p>Please complete payment on your phone.</p>
                    <p>Order ID: {order_id}</p>
                    <a href="/" style="display: inline-block; margin-top: 1.5rem; padding: 0.6rem 1.2rem; background: #c25e7d; color: white; text-decoration: none; border-radius: 30px;">Back to Home</a>
                </div>
                """
            except Exception as e:
                return f"<h2>⚠️ M-Pesa failed: {str(e)}</h2>"
        else:
            # For UK: return JSON so frontend can trigger Stripe
            return jsonify({"error": "Use Stripe checkout"}), 400

    # GET request
    product_id = request.args.get('product_id')
    if product_id:
        try:
            obj_id = ObjectId(product_id)
            product = db.products.find_one({"_id": obj_id})
            if product:
                session['cart'] = [{
                    "id": str(product["_id"]),
                    "name": product["name"],
                    "price": product["price"],
                    "quantity": 1
                }]
        except Exception as e:
            print(f"⚠️ Invalid product_id: {product_id}")

    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart) if cart else 0
    return render_template('Customer/checkout.html', cart=cart, total=total, stripe_pub_key=stripe_pub_key)


# === ADMIN PANEL ===
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.args.get('action') == 'logout':
        session.pop('admin_logged_in', None)
        return redirect(url_for('admin'))

    if request.method == 'POST' and not session.get('admin_logged_in'):
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.users.find_one({"email": email, "role": "admin"})
        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        return "Invalid email or password", 401

    if not session.get('admin_logged_in'):
        return render_template('Admin/admin.html', page='login')

    # Delete product
    if request.args.get('action') == 'delete' and request.args.get('type') == 'product':
        db.products.delete_one({"_id": ObjectId(request.args.get('id'))})
        return redirect(url_for('admin', tab='products'))

    # Add/update product
    if request.method == 'POST' and request.form.get('name'):
        category = request.form.get('category', 'perfume')
        upload_subfolder = 'ebooks' if category == 'ebook' else ''
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], upload_subfolder)
        os.makedirs(upload_path, exist_ok=True)

        image_filename = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                file.save(os.path.join(upload_path, unique_filename))
                image_filename = f"ebooks/{unique_filename}" if upload_subfolder else unique_filename

        if not image_filename and request.form.get('product_id'):
            existing = db.products.find_one({"_id": ObjectId(request.form.get('product_id'))})
            image_filename = existing.get('image_url', '')

        stock = -1 if category == 'ebook' else int(request.form['stock'])

        data = {
            "name": request.form['name'],
            "description": request.form['description'],
            "category": category,
            "price": float(request.form['price']),
            "stock": stock,
            "image_url": image_filename,
            "is_active": True
        }

        product_id = request.form.get('product_id')
        if product_id:
            db.products.update_one({"_id": ObjectId(product_id)}, {"$set": data})
        else:
            data["created_at"] = datetime.utcnow()
            db.products.insert_one(data)
        return redirect(url_for('admin', tab='products'))

    # Update order status
    if request.method == 'POST' and request.form.get('order_id'):
        db.orders.update_one(
            {"_id": ObjectId(request.form['order_id'])},
            {"$set": {"status": "delivered"}}
        )
        return redirect(url_for('admin', tab='orders'))

    tab = request.args.get('tab', 'dashboard')
    products = list(db.products.find()) if tab == 'products' else []
    orders = list(db.orders.find().sort("created_at", -1)) if tab == 'orders' else []
    edit_product = None
    if request.args.get('edit'):
        edit_product = db.products.find_one({"_id": ObjectId(request.args.get('edit'))})
        if edit_product:
            edit_product = serialize_doc(edit_product)

    return render_template(
        'Admin/admin.html',
        page='dashboard',
        tab=tab,
        products=[serialize_doc(p) for p in products],
        orders=orders,
        edit_product=edit_product
    )


# === DEBUG ROUTE ===
@app.route('/test-db')
def test_db():
    try:
        db.list_collection_names()
        return "✅ Connected to MongoDB!"
    except Exception as e:
        return f"❌ Error: {str(e)}"  


if __name__ == '__main__':
    app.run(debug=True)