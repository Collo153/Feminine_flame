# Feminine Flame AI Coding Agent Instructions

## Project Overview

Feminine Flame is a **Flask-based e-commerce platform** selling perfumes and encrypted eBooks with integrated Stripe & M-Pesa payment processing. The architecture separates frontend (Jinja2 templates + vanilla JS), backend (Flask routes), and encrypted file storage.

## Architecture & Key Patterns

### Core Components

1. **Backend (app.py - 809 lines)**
   - Main Flask application with session-based cart management
   - MongoDB integration for products, orders, and users
   - File encryption/decryption for protected eBooks

2. **Database Schema** (MongoDB - `Feminine_flame` DB)
   - `products`: Shared table with category-based fields (perfumes vs ebooks)
   - `orders`: Order records with status tracking (pending → paid → delivered)
   - `users`: Admin & customer authentication (only admin: feminineflame19@gmail.com pre-configured)

3. **Frontend (Templates + static/js/)**
   - **Cart Strategy**: Client-side (localStorage) + server-side (Flask session) dual sync
   - **Client JS**: Vanilla JavaScript (no frameworks) with fetch() for API calls
   - **Product Pages**: Category-separated views (perfumes vs ebooks)

### Data Flow Patterns

- **Cart Operations**: JavaScript adds items to localStorage → fetch POST to `/sync-cart` → Flask updates session
- **Product Categories**: Single products collection with `category: "perfume"` or `category: "ebook"` discriminator
- **Ebook-Specific Fields**: preview_text, file_path (encrypted), file_type, stock=-1 (unlimited)
- **Purchase Verification**: Check `orders` collection for email + item_id to unlock ebook downloads

### Encryption & File Storage

```
/protected_ebooks/         # Encrypted ebook binaries (UUID names)
/static/uploads/ebooks/    # Product images for ebooks (unencrypted)
```

- **Key**: Loaded from `EBOOK_ENCRYPTION_KEY` env var (Fernet symmetric encryption)
- **Workflow**: Upload encrypted → Store in `/protected_ebooks/` → On download: decrypt + stream as attachment
- **Setup**: If `EBOOK_ENCRYPTION_KEY` missing, app generates one and logs warning (must add to .env)

## Critical Workflows & Commands

### Local Development
```bash
pip install -r requirements.txt
# Set .env: MONGO_URI, STRIPE_SECRET_KEY, EBOOK_ENCRYPTION_KEY, MAIL_USERNAME, etc.
python app.py  # Runs on localhost:5000 with debug=True
```

### Deployment (Vercel)
- `vercel.json` configured for Python runtime + static files
- Flask app must handle template file inclusion (`Templates/**` in functions config)
- Environment: All secrets via Vercel env vars (STRIPE_WEBHOOK_SECRET, MONGO_URI, etc.)

### Payment Integration Points
1. **Stripe**: UK Pounds (GBP) primary; detects Kenya → switches to KES
2. **M-Pesa (Daraja API)**: Configured but not integrated into checkout yet (see `mpesa_daraja.py`)
3. **Webhook**: `/webhook` validates Stripe signatures → updates order status → sends ebook emails

## Project-Specific Conventions

### Session Management
- Cart stored in `session['cart']` (list of dicts with id, name, price, quantity, category)
- User email: `session['user_email']` set during login/checkout
- Order ID: `session['order_id']` set after order creation, cleared on success

### MongoDB ObjectId Handling
- All MongoDB operations use `ObjectId()` casting from strings
- Serialization utility: `serialize_doc()` converts `_id` to string for JSON responses
- Errors: ObjectId() constructor may raise exceptions on invalid ID format

### File Upload Validation
- Images: `ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'epub', 'mobi'}`
- eBooks: Stricter `ALLOWED_EBOOK_EXTENSIONS = {'pdf', 'epub', 'mobi'}`
- Naming: Use `secure_filename()` + `uuid.uuid4().hex` to prevent collisions & path traversal

### Ebook Purchase Verification
```python
# Check if user owns ebook (used in 3 places: detail page, download route, add-to-cart)
orders = db.orders.find({
    "email": user_email,
    "status": {"$in": ["paid", "completed", "delivered"]},
    "items": {"$elemMatch": {"id": ebook_id}}
})
if orders.count() > 0:  # User owns ebook
```

## Important Integration Points

### Stripe Webhook Flow
1. Customer completes payment → `/webhook` receives `checkout.session.completed` event
2. Signature verified with `STRIPE_WEBHOOK_SECRET`
3. Order marked "paid" in DB
4. **For ebooks only**: Email sent with download links (uses Flask-Mail)

### Admin Panel (`/admin`)
- Guards: `if not session.get('admin_logged_in')` (simple check, can improve)
- Tabs: dashboard, products, orders
- Edit product: Pass product_id in GET params (`?edit=<ObjectId>`)

### Ebook Download Security
- Only if user logged in AND purchase verified
- Decrypts file on-demand (CPU cost per download)
- MIME types mapped for PDF/EPUB/MOBI (important for browser handling)

## Known Limitations & Improvement Areas

1. **Admin Login**: Currently only checks session flag—no actual credential validation
2. **Product Images**: Stored unencrypted in `/static/uploads/` (consider CDN for scaling)
3. **Error Pages**: Hardcoded template paths (add proper error handling middleware)
4. **M-Pesa**: Configured but not wired into checkout flow
5. **Logging**: Using print() statements instead of structured logging
6. **Testing**: No test suite present

## Environment Variables Required

```env
MONGO_URI=mongodb+srv://...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
EBOOK_ENCRYPTION_KEY=<fernet-key-or-auto-generated>
FLASK_SECRET_KEY=your-secret
MAIL_USERNAME=feminineflame19@gmail.com
MAIL_PASSWORD=<app-password>
MPESA_BASE_URL=https://sandbox.safaricom.co.ke  # or live URL
MPESA_CONSUMER_KEY=...
MPESA_CONSUMER_SECRET=...
MPESA_BUSINESS_SHORTCODE=...
MPESA_PASSKEY=...
MPESA_CALLBACK_URL=https://yourdomain.com/mpesa-callback
```

## File Structure Reference

| Path | Purpose |
|------|---------|
| `app.py` | Main Flask app (routes, DB logic, auth) |
| `stripe_utils.py` | Stripe session creation & webhook helpers |
| `mpesa_daraja.py` | M-Pesa STK push implementation |
| `Templates/Customer/*` | Customer-facing pages |
| `Templates/Admin/admin.html` | Admin dashboard |
| `static/js/cart.js` | Client-side cart logic |
| `protected_ebooks/` | Encrypted ebook storage (not in repo) |
| `static/uploads/ebooks/` | Product images (not in repo) |

---

*Last Updated: Jan 2026 | For questions, check route docstrings in app.py*
