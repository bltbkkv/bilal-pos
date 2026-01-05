let cart = [];
const fmt = v => Number(v).toFixed(2);

// 🔔 Уведомления
function notify(msg, type = "success") {
  const box = document.getElementById('notify');
  if (!box) return;
  box.textContent = msg;
  box.className = "notify " + (type === "error" ? "error show" : "show");
  setTimeout(() => { box.className = "notify"; }, 2000);
}

// 🛒 Отрисовка корзины
function renderCart() {
  const list = document.getElementById('cart-items');
  const totalNode = document.getElementById('cart-total');
  list.innerHTML = '';
  let total = 0;
  cart.forEach(item => {
    const lineTotal = item.price * item.qty;
    total += lineTotal;
    const li = document.createElement('li');
    li.innerHTML = `
      <div>${item.name}</div>
      <div>${fmt(lineTotal)} сом</div>
      <div class="qty">
        <button onclick="decQty('${item.id}')">-</button>
        <span>${item.qty}</span>
        <button onclick="incQty('${item.id}')">+</button>
      </div>
      <div class="remove" onclick="removeItem('${item.id}')">✕</div>
    `;
    list.appendChild(li);
  });
  totalNode.textContent = fmt(total);
}

function addToCart(id, name, price) {
  const existing = cart.find(i => i.id === id);
  if (existing) existing.qty += 1;
  else cart.push({ id, name, price: Number(price), qty: 1 });
  renderCart();
}
function incQty(id) {
  const i = cart.find(x => x.id === id);
  if (i) { i.qty++; renderCart(); }
}
function decQty(id) {
  const i = cart.find(x => x.id === id);
  if (i && i.qty > 1) { i.qty--; } else { removeItem(id); }
  renderCart();
}
function removeItem(id) {
  cart = cart.filter(i => i.id !== id);
  renderCart();
}
function clearCart() {
  cart = [];
  renderCart();
}

// 🔎 Фильтр по категории
function filterCategory(cat) {
  document.querySelectorAll('.cat-btn').forEach(b => b.classList.toggle('active', b.dataset.cat === cat));
  document.querySelectorAll('.item').forEach(el => {
    el.style.display = (cat === 'all' || el.dataset.category === cat) ? '' : 'none';
  });
}

// 🧾 Оформление заказа
async function checkout() {
  if (!cart.length) return notify('Корзина пустая', "error");
  if (!window.EMPLOYEE_ID) return notify('Сначала войдите кассиром', "error");

  const note = document.getElementById('order-note').value || '';
  let orderType = "С собой";
  cart.forEach(i => {
    if (i.name.toLowerCase().includes("доставка")) orderType = "Доставка";
  });

  const payload = {
    employee_id: window.EMPLOYEE_ID,
    items: cart.map(i => ({ id: i.id, name: i.name, price: i.price, qty: i.qty })),
    note,
    order_type: orderType
  };

  const res = await fetch('/orders/submit/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) return notify('Ошибка оформления заказа', "error");
  const data = await res.json();

  if (data.ok) {
    notify("✅ Заказ №" + data.receipt_number + " оформлен и чек напечатан!");
    clearCart();

    const pendingList = document.getElementById('pending-orders');
    if (pendingList) {
      const li = document.createElement('li');
      li.id = 'order-' + data.receipt_number;
      li.innerHTML = `
        <strong>Заказ №${data.receipt_number}</strong> — ${fmt(payload.items.reduce((s,i)=>s+i.price*i.qty,0))} сом
        <ul>${payload.items.map(i => `<li>${i.name} × ${i.qty}</li>`).join('')}</ul>
        <div><em>Тип заказа: ${orderType}</em></div>
        <button onclick="markReady(${data.receipt_number})">Готово</button>
      `;
      pendingList.appendChild(li);
    }
  } else {
    notify("Ошибка: " + (data.error || ""), "error");
  }
}



// ✅ Отметить заказ как готов
async function markReady(orderNumber) {
  const resp = await fetch(`/orders/${orderNumber}/ready/`);
  const data = await resp.json();
  if (data.ok) {
    const el = document.getElementById('order-' + orderNumber);
    if (el) el.remove();
    notify("Заказ №" + orderNumber + " готов!");
  } else {
    notify('Ошибка при смене статуса', "error");
  }
}

// 💰 Калькулятор сдачи
(function initChangeCalculator() {
  let cashInput = document.getElementById('cashGiven');
  let changeSpan = document.getElementById('changeAmount');
  let totalSpan = document.getElementById('cart-total');

  function getTotal() {
    const text = (totalSpan.textContent || '').replace(/[^\d.,]/g, '').replace(',', '.');
    const n = parseFloat(text);
    return isNaN(n) ? 0 : n;
  }

  function getCash() {
    const v = (cashInput.value || '').replace(',', '.');
    const n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  }

  window.updateChange = function updateChange() {
    if (!cashInput || !changeSpan || !totalSpan) return;
    const total = getTotal();
    const cash = getCash();
    const change = cash - total;
    changeSpan.textContent = change.toFixed(2);

    if (change >= 0) {
      changeSpan.classList.add('positive');
      changeSpan.classList.remove('negative');
    } else {
      changeSpan.classList.add('negative');
      changeSpan.classList.remove('positive');
    }
  };
})();

// 🎯 Инициализация событий
window.addEventListener('DOMContentLoaded', () => {
  // Показать PIN-модалку
  const urlParams = new URLSearchParams(window.location.search);
  const modal = document.getElementById('pinModal');
  if (modal) modal.style.display = urlParams.has('emp') ? 'none' : 'flex';

  // События корзины
  document.querySelectorAll('.item').forEach(el => {
    el.addEventListener('click', () => {
      addToCart(el.dataset.id, el.dataset.name, el.dataset.price);
    });
  });
  document.querySelectorAll('.cat-btn').forEach(el => {
    el.addEventListener('click', () => filterCategory(el.dataset.cat));
  });
  document.getElementById('btn-checkout').addEventListener('click', checkout);
  document.getElementById('btn-clear').addEventListener('click', clearCart);

  // Автообновление сдачи при изменении суммы
  const cashInput = document.getElementById('cashGiven');
  const cartTotal = document.getElementById('cart-total');
  if (cashInput) cashInput.addEventListener('input', updateChange);
  if (cartTotal) {
    const observer = new MutationObserver(updateChange);
    observer.observe(cartTotal, { childList: true });
  }
  updateChange();
});


