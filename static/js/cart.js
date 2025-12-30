let cart = [];

const fmt = v => Number(v).toFixed(2);

// 🔔 Функция уведомлений
function notify(msg, type="success") {
  const box = document.getElementById('notify');
  if (!box) return;
  box.textContent = msg;
  box.className = "notify " + (type === "error" ? "error show" : "show");
  setTimeout(() => {
    box.className = "notify"; // скрыть через 2 сек
  }, 2000);
}

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

async function toggleProblem(button, orderId) {
  const resp = await fetch(`/orders/${orderId}/toggle-paid/`);
  const data = await resp.json();
  if (data.ok) {
    const orderBlock = button.closest('.order-card');
    if (orderBlock) {
      orderBlock.classList.toggle('problem', !data.is_paid);
    }
  } else {
    notify('Ошибка при изменении статуса оплаты', "error");
  }
}

function addToCart(id, name, price) {
  const existing = cart.find(i => i.id === id);
  if (existing) existing.qty += 1;
  else cart.push({ id, name, price: Number(price), qty: 1 });
  renderCart();
}
function incQty(id) { const i = cart.find(x => x.id === id); if (i) { i.qty++; renderCart(); } }
function decQty(id) { const i = cart.find(x => x.id === id); if (i && i.qty > 1) { i.qty--; } else { removeItem(id); } renderCart(); }
function removeItem(id) { cart = cart.filter(i => i.id !== id); renderCart(); }
function clearCart() { cart = []; renderCart(); }

function filterCategory(cat) {
  document.querySelectorAll('.cat-btn').forEach(b => b.classList.toggle('active', b.dataset.cat === cat));
  document.querySelectorAll('.item').forEach(el => {
    el.style.display = (cat === 'all' || el.dataset.category === cat) ? '' : 'none';
  });
}

async function checkout() {
  if (!cart.length) return notify('Корзина пустая', "error");
  if (!window.EMPLOYEE_ID) return notify('Сначала войдите кассиром', "error");

  const note = document.getElementById('order-note').value || '';

  // 🔥 определяем тип заказа по блюду "Доставка"
  let orderType = "С собой"; // значение по умолчанию
  cart.forEach(i => {
    if (i.name.toLowerCase().includes("доставка")) {
      orderType = "Доставка";
    }
  });

  const payload = {
    employee_id: window.EMPLOYEE_ID,
    items: cart.map(i => ({ id: i.id, name: i.name, price: i.price, qty: i.qty })),
    note,
    order_type: orderType   // 👈 добавляем тип заказа
  };

  const res = await fetch('/orders/submit/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) return notify('Ошибка оформления заказа', "error");
  const data = await res.json();

  if (data.ok) {
    // ✅ используем receipt_number вместо order_number
    notify("✅ Заказ №" + data.receipt_number + " оформлен и чек напечатан!");
    clearCart();

    const pendingList = document.getElementById('pending-orders');
    if (pendingList) {
      const li = document.createElement('li');
      li.id = 'order-' + data.receipt_number;
      li.innerHTML = `
        <strong>Заказ №${data.receipt_number}</strong> — ${fmt(payload.items.reduce((s,i)=>s+i.price*i.qty,0))} сом
        <ul>
          ${payload.items.map(i => `<li>${i.name} × ${i.qty}</li>`).join('')}
        </ul>
        <div><em>Тип заказа: ${orderType}</em></div>
        <button onclick="markReady(${data.receipt_number})">Готово</button>
      `;
      pendingList.appendChild(li);
    }
  } else {
    notify("Ошибка: " + (data.error || ""), "error");
  }
}

window.addEventListener('DOMContentLoaded', () => {
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
});

function submitPin() {
  const pin = document.getElementById('pinInput').value.trim();
  if (!pin) return notify("Введите PIN", "error");

  fetch(`/employee/get-id/?pin=${pin}`)
    .then(res => res.json())
    .then(data => {
      if (data.id) {
        window.location.href = `/menu/?emp=${data.id}`;
      } else {
        notify("Неверный PIN", "error");
      }
    })
    .catch(err => {
      console.error("Ошибка при проверке PIN:", err);
      notify("Ошибка подключения", "error");
    });
}

window.onload = function() {
  const urlParams = new URLSearchParams(window.location.search);
  const modal = document.getElementById('pinModal');
  if (!urlParams.has('emp')) {
    if (modal) modal.style.display = 'flex';
  } else {
    if (modal) modal.style.display = 'none';
  }
};

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

// === Калькулятор сдачи ===
(function initChangeCalculator() {
  let cashInput, changeSpan, totalSpan;

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
    const change = Math.max(cash - total, 0);
    changeSpan.textContent = change.toFixed(2);
  };

  window.addEventListener('DOMContentLoaded', function() {
    cashInput = document.getElementById('cashGiven');
    changeSpan = document.getElementById('changeAmount');
    totalSpan = document.getElementById('cart-total');

    if (!cashInput || !changeSpan || !totalSpan) return;

    cashInput.addEventListener('input', window.updateChange);
    window.updateChange();
  });
})();



