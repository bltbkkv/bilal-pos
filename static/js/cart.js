let cart = [];

const fmt = v => Number(v).toFixed(2);

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
      if (!data.is_paid) {
        orderBlock.classList.add('problem');
      } else {
        orderBlock.classList.remove('problem');
      }
    }
  } else {
    alert('Ошибка при изменении статуса оплаты');
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
  if (!cart.length) return alert('Корзина пустая');
  if (!window.EMPLOYEE_ID) return alert('Сначала войдите кассиром');

  const note = document.getElementById('order-note').value || '';
  const payload = {
    employee_id: window.EMPLOYEE_ID,
    items: cart.map(i => ({ id: i.id, name: i.name, price: i.price, qty: i.qty })),
    note
  };
  const res = await fetch('/orders/submit/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) return alert('Ошибка оформления заказа');
  const data = await res.json();
  // Открываем чек
  window.open(`/orders/${data.order_id}/receipt/`, '_blank');
  clearCart();

  // ✅ Добавляем заказ в список "Готовятся" на главном экране
  const pendingList = document.getElementById('pending-orders');
  if (pendingList) {
    const li = document.createElement('li');
    li.id = 'order-' + data.order_id;
    li.innerHTML = `
      <strong>Заказ №${data.order_id}</strong> — ${fmt(payload.items.reduce((s,i)=>s+i.price*i.qty,0))} сом
      <ul>
        ${payload.items.map(i => `<li>${i.name} × ${i.qty}</li>`).join('')}
      </ul>
      <button onclick="markReady(${data.order_id})">Готово</button>
    `;
    pendingList.appendChild(li);
  }
}

// Bind
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

// ✅ Вход по PIN с редиректом
function submitPin() {
  const pin = document.getElementById('pinInput').value.trim();
  if (!pin) {
    alert("Введите PIN");
    return;
  }
  fetch(`/employee/get-id/?pin=${pin}`)   // исправленный маршрут
    .then(res => res.json())
    .then(data => {
      if (data.id) {
        // Перенаправляем на меню с выбранным кассиром
        window.location.href = `/menu/?emp=${data.id}`;
      } else {
        alert("Неверный PIN");
      }
    })
    .catch(err => {
      console.error("Ошибка при проверке PIN:", err);
      alert("Ошибка подключения");
    });
}

// Автоматическое скрытие модалки, если кассир выбран
window.onload = function() {
  const urlParams = new URLSearchParams(window.location.search);
  const modal = document.getElementById('pinModal');
  if (!urlParams.has('emp')) {
    if (modal) modal.style.display = 'flex';
  } else {
    if (modal) modal.style.display = 'none';
  }
};

// ✅ Функция смены статуса заказа
async function markReady(orderId) {
  const resp = await fetch(`/orders/${orderId}/ready/`);
  const data = await resp.json();
  if (data.ok) {
    const el = document.getElementById('order-' + orderId);
    if (el) el.remove();
  } else {
    alert('Ошибка при смене статуса');
  }
}
// === Калькулятор сдачи ===
(function initChangeCalculator() {
  let cashInput, changeSpan, totalSpan;

  function getTotal() {
    // Всегда берём чистое число из #cart-total
    const text = (totalSpan.textContent || '').replace(/[^\d.,]/g, '').replace(',', '.');
    const n = parseFloat(text);
    return isNaN(n) ? 0 : n;
  }

  function getCash() {
    const v = (cashInput.value || '').replace(',', '.');
    const n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  }

  // Делаем доступной глобально — вызывается из renderCart()
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

    // Счёт при вводе
    cashInput.addEventListener('input', window.updateChange);

    // Первый рассчёт
    window.updateChange();
  });
})();