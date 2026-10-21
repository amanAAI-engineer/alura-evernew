/* ALURA EverNew - shared client code. Prices always come from the server (/api/cart/price). */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const money = p => '₹ ' + (p / 100).toLocaleString('en-IN', {minimumFractionDigits: p % 100 ? 2 : 0, maximumFractionDigits: 2});
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(path, body) {
  const opt = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  let res;
  try { res = await fetch(path, opt); } catch { return {ok: false, status: 0, data: {errors: {form: 'Network error. Please check your connection.'}}}; }
  let data = {}; try { data = await res.json(); } catch {}
  return {ok: res.ok, status: res.status, data};
}

const Cart = {
  key: 'alura_cart_v1',
  read() { try { return JSON.parse(localStorage.getItem(this.key)) || {items: [], coupon: ''}; } catch { return {items: [], coupon: ''}; } },
  write(c) { try { localStorage.setItem(this.key, JSON.stringify(c)); } catch {} this.badge(); },
  count() { return this.read().items.reduce((n, i) => n + i.qty, 0); },
  add(pack, qty) {
    const c = this.read(), it = c.items.find(i => i.pack === pack);
    it ? it.qty = Math.min(500, it.qty + qty) : c.items.push({pack, qty});
    this.write(c);
  },
  setQty(pack, qty) { const c = this.read(), it = c.items.find(i => i.pack === pack); if (it) it.qty = Math.max(1, Math.min(500, qty)); this.write(c); },
  remove(pack) { const c = this.read(); c.items = c.items.filter(i => i.pack !== pack); this.write(c); },
  setCoupon(code) { const c = this.read(); c.coupon = code; this.write(c); },
  clear() { this.write({items: [], coupon: ''}); },
  badge() { const b = $('#cart-count'); if (b) { const n = this.count(); b.textContent = n || ''; b.dataset.n = n; } }
};
Cart.badge();

let toastTimer;
function toast(html) {
  const t = $('#toast'); t.innerHTML = html; t.classList.add('on');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('on'), 4000);
}

/* Show validation errors returned by the server next to each field (inputs use name="..."). */
function showErrors(form, errors = {}) {
  $$('.err', form).forEach(e => e.remove());
  $$('.bad', form).forEach(e => e.classList.remove('bad'));
  let first;
  for (const [k, msg] of Object.entries(errors)) {
    const el = form.elements[k];
    const isInput = el && el.closest;
    const holder = $('[data-err="' + k + '"]', form) || (isInput ? (el.closest('label') || el.parentElement) : null);
    if (isInput) el.classList.add('bad');
    if (holder) { const p = document.createElement('div'); p.className = 'err'; p.setAttribute('role', 'alert'); p.textContent = msg; holder.appendChild(p); first = first || el || holder; }
  }
  if (first && first.scrollIntoView) first.scrollIntoView({block: 'center', behavior: 'smooth'});
}

/* Wire a simple POST-JSON form with a success panel: <form data-api="/api/x" data-done="#panel"> */
function wireForm(form, endpoint, onDone) {
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = form.querySelector('[type=submit]'); btn.disabled = true;
    const data = Object.fromEntries(new FormData(form));
    const r = await api(endpoint, data);
    btn.disabled = false;
    if (r.ok) { showErrors(form); onDone(); form.reset(); }
    else showErrors(form, r.data.errors || {form: 'Something went wrong. Please try again.'});
  });
}
