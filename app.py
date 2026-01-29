from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import uuid
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import stripe
import ssl
import io
from cryptography.fernet import Fernet # type: ignore
from datetime import datetime

# Load environment variables
load_dotenv()

# === STRIPE CONFIGURATION ===
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
stripe_pub_key = os.getenv("STRIPE_PUBLISHABLE_KEY")

# === EBOOK ENCRYPTION KEY ===
EBOOK_ENCRYPTION_KEY = os.getenv("EBOOK_ENCRYPTION_KEY")
if not EBOOK_ENCRYPTION_KEY:
    # Generate a new key if not exists (store this in .env for production)
    EBOOK_ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"[WARNING] NEW ENCRYPTION KEY GENERATED: {EBOOK_ENCRYPTION_KEY}")
    print("[WARNING] Add this to your .env file as EBOOK_ENCRYPTION_KEY")

cipher = Fernet(EBOOK_ENCRYPTION_KEY.encode())

# === UTILITY: Make MongoDB docs JSON-safe ===
def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    if '_id' in doc:
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
ALLOWED_EBOOK_EXTENSIONS = {'pdf', 'epub', 'mobi'}
UPLOAD_FOLDER = os.path.join('static', 'uploads')
EBOOK_FOLDER = os.path.join('protected_ebooks')  # Encrypted ebooks stored separately
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['EBOOK_FOLDER'] = EBOOK_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max for ebooks

# Create directories only on local development
# (Vercel file system is ephemeral, use S3/cloud storage in production)
if not os.getenv('VERCEL'):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(EBOOK_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_ebook_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EBOOK_EXTENSIONS

# === MONGODB CONNECTION ===
MONGO_URI = os.getenv("MONGO_URI")
client = None
db = None

def get_db():
    """Get MongoDB connection with lazy initialization"""
    global client, db
    if client is None:
        try:
            if MONGO_URI and "mongodb.net" in MONGO_URI:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                client = MongoClient(MONGO_URI, tls=True, ssl_context=ssl_context, serverSelectionTimeoutMS=5000)
            else:
                client = MongoClient(MONGO_URI or "mongodb://localhost:27017", serverSelectionTimeoutMS=5000)
            
            # Test connection
            client.admin.command('ping')
            db = client.Feminine_flame
            print("[OK] MongoDB connected successfully")
        except Exception as e:
            print(f"[WARNING] MongoDB connection warning: {str(e)}")
            print("[WARNING] Continuing with limited functionality...")
    return db

# === LAZY INITIALIZATION ===
_initialized = False

def initialize_db():
    """Initialize database (admin user, sample data) - runs once per cold start"""
    global _initialized
    if _initialized:
        return
    
    try:
        database = get_db()
        if database is None:
            print("[WARNING] Database not available, skipping initialization")
            _initialized = True
            return
        
        # === CREATE ADMIN USER ===
        admin_exists = database.users.find_one({"email": "feminineflame19@gmail.com"})
        if not admin_exists:
            admin_user = {
                "email": "feminineflame19@gmail.com",
                "password_hash": generate_password_hash("MaAlma26."),
                "role": "admin",
                "is_active": True
            }
            database.users.insert_one(admin_user)
            print("[OK] Admin user created!")
        
        # === SEED SAMPLE DATA ===
        if database.products.count_documents({}) == 0:
            database.products.insert_many([
                {
                    "name": "Velvet Bloom",
                    "description": "A rich floral blend with notes of rose, amber, and vanilla.",
                    "category": "perfume",
                    "price": 89.00,
                    "stock": 25,
                    "image_url": "",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc)
                },
                {
                    "name": "Midnight Whisper",
                    "description": "Mysterious and sensual — oud, sandalwood, and musk.",
                    "category": "perfume",
                    "price": 75.00,
                    "stock": 15,
                    "image_url": "",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc)
                },
                {
                    "name": "The Silent Poet",
                    "description": "A soul-stirring eBook about love, loss, and rebirth.",
                    "category": "ebook",
                    "price": 9.99,
                    "stock": -1,
                    "image_url": "",
                    "preview_text": "In the quiet corners of my heart, where shadows dance with light, I found words that refused to stay silent. This is not just a story; it's a journey through the corridors of love, where every step echoes with memories...",
                    "file_path": "",  # Will be added when uploading actual ebook
                    "file_type": "pdf",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc)
                }
            ])
            print("[OK] Sample products added!")
        
        _initialized = True
    except Exception as e:
        print(f"[WARNING] Database initialization failed (continuing anyway): {str(e)}")
        _initialized = True  # Mark as attempted to avoid retry loop

# === BEFORE REQUEST: Ensure DB connection ===
@app.before_request
def before_request():
    """Initialize DB connection before each request"""
    global db
    if db is None:
        db = get_db()
    if db is not None:
        initialize_db()

# === GLOBAL ERROR HANDLER ===
@app.errorhandler(500)
def handle_500_error(e):
    """Handle unhandled exceptions to prevent FUNCTION_INVOCATION_FAILED"""
    print(f"[ERROR] Error: {str(e)}")
    try:
        return render_template('Customer/error.html', 
                             message='An unexpected error occurred. Please try again.'), 500
    except:
        return "Internal Server Error", 500

# === EBOOK UPLOAD ROUTE ===
@app.route('/admin/upload-ebook', methods=['POST'])
def upload_ebook():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'ebook_file' not in request.files:
        return jsonify({'error': 'No ebook file uploaded'}), 400
    
    file = request.files['ebook_file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_ebook_file(file.filename):
        try:
            # Read file content
            file_content = file.read()
            
            # Encrypt the file
            encrypted_data = cipher.encrypt(file_content)
            
            # Generate unique filename
            original_filename = secure_filename(file.filename)
            file_ext = original_filename.rsplit('.', 1)[1].lower()
            encrypted_filename = f"{uuid.uuid4().hex}.{file_ext}"
            encrypted_path = os.path.join(app.config['EBOOK_FOLDER'], encrypted_filename)
            
            # Save encrypted file
            with open(encrypted_path, 'wb') as f:
                f.write(encrypted_data)
            
            return jsonify({
                'success': True,
                'file_path': encrypted_filename,
                'file_type': file_ext,
                'file_size': len(file_content)
            })
            
        except Exception as e:
            return jsonify({'error': f'Upload failed: {str(e)}'}), 500
    
    return jsonify({'error': 'Invalid file type. Only PDF, EPUB, MOBI allowed'}), 400

# === EBOOK DETAIL PAGE ===
@app.route('/ebook/<ebook_id>')
def ebook_detail(ebook_id):
    try:
        ebook = db.products.find_one({"_id": ObjectId(ebook_id), "category": "ebook", "is_active": True})
        
        if not ebook:
            return render_template('Customer/404.html'), 404
        
        # Check if user has purchased this ebook
        user_email = session.get('user_email')  # You might need to implement user login
        has_purchased = False
        
        if user_email:
            # Check orders for this ebook
            orders = db.orders.find({
                "email": user_email,
                "status": {"$in": ["paid", "completed", "delivered"]},
                "items": {"$elemMatch": {"id": ebook_id}}
            })
            has_purchased = orders.count() > 0
        
        # Get preview text (first 300 characters)
        preview_text = ebook.get('preview_text', '')
        show_full_preview = len(preview_text) > 300
        preview_display = preview_text[:300] + '...' if show_full_preview else preview_text
        
        return render_template(
            'Customer/ebook_detail.html',
            ebook=serialize_doc(ebook),
            has_purchased=has_purchased,
            preview_text=preview_display,
            show_full_preview=show_full_preview
        )
    except Exception as e:
        print(f"Error loading ebook detail: {str(e)}")
        return render_template('Customer/404.html'), 404

# === EBOOK PREVIEW API ===
@app.route('/api/ebook/<ebook_id>/preview')
def ebook_preview(ebook_id):
    try:
        ebook = db.products.find_one({"_id": ObjectId(ebook_id), "category": "ebook"})
        
        if not ebook or not ebook.get('preview_text'):
            return jsonify({'error': 'No preview available'}), 404
        
        preview_text = ebook['preview_text']
        return jsonify({
            'success': True,
            'title': ebook['name'],
            'preview': preview_text,
            'preview_length': len(preview_text)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === SECURE EBOOK DOWNLOAD ===
@app.route('/ebook/<ebook_id>/download')
def download_ebook(ebook_id):
    try:
        # Check if user is logged in
        user_email = session.get('user_email')
        if not user_email:
            return redirect(url_for('login', next=url_for('ebook_detail', ebook_id=ebook_id)))
        
        # Verify purchase
        orders = db.orders.find({
            "email": user_email,
            "status": {"$in": ["paid", "completed", "delivered"]},
            "items": {"$elemMatch": {"id": ebook_id}}
        })
        
        if orders.count() == 0:
            return render_template('Customer/error.html', 
                                 message='You need to purchase this ebook first'), 403
        
        # Get ebook details
        ebook = db.products.find_one({"_id": ObjectId(ebook_id), "category": "ebook"})
        
        if not ebook:
            return render_template('Customer/404.html'), 404
        
        # Get encrypted file path
        encrypted_filename = ebook.get('file_path')
        if not encrypted_filename:
            return render_template('Customer/error.html', 
                                 message='Ebook file not found'), 404
        
        encrypted_path = os.path.join(app.config['EBOOK_FOLDER'], encrypted_filename)
        
        if not os.path.exists(encrypted_path):
            return render_template('Customer/error.html', 
                                 message='Ebook file not found on server'), 404
        
        # Decrypt file
        try:
            with open(encrypted_path, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = cipher.decrypt(encrypted_data)
            
            # Create file-like object for sending
            file_stream = io.BytesIO(decrypted_data)
            file_stream.seek(0)
            
            # Determine MIME type
            file_type = ebook.get('file_type', 'pdf')
            mime_types = {
                'pdf': 'application/pdf',
                'epub': 'application/epub+zip',
                'mobi': 'application/x-mobipocket-ebook'
            }
            mimetype = mime_types.get(file_type, 'application/octet-stream')
            
            # Send file
            return send_file(
                file_stream,
                mimetype=mimetype,
                as_attachment=True,
                download_name=f"{ebook['name']}.{file_type}"
            )
            
        except Exception as e:
            print(f"Decryption error: {str(e)}")
            return render_template('Customer/error.html', 
                                 message='Error accessing ebook file'), 500
        
    except Exception as e:
        print(f"Download error: {str(e)}")
        return render_template('Customer/error.html', 
                             message='An error occurred'), 500

# === ADD EBOOK TO CART ===
@app.route('/add-ebook-to-cart', methods=['POST'])
def add_ebook_to_cart():
    try:
        data = request.get_json()
        ebook_id = data.get('ebook_id')
        
        if not ebook_id:
            return jsonify({'error': 'Ebook ID required'}), 400
        
        ebook = db.products.find_one({"_id": ObjectId(ebook_id), "category": "ebook", "is_active": True})
        
        if not ebook:
            return jsonify({'error': 'Ebook not found'}), 404
        
        # Check if already purchased
        user_email = session.get('user_email')
        if user_email:
            orders = db.orders.find({
                "email": user_email,
                "status": {"$in": ["paid", "completed", "delivered"]},
                "items": {"$elemMatch": {"id": ebook_id}}
            })
            if orders.count() > 0:
                return jsonify({'error': 'You already own this ebook!', 'owned': True}), 400
        
        # Add to cart
        cart = session.get('cart', [])
        existing_item = next((item for item in cart if item['id'] == ebook_id), None)
        
        if existing_item:
            existing_item['quantity'] = 1  # Ebooks can only be bought once
        else:
            cart.append({
                "id": str(ebook["_id"]),
                "name": ebook["name"],
                "price": ebook["price"],
                "quantity": 1,
                "category": "ebook"
            })
        
        session['cart'] = cart
        return jsonify({
            'success': True,
            'message': 'Ebook added to cart',
            'cart_count': len(cart)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

        # Check for ebooks in cart
        has_ebooks = any(item.get('category') == 'ebook' for item in cart)
        
        total = sum(item['price'] * item['quantity'] for item in cart)
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
            "created_at": datetime.now(timezone.utc)
        }
        result = db.orders.insert_one(order)
        order_id = str(result.inserted_id)
        session['order_id'] = order_id
        session['user_email'] = email  # Store for ebook access

        session_obj = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "gbp" if country != "Kenya" else "kes",
                    "product_data": {"name": "Feminine Flame Order"},
                    "unit_amount": int(total * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=url_for("payment_success", _external=True),
            cancel_url=url_for("checkout", _external=True),
            customer_email=email,
            client_reference_id=order_id,
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
                
                # Send ebook download links if ebooks were purchased
                order = db.orders.find_one({"_id": ObjectId(order_id)})
                if order and order.get('email'):
                    ebooks_in_order = [item for item in order.get('items', []) 
                                     if item.get('category') == 'ebook']
                    
                    if ebooks_in_order:
                        try:
                            customer_msg = Message(
                                subject="Feminine Flame - Your Ebooks Are Ready!",
                                recipients=[order['email']]
                            )
                            ebooks_list = "\n".join([f"• {item['name']}" for item in ebooks_in_order])
                            customer_msg.html = f"""
                            <div style="font-family: Arial, sans-serif; max-width: 600px;">
                                <h2 style="color: #c25e7d;">Thank You for Your Purchase!</h2>
                                <p>Your ebooks are now available for download:</p>
                                <ul>
                                    {"".join([f'<li>{item["name"]} - <a href="{url_for("ebook_detail", ebook_id=item["id"], _external=True)}">Download Here</a></li>' for item in ebooks_in_order])}
                                </ul>
                                <p>You can also access them anytime from your account.</p>
                            </div>
                            """
                            mail.send(customer_msg)
                        except Exception as e:
                            print(f"[MAIL] Ebook download email failed: {str(e)}")

    return jsonify({"status": "success"})

# === PAYMENT SUCCESS ===
@app.route("/payment-success")
def payment_success():
    session.pop('cart', None)
    order_id = session.pop('order_id', None)
    
    # Get order details to check if ebooks were purchased
    if order_id:
        order = db.orders.find_one({"_id": ObjectId(order_id)})
        if order and order.get('email'):
            session['user_email'] = order['email']  # Keep email for ebook access
    
    return render_template("Customer/success.html")

# === HEALTHCHECK ROUTE ===
@app.route('/health')
def health():
    """Healthcheck endpoint for Vercel monitoring"""
    try:
        db_status = "connected" if db is not None else "not_connected"
        return jsonify({
            "status": "healthy",
            "database": db_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# === HOMEPAGE ===
@app.route('/')
def home():
    try:
        initialize_db()  # Ensure DB is initialized before first request
        if db is None:
            return render_template('Customer/error.html', 
                                 message='Database connection unavailable. Please try again later.'), 503
        
        all_products = list(db.products.find({"is_active": True}))
        perfumes = [serialize_doc(p) for p in all_products if p.get('category') == 'perfume']
        ebooks = [serialize_doc(p) for p in all_products if p.get('category') == 'ebook']
        
        return render_template('Customer/index.html', 
                             perfumes=perfumes, 
                             ebooks=ebooks,
                             now=datetime.utcnow())
    except Exception as e:
        print(f"[ERROR] Homepage error: {str(e)}")
        # Return a simple error page or fallback
        return render_template('Customer/error.html', 
                             message='An error occurred loading the page. Please try again.'), 500

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
            # For ebooks, quantity should always be 1
            if item.get('category') == 'ebook':
                item['quantity'] = 1
            else:
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
        
        # Override phone number for Kenya
        if country == "Kenya":
            phone = "0715072834"

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
            "created_at": datetime.now(timezone.utc)
        }
        result = db.orders.insert_one(order)
        order_id = str(result.inserted_id)
        session['order_id'] = order_id
        session['user_email'] = email  # Store for ebook access

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
            print(f"[MAIL] Admin email failed: {str(e)}")

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
                    <p><strong>Payment:</strong> {"Send M-Pesa to 0715072834" if country=="Kenya" else "Complete payment on Stripe"}</p>
                    <p>We'll contact you soon.</p>
                </div>
                """
                mail.send(customer_msg)
            except Exception as e:
                print(f"[MAIL] Customer email failed: {str(e)}")
        session['order_id'] = order_id

        if country == "Kenya":
            session.pop('cart', None)
            return f"""
            <div style="max-width: 600px; margin: 3rem auto; padding: 2rem; text-align: center; font-family: Arial, sans-serif;">
                <h2>✅ Order Received!</h2>
                <p>Thank you, {name}! We've received your order.</p>
                <p>Please send your payment via M-Pesa to <strong>0715072834</strong>.</p>
                <p>We'll confirm your order once payment is received.</p>
                <a href="/" style="display: inline-block; margin-top: 1.5rem; padding: 0.6rem 1.2rem; background: #c25e7d; color: white; text-decoration: none; border-radius: 30px;">Back to Home</a>
            </div>
            """
        else:
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
                    "quantity": 1,
                    "category": product.get("category", "perfume")
                }]
        except Exception as e:
            print(f"[WARNING] Invalid product_id: {product_id}")

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
        product_id = request.args.get('id')
        product = db.products.find_one({"_id": ObjectId(product_id)})
        
        # If it's an ebook, delete the encrypted file too
        if product and product.get('category') == 'ebook':
            file_path = product.get('file_path')
            if file_path:
                encrypted_file = os.path.join(app.config['EBOOK_FOLDER'], file_path)
                if os.path.exists(encrypted_file):
                    os.remove(encrypted_file)
        
        db.products.delete_one({"_id": ObjectId(product_id)})
        return redirect(url_for('admin', tab='products'))

    # Clear all orders
    if request.method == 'POST' and request.form.get('clear_orders'):
        db.orders.delete_many({})
        return redirect(url_for('admin', tab='orders'))

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
        
        # Handle ebook file upload
        file_path = ''
        file_type = ''
        if category == 'ebook':
            file_path = request.form.get('ebook_file_path', '')
            file_type = request.form.get('ebook_file_type', 'pdf')

        data = {
            "name": request.form['name'],
            "description": request.form['description'],
            "category": category,
            "price": float(request.form['price']),
            "stock": stock,
            "image_url": image_filename,
            "is_active": True
        }
        
        # Add ebook-specific fields
        if category == 'ebook':
            data["preview_text"] = request.form.get('preview_text', '')[:1000]  # Limit to 1000 chars
            data["file_path"] = file_path
            data["file_type"] = file_type

        product_id = request.form.get('product_id')
        if product_id:
            db.products.update_one({"_id": ObjectId(product_id)}, {"$set": data})
        else:
            data["created_at"] = datetime.now(timezone.utc)
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

# === USER LOGIN (Simple Implementation) ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        # In a real app, you'd check password here
        session['user_email'] = email
        next_page = request.args.get('next')
        return redirect(next_page or url_for('home'))
    return render_template('Customer/login.html')

# === DEBUG ROUTE ===
@app.route('/test-db')
def test_db():
    try:
        db.list_collection_names()
        return "✅ Connected to MongoDB!"
    except Exception as e:
        return f"❌ Error: {str(e)}"


if __name__ == '__main__':
    print("[STARTUP] Starting Feminine Flame Application...")
    print(f"[STARTUP] Ebooks folder: {EBOOK_FOLDER}")
    print(f"[STARTUP] Uploads folder: {UPLOAD_FOLDER}")
    print(f"[STARTUP] MongoDB URI: {'SET' if MONGO_URI else 'NOT SET'}")
    print(f"[STARTUP] Stripe Key: {'SET' if os.getenv('STRIPE_SECRET_KEY') else 'NOT SET'}")
    app.run(debug=True)