from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime 
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import uuid
from werkzeug.utils import secure_filename

load_dotenv()

# Initialize Flask app with correct template folder
app = Flask(__name__, template_folder='Templates')
app.secret_key = 'your-secret-key-change-in-production'

# Upload config (after app = Flask(...))
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client.Feminine_flame

# === CREATE ADMIN USER (IF NOT EXISTS) ===
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

# === SEED SAMPLE DATA ON STARTUP ===
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
        }
    ])
    print("✅ Sample products added!")

if db.orders.count_documents({}) == 0:
    db.orders.insert_one({
        "customer_name": "Test Customer",
        "phone": "+254712345678",
        "address": "Nairobi, Kenya",
        "country": "Kenya",
        "payment_method": "mpesa",
        "items": [{"id": 1, "name": "Velvet Bloom", "price": 89.00, "quantity": 1}],
        "total": 89.00,
        "status": "pending",
        "created_at": datetime.utcnow()
    })
    print("✅ Sample order added!")


# === PUBLIC ROUTES ===
@app.route('/')
def home():
    return render_template('Customer/index.html')

@app.route('/products')
def products():
    dummy_products = [
        {
            "id": 1,
            "name": "Velvet Bloom",
            "price": 89.00,
            "image": "perfume1.jpg",
            "description": "A rich floral blend with notes of rose, amber, and vanilla.",
            "category": "perfume"
        },
        {
            "id": 2,
            "name": "Midnight Whisper",
            "price": 75.00,
            "image": "perfume2.jpg",
            "description": "Mysterious and sensual — oud, sandalwood, and musk.",
            "category": "perfume"
        }
    ]
    return render_template('Customer/products.html', products=dummy_products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = next((p for p in [
        {"id": 1, "name": "Velvet Bloom", "price": 89.00, "description": "A rich floral blend..."},
        {"id": 2, "name": "Midnight Whisper", "price": 75.00, "description": "Mysterious and sensual..."}
    ] if p["id"] == product_id), None)

    if not product:
        return "Product not found", 404

    return render_template('Customer/product_detail.html', product=product)

@app.route('/cart')
def cart():
    return render_template('Customer/cart.html')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        country = request.form.get('country')

        if not all([name, phone, address, country]):
            return "All fields are required", 400

        cart = session.get('cart', [])
        if not cart:
            return "Cart is empty", 400

        # Auto-set payment method based on country
        payment_method = "mpesa" if country == "Kenya" else "contact"

        order = {
            "customer_name": name,
            "phone": phone,
            "address": address,
            "country": country,
            "payment_method": payment_method,
            "items": cart,
            "total": sum(item['price'] * item['quantity'] for item in cart),
            "status": "pending",
            "created_at": datetime.utcnow()
        }
        db.orders.insert_one(order)
        session.pop('cart', None)

        if country == "UK":
            return f"""
            <div style="max-width: 600px; margin: 3rem auto; padding: 2rem; text-align: center; font-family: Arial, sans-serif;">
                <h2>✅ Order Received!</h2>
                <p>Thank you, {name}!</p>
                <p><strong>UK Customers:</strong> Please contact us at <strong>+44 7301 623591</strong> to complete payment.</p>
                <a href="{url_for('home')}" style="display: inline-block; margin-top: 1.5rem; padding: 0.6rem 1.2rem; background: #c25e7d; color: white; text-decoration: none; border-radius: 30px;">Back to Home</a>
            </div>
            """
        else:
            return f"""
            <div style="max-width: 600px; margin: 3rem auto; padding: 2rem; text-align: center; font-family: Arial, sans-serif;">
                <h2>✅ Order Placed!</h2>
                <p>Thank you, {name}! We'll contact you soon via <strong>{phone}</strong>.</p>
                <a href="{url_for('home')}" style="display: inline-block; margin-top: 1.5rem; padding: 0.6rem 1.2rem; background: #c25e7d; color: white; text-decoration: none; border-radius: 30px;">Back to Home</a>
            </div>
            """

    # Handle "Buy Now"
    product_id = request.args.get('product_id')
    if product_id:
        products = {
            1: {"id": 1, "name": "Velvet Bloom", "price": 89.00},
            2: {"id": 2, "name": "Midnight Whisper", "price": 75.00}
        }
        product = products.get(int(product_id))
        if product:
            session['cart'] = [{
                "id": product["id"],
                "name": product["name"],
                "price": product["price"],
                "quantity": 1
            }]

    return render_template('Customer/checkout.html')

@app.route('/test-db')
def test_db():
    try:
        db.list_collection_names()
        return "✅ Connected to MongoDB!"
    except Exception as e:
        return f"❌ Error: {str(e)}"



@app.route('/admin', methods=['GET', 'POST'])
def admin():
    # --- LOGOUT ---
    if request.args.get('action') == 'logout':
        session.pop('admin_logged_in', None)
        return redirect(url_for('admin'))

    # --- LOGIN ---
    if request.method == 'POST' and not session.get('admin_logged_in'):
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.users.find_one({"email": email, "role": "admin"})
        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        return "Invalid email or password", 401

    # --- AUTH GUARD ---
    if not session.get('admin_logged_in'):
        return render_template('Admin/admin.html', page='login')

    # --- DELETE PRODUCT ---
    if request.args.get('action') == 'delete' and request.args.get('type') == 'product':
        db.products.delete_one({"_id": ObjectId(request.args.get('id'))})
        return redirect(url_for('admin', tab='products'))

    # --- ADD/UPDATE PRODUCT (WITH IMAGE UPLOAD) ---
    if request.method == 'POST' and request.form.get('name'):
        # Handle image upload
        image_filename = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                image_filename = unique_filename

        # If editing and no new image, keep old one
        if not image_filename and request.form.get('product_id'):
            existing = db.products.find_one({"_id": ObjectId(request.form.get('product_id'))})
            image_filename = existing.get('image_url', '')

        data = {
            "name": request.form['name'],
            "description": request.form['description'],
            "category": "perfume",
            "price": float(request.form['price']),
            "stock": int(request.form['stock']),
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

    # --- UPDATE ORDER STATUS ---
    if request.method == 'POST' and request.form.get('order_id'):
        db.orders.update_one(
            {"_id": ObjectId(request.form['order_id'])},
            {"$set": {"status": "delivered"}}
        )
        return redirect(url_for('admin', tab='orders'))

    # --- PREPARE DATA ---
    tab = request.args.get('tab', 'dashboard')
    products = list(db.products.find()) if tab == 'products' else []
    orders = list(db.orders.find().sort("created_at", -1)) if tab == 'orders' else []
    edit_product = None
    if request.args.get('edit'):
        edit_product = db.products.find_one({"_id": ObjectId(request.args.get('edit'))})

    return render_template(
        'Admin/admin.html',
        page='dashboard',
        tab=tab,
        products=products,
        orders=orders,
        edit_product=edit_product
    )

@app.route('/admin/update-order-status', methods=['POST'])
def update_order_status():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    
    order_id = request.form.get('order_id')
    if order_id:
        db.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"status": "delivered"}}
        )
    return redirect(url_for('admin', tab='orders'))

if __name__ == '__main__':
    app.run(debug=True)