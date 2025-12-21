// =============== ADD TO CART ===============
function addToCart(productId, name, price, quantity = 1) {
  let cart = JSON.parse(localStorage.getItem('cart')) || [];

  // Ensure types
  productId = parseInt(productId);
  price = parseFloat(price);
  quantity = parseInt(quantity) || 1;

  const existing = cart.find(item => item.id === productId);
  if (existing) {
    existing.quantity += quantity;
  } else {
    cart.push({ id: productId, name, price, quantity });
  }

  localStorage.setItem('cart', JSON.stringify(cart));
  alert(`${name} added to cart!`);
}

// =============== RENDER CART ===============
function renderCart() {
  const cartContent = document.getElementById('cart-content');
  if (!cartContent) return;

  const cart = JSON.parse(localStorage.getItem('cart')) || [];

  if (cart.length === 0) {
    cartContent.innerHTML = `
      <div class="empty-cart">
        <h2>Your cart is empty</h2>
        <p><a href="/products">← Start shopping</a></p>
      </div>
    `;
    return;
  }

  let html = `
    <div class="cart-items">
      <div class="cart-header">
        <div>Product</div>
        <div>Price</div>
        <div>Qty</div>
        <div>Total</div>
        <div>Actions</div>
      </div>
  `;

  cart.forEach(item => {
    const total = (item.price * item.quantity).toFixed(2);
    html += `
      <div class="cart-item">
        <div>${item.name}</div>
        <div>$${item.price.toFixed(2)}</div>
        <div>${item.quantity}</div>
        <div>$${total}</div>
        <div><button onclick="removeItem(${item.id})">Remove</button></div>
      </div>
    `;
  });

  const grandTotal = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0).toFixed(2);
  html += `
    </div>
    <div class="cart-summary">
      <div class="summary-row">
        <span>Grand Total:</span>
        <span>$${grandTotal}</span>
      </div>
      <a href="/checkout" class="checkout-btn">Proceed to Checkout</a>
    </div>
  `;

  cartContent.innerHTML = html;
}

// =============== REMOVE ITEM ===============
function removeItem(itemId) {
  let cart = JSON.parse(localStorage.getItem('cart')) || [];
  cart = cart.filter(item => item.id !== itemId);
  localStorage.setItem('cart', JSON.stringify(cart));
  renderCart(); // Refresh cart page
}

// =============== GLOBAL EXPOSURE ===============
window.addToCart = addToCart;
window.renderCart = renderCart;
window.removeItem = removeItem;
window.buyAllCart = () => window.location.href = '/checkout';