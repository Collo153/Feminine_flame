from flask import Flask, render_template
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from flask import request, redirect, url_for, session
from datetime import datetime 
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from functools import wraps
from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, session, jsonify





load_dotenv()


app = Flask(__name__)

app.secret_key = 'your-secret-key-change-in-production'

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client.Feminine_flame

admin_user = {
    "email": "admin@feminineflame.com",
    "password_hash": generate_password_hash("secureAdminPass123!"),
    "role": "admin",
    "is_active": True
}

db.users.insert_one(admin_user)
print("✅ Admin user created!")

@app.route('/')
def home():
    return render_template('customer/index.html')

@app.route('/products')
def products():
    # Later: fetch from MongoDB
    # For now: dummy data
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
    return render_template('customer/products.html', products=dummy_products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    # Find product by ID (later from DB)
    product = next((p for p in [
        {"id": 1, "name": "Velvet Bloom", "price": 89.00, "description": "A rich floral blend..."},
        {"id": 2, "name": "Midnight Whisper", "price": 75.00, "description": "Mysterious and sensual..."}
    ] if p["id"] == product_id), None)

    if not product:
        return "Product not found", 404

    return render_template('customer/product_detail.html', product=product)

@app.route('/cart')
def cart():
    # No backend logic needed yet — cart lives in localStorage
    return render_template('customer/cart.html')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        # Handle form submission
        name = request.form.get('name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        payment_method = request.form.get('payment_method', 'mpesa')
        
        cart = session.get('cart', [])
        if not cart:
            return "Cart is empty", 400

        order = {
            "customer_name": name,
            "phone": phone,
            "address": address,
            "payment_method": payment_method,
            "items": cart,
            "total": sum(item['price'] * item['quantity'] for item in cart),
            "status": "pending",
            "created_at": datetime.utcnow()
        }
        db.orders.insert_one(order)
        session.pop('cart', None)
        return f"<h1>Order Placed!</h1><p>Thank you, {name}. We'll contact you soon.</p>"

    # Handle GET: show form
    # Also handle "Buy Now" with product_id
    product_id = request.args.get('product_id')
    if product_id:
        # Dummy product lookup
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

    return render_template('customer/checkout.html')

@app.route('/test-db')
def test_db():
    try:
        db.list_collection_names()  # Ping the DB
        return "✅ Connected to MongoDB Atlas!"
    except Exception as e:
        return f"❌ Error: {str(e)}"
    
    #admin
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = db.users.find_one({"email": email, "role": "admin"})
        if user and check_password_hash(user['password_hash'], password):
            session['admin_id'] = str(user['_id'])
            return redirect(url_for('admin_dashboard'))
        return "Invalid credentials", 401
    return render_template('Admin/admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    return redirect(url_for('admin_login'))
    
    
    # Admin routes
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    # Handle login (POST)
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.users.find_one({"email": email, "role": "admin"})
        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        return "Invalid credentials", 401

    # Handle logout
    if request.args.get('action') == 'logout':
        session.pop('admin_logged_in', None)
        return redirect(url_for('admin'))

    # Check if logged in
    if not session.get('admin_logged_in'):
        return render_template('admin.html', page='login')

    # Handle product actions
    action = request.args.get('action')
    if action == 'delete':
        db.products.delete_one({"_id": ObjectId(request.args.get('id'))})
        return redirect(url_for('admin'))

    if request.method == 'POST' and request.form.get('name'):
        # Add or edit product
        data = {
            "name": request.form['name'],
            "description": request.form['description'],
            "category": request.form['category'],
            "price": float(request.form['price']),
            "stock": int(request.form['stock']) if request.form['category'] == 'perfume' else -1,
            "image_url": request.form.get('image_url', ''),
            "is_active": True
        }
        if request.form.get('product_id'):
            # Edit
            db.products.update_one(
                {"_id": ObjectId(request.form['product_id'])},
                {"$set": data}
            )
        else:
            # Add
            data["created_at"] = datetime.utcnow()
            db.products.insert_one(data)
        return redirect(url_for('admin'))

    # Render dashboard
    products = list(db.products.find())
    edit_product = None
    if request.args.get('edit'):
        edit_product = db.products.find_one({"_id": ObjectId(request.args.get('edit'))})

    return render_template('Admin/admin.html', 
                          page='dashboard', 
                          products=products, 
                          edit_product=edit_product)

if __name__ == '__main__':
    app.run(debug=True)