from flask import Flask, render_template
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from flask import request, redirect, url_for, session
from datetime import datetime 


load_dotenv()

app = Flask(__name__)

app.secret_key = 'your-secret-key-change-in-production'

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client.feminine_flame

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

if __name__ == '__main__':
    app.run(debug=True)