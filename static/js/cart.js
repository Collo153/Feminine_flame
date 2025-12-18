// Simple cart using localStorage
function changeQty(delta) {
  const input = document.getElementById('quantity');
  let qty = parseInt(input.value);
  qty = Math.max(1, qty + delta);
  input.value = qty;
}

function addToCart(productId, name, price) {
  // Get existing cart or create new
  let cart = JSON.parse(localStorage.getItem('cart')) || [];

  // Check if product already in cart
  const existing = cart.find(item => item.id === productId);
  const qty = parseInt(document.getElementById('quantity').value);

  if (existing) {
    existing.quantity += qty;
  } else {
    cart.push({
      id: productId,
      name: name,
      price: price,
      quantity: qty
    });
  }

  localStorage.setItem('cart', JSON.stringify(cart));
  alert(`${name} added to cart!`);
  // Optional: update cart icon count
}

document.addEventListener('DOMContentLoaded', function () {
  const button = document.getElementById('add-to-cart-btn');
  if (!button) return;

  button.addEventListener('click', function () {
    const productId = parseInt(button.dataset.productId);
    const productName = button.dataset.productName; // already a safe string
    const productPrice = parseFloat(button.dataset.productPrice);

    // Validate
    if (isNaN(productId) || !productName || isNaN(productPrice)) {
      alert('Product data missing!');
      return;
    }

    addToCart(productId, productName, productPrice);
  });
});

// Keep your existing addToCart function
function addToCart(productId, name, price) {
  let cart = JSON.parse(localStorage.getItem('cart')) || [];
  const qty = parseInt(document.getElementById('quantity')?.value) || 1;

  const existing = cart.find(item => item.id === productId);
  if (existing) {
    existing.quantity += qty;
  } else {
    cart.push({ id: productId, name, price, quantity: qty });
  }

  localStorage.setItem('cart', JSON.stringify(cart));
  alert(`${name} added to cart!`);
}

function changeQty(delta) {
  const input = document.getElementById('quantity');
  if (!input) return;
  let qty = parseInt(input.value);
  qty = Math.max(1, qty + delta);
  input.value = qty;
}

// =============== CART MANAGEMENT ===============

function changeQty(itemId, delta) {
  let cart = JSON.parse(localStorage.getItem('cart')) || [];
  const item = cart.find(i => i.id === itemId);
  if (item) {
    item.quantity = Math.max(1, item.quantity + delta);
    if (item.quantity === 0) {
      cart = cart.filter(i => i.id !== itemId);
    }
    localStorage.setItem('cart', JSON.stringify(cart));
    renderCart();
  }
}

function removeItem(itemId) {
  let cart = JSON.parse(localStorage.getItem('cart')) || [];
  cart = cart.filter(i => i.id !== itemId);
  localStorage.setItem('cart', JSON.stringify(cart));
  renderCart();
}

function updateQuantity(itemId, newQty) {
  let cart = JSON.parse(localStorage.getItem('cart')) || [];
  const item = cart.find(i => i.id === itemId);
  if (item && newQty >= 1) {
    item.quantity = parseInt(newQty);
    localStorage.setItem('cart', JSON.stringify(cart));
    renderCart();
  }
}

function calculateTotal(cart) {
  return cart.reduce((total, item) => total + (item.price * item.quantity), 0);
}

function renderCart() {
  const cartContent = document.getElementById('cart-content');
  if (!cartContent) return;

  const cart = JSON.parse(localStorage.getItem('cart')) || [];

  if (cart.length === 0) {
    cartContent.innerHTML = `
      <div class="empty-cart">
        <h2>Your cart is empty</h2>
        <p>← <a href="${window.location.origin}/products">Start shopping</a></p>
      </div>
    `;
    return;
  }

  let itemsHTML = `
    <div class="cart-items">
      <div class="cart-header">
        <div>Product</div>
        <div>Description</div>
        <div>Price</div>
        <div>Quantity</div>
        <div>Total</div>
      </div>
  `;

  cart.forEach(item => {
    const total = (item.price * item.quantity).toFixed(2);
    itemsHTML += `
      <div class="cart-item">
        <div class="item-image">${item.name}</div>
        <div class="item-name">${item.name}</div>
        <div class="item-price">$${item.price.toFixed(2)}</div>
        <div class="quantity-controls">
          <button class="qty-btn" onclick="changeQty(${item.id}, -1)">-</button>
          <input type="number" 
                 class="qty-input" 
                 value="${item.quantity}" 
                 min="1"
                 onchange="updateQuantity(${item.id}, this.value)">
          <button class="qty-btn" onclick="changeQty(${item.id}, 1)">+</button>
        </div>
        <div class="item-total">$${total}</div>
        <button class="remove-btn" onclick="removeItem(${item.id})">×</button>
      </div>
    `;
  });

  const total = calculateTotal(cart).toFixed(2);
  itemsHTML += `
    </div>
    <div class="cart-summary">
      <div class="summary-row">
        <span>Subtotal:</span>
        <span>$${total}</span>
      </div>
      <div class="summary-row">
        <span>Shipping:</span>
        <span>$0.00</span>
      </div>
      <div class="summary-row total-row">
        <span>Total:</span>
        <span>$${total}</span>
      </div>
      <a href="/checkout" class="checkout-btn">Proceed to Checkout</a>
    </div>
  `;

  cartContent.innerHTML = itemsHTML;
}

// Expose functions to global scope for inline handlers
window.changeQty = changeQty;
window.removeItem = removeItem;
window.updateQuantity = updateQuantity;
window.renderCart = renderCart;

function buyAllCart() {
  const cart = JSON.parse(localStorage.getItem('cart')) || [];
  if (cart.length === 0) {
    alert("Your cart is empty!");
    return;
  }
  // Redirect to checkout with cart data in URL (temporary)
  // Later: send via POST to Flask
  window.location.href = "/checkout";
}


function renderCart() {
  const cartContent = document.getElementById('cart-content');
  if (!cartContent) return;

  const cart = JSON.parse(localStorage.getItem('cart')) || [];

  if (cart.length === 0) {
    cartContent.innerHTML = `
      <div class="empty-cart">
        <h2>Your cart is empty</h2>
        <p><a href="${window.location.origin}/products">← Start shopping</a></p>
      </div>
    `;
    return;
  }

  let html = '<div class="cart-items"><div class="cart-header">...</div>'; // keep your existing header

  // Rebuild this section based on your actual cart design
  cart.forEach(item => {
    const total = (item.price * item.quantity).toFixed(2);
    html += `
      <div class="cart-item">
        <div class="item-image">${item.name}</div>
        <div class="item-name">${item.name}</div>
        <div class="item-price">$${item.price.toFixed(2)}</div>
        <div class="quantity-controls">
          <button onclick="changeQty(${item.id}, -1)">-</button>
          <span>${item.quantity}</span>
          <button onclick="changeQty(${item.id}, 1)">+</button>
        </div>
        <div class="item-total">$${total}</div>
        <button onclick="removeItem(${item.id})">×</button>
      </div>
    `;
  });

  html += '</div>'; // close cart-items

  // Add summary and checkout button
  const total = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0).toFixed(2);
  html += `
    <div class="cart-summary">
      <div class="summary-row"><span>Total:</span> <span>$${total}</span></div>
      <button class="checkout-btn" onclick="buyAllCart()">Buy All</button>
    </div>
  `;

  cartContent.innerHTML = html;
}

// Expose to global scope
window.renderCart = renderCart;
window.changeQty = changeQty;
window.removeItem = removeItem;
window.buyAllCart = buyAllCart;


// =============== RENDER CART PAGE ===============
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
        <div>Description</div>
        <div>Price</div>
        <div>Quantity</div>
        <div>Total</div>
      </div>
  `;

  cart.forEach(item => {
    const total = (item.price * item.quantity).toFixed(2);
    html += `
      <div class="cart-item">
        <div class="item-image">${item.name}</div>
        <div class="item-name">${item.name}</div>
        <div class="item-price">$${item.price.toFixed(2)}</div>
        <div>${item.quantity}</div>
        <div class="item-total">$${total}</div>
      </div>
    `;
  });

  const total = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0).toFixed(2);
  html += `
    </div>
    <div class="cart-summary">
      <div class="summary-row">
        <span>Total:</span>
        <span>$${total}</span>
      </div>
      <a href="/checkout" class="checkout-btn">Proceed to Checkout</a>
    </div>
  `;

  cartContent.innerHTML = html;
}

// Make it globally available
window.renderCart = renderCart;