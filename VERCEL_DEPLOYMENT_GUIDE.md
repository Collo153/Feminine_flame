# Vercel Deployment & FUNCTION_INVOCATION_FAILED Fix

## What Was Fixed

### 1. **Lazy Database Initialization**
**Problem:** Database queries were running at module import time, causing crashes if MongoDB was unavailable.
```python
# BEFORE: Runs immediately when file is imported
admin_exists = db.users.find_one({})  # ❌ CRASHES if DB unavailable
```

**Solution:** Moved initialization to a lazy function that runs on first request.
```python
# AFTER: Runs only when needed
def initialize_db():
    global _initialized
    if _initialized:
        return
    # ... initialization code ...
    _initialized = True
```

### 2. **Ephemeral File System Handling**
**Problem:** Vercel's file system is temporary—files created during a request are deleted after it ends.
```python
# BEFORE: Always creates directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # ❌ Can cause permission errors on Vercel
```

**Solution:** Only create directories on local development.
```python
# AFTER: Check if running on Vercel
if not os.getenv('VERCEL'):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # ✅ Only on local
```

### 3. **Global Error Handling**
**Problem:** Unhandled exceptions crash the entire function.
```python
# BEFORE: Exceptions cause 500 error without graceful fallback
if something_fails:
    raise Exception()  # ❌ FUNCTION_INVOCATION_FAILED
```

**Solution:** Added Flask error handler.
```python
# AFTER: Graceful error responses
@app.errorhandler(500)
def handle_500_error(e):
    return render_template('Customer/error.html', message='Error occurred'), 500
```

### 4. **Enhanced Vercel Configuration**
**Problem:** Default configuration has insufficient memory/timeout for Python.
```json
// BEFORE
{
  "functions": {
    "app.py": {
      "includeFiles": "Templates/**"
    }
  }
}
```

**Solution:** Added memory, timeout, and excluded ephemeral directories.
```json
// AFTER
{
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python",
      "config": {
        "maxDuration": 30,    // 30 second timeout
        "memory": 512         // 512MB memory
      }
    }
  ],
  "functions": {
    "app.py": {
      "includeFiles": "Templates/**",
      "excludeFiles": "protected_ebooks/**"  // Don't include ephemeral dirs
    }
  }
}
```

---

## Environment Variables Checklist

Ensure these are set in Vercel Project Settings → Environment Variables:

- [ ] `MONGO_URI` - Must be a valid MongoDB Atlas connection string
- [ ] `STRIPE_SECRET_KEY` - Stripe API key
- [ ] `STRIPE_WEBHOOK_SECRET` - For webhook validation
- [ ] `FLASK_SECRET_KEY` - For session management
- [ ] `MAIL_USERNAME` - Gmail address for sending emails
- [ ] `MAIL_PASSWORD` - Gmail app password (NOT your regular password)
- [ ] `EBOOK_ENCRYPTION_KEY` - Fernet encryption key (generated if missing)

**Testing MongoDB Connection:**
```bash
# In Vercel Logs, you should see:
# "✅ Admin user created!" or similar initialization messages
# NOT: "❌ Error connecting to MongoDB"
```

---

## Deployment Testing Checklist

### Before Pushing to Vercel:
```bash
# 1. Test locally
python app.py
# Visit http://localhost:5000 and verify homepage loads

# 2. Check syntax
python -m py_compile app.py
# Should complete without errors

# 3. Verify imports
python -c "import app; print('✅ All imports successful')"
```

### After Pushing to Vercel:
1. Go to your Vercel project dashboard
2. Click "Deployments"
3. Click the latest deployment
4. Go to "Logs" tab
5. Look for:
   - ✅ Should see: `✅ Admin user created!` or `✅ Sample products added!`
   - ❌ Should NOT see: Database connection errors, file permission errors
6. Test the homepage: `https://yourdomain.vercel.app/`

---

## Common Issues & Fixes

### Issue: "FUNCTION_INVOCATION_FAILED" on every request
**Check:**
1. Vercel Logs tab for actual error message
2. Is `MONGO_URI` set in environment variables? (Most common cause)
3. Is `MONGO_URI` accessible from Vercel? (Test IP whitelisting)

### Issue: 502 Bad Gateway / Gateway Timeout
**Check:**
1. Increase `maxDuration` in `vercel.json` (currently 30 seconds)
2. Database queries taking too long? Add indexes to MongoDB
3. Large file uploads? Increase `MAX_CONTENT_LENGTH`

### Issue: "Error accessing ebook file" (404)
**Root Cause:** Files saved during request are deleted after request ends
**Solution:** For production, use AWS S3 or similar cloud storage:
```python
# Instead of:
# with open(encrypted_path, 'wb') as f:
#     f.write(encrypted_data)

# Use:
# s3.upload_fileobj(encrypted_data, bucket_name, file_path)
```

### Issue: Admin panel file uploads don't work
**Root Cause:** Same as above—files not persisting
**Solution:** Implement S3 integration (see S3_INTEGRATION.md when ready)

---

## Local vs. Production Differences

| Feature | Local | Vercel |
|---------|-------|--------|
| Database init | Runs at startup | Runs on first request (lazy) |
| File system | Persists across requests | Ephemeral (per request) |
| Timeout | Unlimited | 30 seconds (configurable) |
| Memory | System limit | 512MB default |
| Environment vars | `.env` file | Project settings |
| Logs | Console output | Vercel Logs dashboard |
| Cold starts | N/A | ~2-5 seconds on first request |

---

## Performance Optimization Tips

1. **Minimize startup time** - Only lazy-load what's needed
2. **Cache database queries** - Use `_initialized` pattern for one-time setup
3. **Optimize MongoDB** - Add indexes on frequently queried fields:
   ```python
   db.products.create_index("category")
   db.orders.create_index("email")
   db.users.create_index("email")
   ```
4. **Enable MongoDB connection pooling** - Already configured in app.py

---

## Next Steps for Full Vercel Compatibility

Once the current error is resolved:

1. **Replace local file uploads with S3:**
   - Install `boto3`: `pip install boto3`
   - Upload to S3 instead of local `protected_ebooks/`
   - Stream downloads from S3

2. **Add structured logging:**
   - Install `python-json-logger`
   - Replace print statements with logging
   - Monitor in Vercel Observability dashboard

3. **Set up automated backups:**
   - MongoDB Atlas automatic backups
   - S3 versioning enabled

4. **Add monitoring:**
   - Sentry for error tracking
   - DataDog for performance monitoring

---

*Last Updated: January 2026*
