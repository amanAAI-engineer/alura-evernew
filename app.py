"""ALURA EverNew - full-stack website (Flask + SQLite).

Run:  pip install -r requirements.txt  &&  python app.py
Config is via environment variables - see .env.example / README.md
"""
import csv
import io
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time
from datetime import date, timedelta
from email.message import EmailMessage

from flask import (Flask, Response, abort, g, jsonify, redirect,
                   render_template, request, session, url_for)

BASE = os.path.dirname(os.path.abspath(__file__))
INSTANCE = os.path.join(BASE, "instance")
os.makedirs(INSTANCE, exist_ok=True)
DB_PATH = os.environ.get("DATABASE", os.path.join(INSTANCE, "alura.db"))
GENERATED = []  # secrets created on first run (printed once at startup)


def _secret(filename, env, gen, label):
    if os.environ.get(env):
        return os.environ[env]
    path = os.path.join(INSTANCE, filename)
    if os.path.exists(path):
        return open(path).read().strip()
    value = gen()
    with open(path, "w") as f:
        f.write(value)
    if label != "SECRET_KEY":
        GENERATED.append((label, value))
    return value


app = Flask(__name__)
app.secret_key = _secret("secret_key.txt", "SECRET_KEY", lambda: secrets.token_hex(32), "SECRET_KEY")
ADMIN_PASSWORD = _secret("admin_password.txt", "ADMIN_PASSWORD", lambda: secrets.token_urlsafe(9), "Admin password")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("HTTPS", "").lower() == "true",
                  MAX_CONTENT_LENGTH=64 * 1024)
if os.environ.get("BEHIND_PROXY", "").lower() == "true":  # real client IP / https behind Caddy, Nginx, Render...
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ----------------------------------------------------------------- settings
SITE = {
    "company": os.environ.get("COMPANY_NAME", "ALURA Services Pvt. Ltd."),
    "address": os.environ.get("COMPANY_ADDRESS", "[Street address, city, state, PIN]"),
    "gstin": os.environ.get("COMPANY_GSTIN", "[Company GSTIN]"),
    "phone": os.environ.get("SUPPORT_PHONE", "[Phone number]"),
    "email": os.environ.get("SUPPORT_EMAIL", "[Email address]"),
    "hours": os.environ.get("SUPPORT_HOURS", "[Working days and hours]"),
    "year": date.today().year,
}
GST_RATE = float(os.environ.get("GST_RATE", "18"))  # prices are GST-inclusive
FREE_SHIP_ABOVE = int(os.environ.get("FREE_SHIPPING_ABOVE_RUPEES", "999")) * 100
COD_ENABLED = os.environ.get("COD_ENABLED", "true").lower() == "true"
PAYMENT_MODE = os.environ.get("PAYMENT_MODE", "demo")  # demo | (add your gateway)

SHIPPING = {
    "std": {"label": "Standard delivery", "fee": 6000, "metro": (2, 4), "rest": (4, 7)},
    "exp": {"label": "Express delivery", "fee": 15000, "metro": (1, 2), "rest": (2, 4)},
}
PAYMENTS = {
    "upi": ("UPI", "Pay with any UPI app"),
    "card": ("Credit / debit card", "Visa, Mastercard, RuPay"),
    "nb": ("Net banking", "All major banks"),
    "cod": ("Cash on delivery", "Pay when it arrives"),
}
STATES = ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
          "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa",
          "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka",
          "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur",
          "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan",
          "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"]
METRO_PREFIXES = ("11", "40", "56", "60", "70", "50", "38", "41")
ORDER_STATUSES = ["pending_payment", "confirmed", "dispatched", "delivered", "cancelled"]

# ----------------------------------------------------------------- database
SCHEMA = """
CREATE TABLE IF NOT EXISTS packs(
  id TEXT PRIMARY KEY, label TEXT NOT NULL, price INTEGER NOT NULL,
  stock INTEGER NOT NULL DEFAULT 1000, active INTEGER NOT NULL DEFAULT 1, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS coupons(
  code TEXT PRIMARY KEY, percent INTEGER NOT NULL, min_subtotal INTEGER DEFAULT 0, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT UNIQUE, token TEXT NOT NULL,
  name TEXT, phone TEXT, email TEXT, line1 TEXT, line2 TEXT, city TEXT, pin TEXT, state TEXT,
  biz_name TEXT, gstin TEXT, ship TEXT, ship_fee INTEGER, pay TEXT, pay_status TEXT, status TEXT,
  subtotal INTEGER, discount INTEGER, coupon TEXT, total INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS order_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, pack_id TEXT, label TEXT, unit_price INTEGER, qty INTEGER);
CREATE TABLE IF NOT EXISTS enquiries(
  id INTEGER PRIMARY KEY AUTOINCREMENT, business TEXT, person TEXT, phone TEXT, email TEXT, btype TEXT,
  city TEXT, volume TEXT, gstin TEXT, message TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, contact TEXT, topic TEXT, order_no TEXT, message TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, to_addr TEXT, subject TEXT, body TEXT, sent INTEGER DEFAULT 0,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    if not conn.execute("SELECT 1 FROM packs").fetchone():
        # SAMPLE prices (the design had placeholders) - edit them in /admin > Products
        conn.executemany("INSERT INTO packs(id,label,price,stock,sort) VALUES(?,?,?,?,?)",
                         [("s", "500 ml", 39900, 500, 1), ("m", "1 L", 69900, 500, 2), ("l", "5 L", 299900, 100, 3)])
        conn.execute("INSERT INTO coupons(code,percent,min_subtotal) VALUES('WELCOME10',10,0)")
    conn.commit()
    conn.close()


# ----------------------------------------------------------------- helpers
_hits = {}


def rate_limit(bucket, limit=10, window=600):
    """Tiny in-memory per-IP limiter (use Redis / a proxy limiter for multi-process deployments)."""
    now = time.time()
    key = (request.remote_addr, bucket)
    recent = [t for t in _hits.get(key, []) if now - t < window]
    if len(recent) >= limit:
        abort(429)
    recent.append(now)
    _hits[key] = recent


def clean(v, n=500):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def norm_phone(v):
    digits = re.sub(r"\D", "", str(v or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def add_business_days(start, n):
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def eta_range(pin, ship):
    zone = "metro" if str(pin).startswith(METRO_PREFIXES) else "rest"
    lo, hi = SHIPPING[ship][zone]
    a, b = add_business_days(date.today(), lo), add_business_days(date.today(), hi)
    return a, b


def fmt_range(a, b):
    return f"{a.strftime('%d %b')} - {b.strftime('%d %b %Y')}"


def send_email(to, subject, body):
    """Always logged to the outbox table; also sent via SMTP when SMTP_HOST is configured."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("INSERT INTO outbox(to_addr,subject,body) VALUES(?,?,?)", (to, subject, body))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    host = os.environ.get("SMTP_HOST")
    if not host or not to:
        return

    def work():
        try:
            msg = EmailMessage()
            msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "no-reply@localhost"))
            msg["To"], msg["Subject"] = to, subject
            msg.set_content(body)
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
                s.starttls()
                if os.environ.get("SMTP_USER"):
                    s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                s.send_message(msg)
            c = sqlite3.connect(DB_PATH)
            c.execute("UPDATE outbox SET sent=1 WHERE id=?", (row_id,))
            c.commit()
            c.close()
        except Exception as exc:  # never break an order because email failed
            print("[email] failed:", exc)

    threading.Thread(target=work, daemon=True).start()


def rupees(paise):
    return f"{paise / 100:,.2f}".rstrip("0").rstrip(".") if paise % 100 == 0 else f"{paise / 100:,.2f}"


app.jinja_env.filters["inr"] = lambda p: "\u20b9 " + rupees(int(p or 0))


@app.context_processor
def inject():
    return {"site": SITE, "cod_enabled": COD_ENABLED}


# ----------------------------------------------------------------- pricing
def price_cart(items, coupon_code=None, ship="std"):
    """Single source of truth for prices. The browser never decides what a customer pays."""
    merged = {}
    for it in items if isinstance(items, list) else []:
        try:
            pid, qty = str(it.get("pack")), int(it.get("qty"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 1 <= qty <= 500:
            merged[pid] = min(500, merged.get(pid, 0) + qty)
    lines, subtotal = [], 0
    for pid, qty in merged.items():
        p = db().execute("SELECT * FROM packs WHERE id=? AND active=1", (pid,)).fetchone()
        if not p:
            continue
        lines.append({"pack": pid, "label": p["label"], "unit": p["price"], "qty": qty,
                      "total": p["price"] * qty, "stock": p["stock"]})
        subtotal += p["price"] * qty
    discount, coupon_msg, applied = 0, None, None
    code = clean(coupon_code, 30).upper()
    if code:
        c = db().execute("SELECT * FROM coupons WHERE code=? AND active=1", (code,)).fetchone()
        if not c:
            coupon_msg = "That coupon code isn't valid."
        elif subtotal < c["min_subtotal"]:
            coupon_msg = f"This coupon needs a subtotal of at least \u20b9 {rupees(c['min_subtotal'])}."
        else:
            discount, applied = subtotal * c["percent"] // 100, code
    ship = ship if ship in SHIPPING else "std"
    after = subtotal - discount
    ship_fee = 0 if (not lines or after >= FREE_SHIP_ABOVE) else SHIPPING[ship]["fee"]
    total = after + ship_fee
    taxable = round(total / (1 + GST_RATE / 100))
    return {"lines": lines, "subtotal": subtotal, "discount": discount, "coupon": applied,
            "coupon_error": coupon_msg, "ship": ship, "ship_fee": ship_fee, "total": total,
            "gst_included": total - taxable, "count": sum(l["qty"] for l in lines),
            "free_ship_above": FREE_SHIP_ABOVE}


# ----------------------------------------------------------------- pages
def page(name, **ctx):
    return render_template(name, **ctx)


@app.get("/")
def home():
    return page("home.html")


@app.get("/shop")
def shop():
    packs = [dict(r) for r in db().execute("SELECT id,label,price,stock FROM packs WHERE active=1 ORDER BY sort")]
    return page("shop.html", packs=packs)


@app.get("/how-it-works")
def how():
    return page("how.html")


@app.get("/business")
def business():
    return page("business.html")


@app.get("/about")
def about():
    return page("about.html")


@app.get("/cart")
def cart():
    return page("cart.html")


@app.get("/checkout")
def checkout():
    return page("checkout.html", states=STATES, shipping=SHIPPING, payments=PAYMENTS)


LEGAL = {
    "privacy": ("Privacy policy", "We collect only what we need to process your order and answer your questions: name, contact details, delivery address and (for business orders) GSTIN. We do not sell your data."),
    "terms": ("Terms of sale", "ALURA EverNew is a professional interior protection treatment. It is sold for professional use and must be applied as directed. Do not use on glass or screens."),
    "shipping": ("Shipping & delivery", "Standard and express delivery are available across India. Estimated dates are shown at checkout; a tracking link is shared on dispatch."),
    "returns": ("Returns & refunds", "If your order arrives damaged or incorrect, contact us with your order number and we will make it right."),
}


@app.get("/<slug>")
def legal(slug):
    if slug not in LEGAL:
        abort(404)
    return page("legal.html", title=LEGAL[slug][0], body=LEGAL[slug][1])


# ----------------------------------------------------------------- public API
@app.post("/api/cart/price")
def api_price():
    d = request.get_json(silent=True) or {}
    return jsonify(price_cart(d.get("items"), d.get("coupon"), d.get("ship", "std")))


@app.get("/api/pincode/<pin>")
def api_pin(pin):
    if not re.fullmatch(r"[1-9]\d{5}", pin):
        return jsonify(ok=False, message="Enter a valid 6-digit pincode."), 400
    out = {}
    for sid in SHIPPING:
        a, b = eta_range(pin, sid)
        out[sid] = fmt_range(a, b)
    return jsonify(ok=True, message=f"Delivery available. Standard: {out['std']}.", eta=out)


def validate_order(d):
    e = {}
    if len(clean(d.get("name"))) < 2:
        e["name"] = "Enter your full name."
    if not norm_phone(d.get("phone")):
        e["phone"] = "Enter a valid 10-digit mobile number."
    if not EMAIL_RE.match(clean(d.get("email"))):
        e["email"] = "Enter a valid email address."
    if len(clean(d.get("line1"))) < 4:
        e["line1"] = "Enter your address."
    if len(clean(d.get("city"))) < 2:
        e["city"] = "Enter your city."
    if not re.fullmatch(r"[1-9]\d{5}", clean(d.get("pin"))):
        e["pin"] = "Enter a valid 6-digit PIN code."
    if clean(d.get("state")) not in STATES:
        e["state"] = "Select your state."
    if d.get("business"):
        if len(clean(d.get("biz_name"))) < 2:
            e["biz_name"] = "Enter your business name."
        if not GSTIN_RE.match(clean(d.get("gstin")).upper()):
            e["gstin"] = "Enter a valid 15-character GSTIN."
    if d.get("ship") not in SHIPPING:
        e["ship"] = "Choose a delivery option."
    if d.get("pay") not in PAYMENTS or (d.get("pay") == "cod" and not COD_ENABLED):
        e["pay"] = "Choose a payment method."
    if not d.get("agree"):
        e["agree"] = "Please confirm the checkbox above to continue."
    return e


@app.post("/api/orders")
def api_order():
    rate_limit("order", 20)
    d = request.get_json(silent=True) or {}
    if d.get("website"):  # honeypot: bots fill hidden fields
        return jsonify(ok=True)
    errors = validate_order(d)
    p = price_cart(d.get("items"), d.get("coupon"), d.get("ship", "std"))
    if not p["lines"]:
        errors["cart"] = "Your cart is empty."
    if errors:
        return jsonify(errors=errors), 400
    biz = bool(d.get("business"))
    pay = d["pay"]
    conn = db()
    try:
        for l in p["lines"]:  # atomic stock decrement
            cur = conn.execute("UPDATE packs SET stock=stock-? WHERE id=? AND stock>=?", (l["qty"], l["pack"], l["qty"]))
            if cur.rowcount == 0:
                conn.rollback()
                return jsonify(errors={"cart": f"Sorry, {l['label']} is low on stock. Please reduce the quantity."}), 409
        status, pay_status = ("confirmed", "cod") if pay == "cod" else ("pending_payment", "pending")
        token = secrets.token_urlsafe(16)
        cur = conn.execute(
            """INSERT INTO orders(token,name,phone,email,line1,line2,city,pin,state,biz_name,gstin,ship,ship_fee,
               pay,pay_status,status,subtotal,discount,coupon,total) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (token, clean(d["name"], 100), norm_phone(d["phone"]), clean(d["email"], 120).lower(),
             clean(d["line1"], 200), clean(d.get("line2"), 200), clean(d["city"], 80), clean(d["pin"]),
             clean(d["state"]), clean(d.get("biz_name"), 120) if biz else "",
             clean(d.get("gstin"), 15).upper() if biz else "", p["ship"], p["ship_fee"], pay, pay_status,
             status, p["subtotal"], p["discount"], p["coupon"], p["total"]))
        oid = cur.lastrowid
        order_no = f"ALR-{oid:06d}"
        conn.execute("UPDATE orders SET order_no=? WHERE id=?", (order_no, oid))
        conn.executemany("INSERT INTO order_items(order_id,pack_id,label,unit_price,qty) VALUES(?,?,?,?,?)",
                         [(oid, l["pack"], l["label"], l["unit"], l["qty"]) for l in p["lines"]])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if pay == "cod":
        notify_order(order_no)
        return jsonify(ok=True, redirect=url_for("order_page", order_no=order_no, t=token))
    return jsonify(ok=True, redirect=url_for("pay_page", order_no=order_no, t=token))


def get_order(order_no, token=None, allow_admin=True):
    o = db().execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if not o:
        abort(404)
    is_admin = allow_admin and session.get("admin")
    if not is_admin and not (token and secrets.compare_digest(token, o["token"])):
        abort(404)
    items = db().execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)).fetchall()
    return o, items


def notify_order(order_no):
    o = db().execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    items = db().execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)).fetchall()
    lines = "\n".join(f"  {i['label']} x {i['qty']}  \u20b9 {rupees(i['unit_price'] * i['qty'])}" for i in items)
    send_email(o["email"], f"ALURA EverNew order {order_no} confirmed",
               f"Hi {o['name']},\n\nThank you - your order {order_no} is confirmed.\n\n{lines}\n\n"
               f"Total: \u20b9 {rupees(o['total'])} ({PAYMENTS[o['pay']][0]})\n"
               f"Delivering to: {o['line1']}, {o['city']} {o['pin']}\n\n- {SITE['company']}")
    if os.environ.get("ADMIN_EMAIL"):
        send_email(os.environ["ADMIN_EMAIL"], f"New order {order_no}", f"{o['name']} - \u20b9 {rupees(o['total'])} - {o['pay']}")


@app.get("/order/<order_no>")
def order_page(order_no):
    o, items = get_order(order_no, request.args.get("t"))
    if o["pay_status"] == "pending":
        return redirect(url_for("pay_page", order_no=order_no, t=o["token"]))
    a, b = eta_range(o["pin"], o["ship"])
    return page("confirmed.html", o=o, items=items, eta=fmt_range(a, b), pay_label=PAYMENTS[o["pay"]][0])


@app.get("/invoice/<order_no>")
def invoice(order_no):
    o, items = get_order(order_no, request.args.get("t"))
    taxable = round(o["total"] / (1 + GST_RATE / 100))
    return page("invoice.html", o=o, items=items, taxable=taxable, gst=o["total"] - taxable, rate=GST_RATE,
                intra=(o["state"] == os.environ.get("COMPANY_STATE", "")), pay_label=PAYMENTS[o["pay"]][0])


# ----------------------------------------------------------------- payment (DEMO gateway)
# Replace this block with your real gateway (Razorpay / Cashfree / PayU ...): create a gateway order here,
# verify the signed callback/webhook, then call mark_paid(). See README "Going live with payments".
@app.get("/pay/<order_no>")
def pay_page(order_no):
    o, _ = get_order(order_no, request.args.get("t"))
    if o["pay_status"] != "pending":
        return redirect(url_for("order_page", order_no=order_no, t=o["token"]))
    return page("pay.html", o=o, demo=PAYMENT_MODE == "demo", pay_label=PAYMENTS[o["pay"]][0])


def mark_paid(order_no):
    db().execute("UPDATE orders SET pay_status='paid', status='confirmed' WHERE order_no=? AND pay_status='pending'", (order_no,))
    db().commit()
    notify_order(order_no)


@app.post("/pay/<order_no>/complete")
def pay_complete(order_no):
    if PAYMENT_MODE != "demo":
        abort(404)
    o, _ = get_order(order_no, request.form.get("t"), allow_admin=False)
    if request.form.get("result") == "success":
        mark_paid(order_no)
        return redirect(url_for("order_page", order_no=order_no, t=o["token"]))
    return page("pay.html", o=o, demo=True, failed=True, pay_label=PAYMENTS[o["pay"]][0])


# ----------------------------------------------------------------- forms
@app.post("/api/enquiry")
def api_enquiry():
    rate_limit("form", 10)
    d = request.get_json(silent=True) or {}
    if d.get("website"):
        return jsonify(ok=True)
    e = {}
    if len(clean(d.get("business"))) < 2: e["business"] = "Enter your business name."
    if len(clean(d.get("person"))) < 2: e["person"] = "Enter a contact person."
    if not norm_phone(d.get("phone")): e["phone"] = "Enter a valid 10-digit mobile number."
    if not EMAIL_RE.match(clean(d.get("email"))): e["email"] = "Enter a valid email."
    if len(clean(d.get("city"))) < 2: e["city"] = "Enter your city."
    if clean(d.get("gstin")) and not GSTIN_RE.match(clean(d["gstin"]).upper()): e["gstin"] = "That GSTIN doesn't look right."
    if e:
        return jsonify(errors=e), 400
    db().execute("INSERT INTO enquiries(business,person,phone,email,btype,city,volume,gstin,message) VALUES(?,?,?,?,?,?,?,?,?)",
                 (clean(d["business"], 120), clean(d["person"], 100), norm_phone(d["phone"]), clean(d["email"], 120),
                  clean(d.get("btype"), 60), clean(d["city"], 80), clean(d.get("volume"), 30),
                  clean(d.get("gstin"), 15).upper(), clean(d.get("message"), 2000)))
    db().commit()
    if os.environ.get("ADMIN_EMAIL"):
        send_email(os.environ["ADMIN_EMAIL"], f"Bulk enquiry: {clean(d['business'])}", f"{clean(d['person'])} - {clean(d['phone'])}")
    return jsonify(ok=True)


@app.post("/api/contact")
def api_contact():
    rate_limit("form", 10)
    d = request.get_json(silent=True) or {}
    if d.get("website"):
        return jsonify(ok=True)
    e = {}
    if len(clean(d.get("name"))) < 2: e["name"] = "Enter your name."
    c = clean(d.get("contact"), 120)
    if not (EMAIL_RE.match(c) or norm_phone(c)): e["contact"] = "Enter a valid email or mobile number."
    if len(clean(d.get("message"))) < 5: e["message"] = "Please write a short message."
    if e:
        return jsonify(errors=e), 400
    db().execute("INSERT INTO messages(name,contact,topic,order_no,message) VALUES(?,?,?,?,?)",
                 (clean(d["name"], 100), c, clean(d.get("topic"), 60), clean(d.get("order_no"), 20), clean(d["message"], 3000)))
    db().commit()
    if os.environ.get("ADMIN_EMAIL"):
        send_email(os.environ["ADMIN_EMAIL"], f"New message from {clean(d['name'])}", clean(d["message"], 3000))
    return jsonify(ok=True)


# ----------------------------------------------------------------- admin
def admin_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*a, **k)
    return wrapper


def csrf_ok():
    return secrets.compare_digest(request.form.get("csrf", ""), session.get("csrf", "x"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        rate_limit("login", 8)
        if secrets.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session.clear()
            session["admin"], session["csrf"] = True, secrets.token_hex(16)
            return redirect(url_for("admin"))
        error = "Wrong password."
    return page("admin_login.html", error=error)


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/admin")
@admin_required
def admin():
    tab = request.args.get("tab", "orders")
    d = db()
    ctx = {"tab": tab, "statuses": ORDER_STATUSES, "csrf": session["csrf"],
           "stats": d.execute("SELECT COUNT(*) n, COALESCE(SUM(total),0) rev FROM orders WHERE status NOT IN ('cancelled','pending_payment')").fetchone()}
    if tab == "orders":
        orders = d.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 200").fetchall()
        ctx["orders"] = [(o, d.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)).fetchall()) for o in orders]
    elif tab == "enquiries":
        ctx["rows"] = d.execute("SELECT * FROM enquiries ORDER BY id DESC LIMIT 200").fetchall()
    elif tab == "messages":
        ctx["rows"] = d.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 200").fetchall()
    elif tab == "products":
        ctx["packs"] = d.execute("SELECT * FROM packs ORDER BY sort").fetchall()
        ctx["coupons"] = d.execute("SELECT * FROM coupons").fetchall()
    return page("admin.html", **ctx)


@app.post("/admin/order/<order_no>/status")
@admin_required
def admin_status(order_no):
    if not csrf_ok():
        abort(400)
    status = request.form.get("status")
    if status in ORDER_STATUSES:
        db().execute("UPDATE orders SET status=? WHERE order_no=?", (status, order_no))
        if status == "delivered":
            db().execute("UPDATE orders SET pay_status='paid' WHERE order_no=? AND pay_status='cod'", (order_no,))
        db().commit()
        o = db().execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
        if o and status == "dispatched":
            send_email(o["email"], f"Your ALURA EverNew order {order_no} has been dispatched",
                       f"Hi {o['name']}, your order is on its way. Tracking details will be shared shortly.")
    return redirect(url_for("admin", tab="orders"))


@app.post("/admin/pack/<pid>")
@admin_required
def admin_pack(pid):
    if not csrf_ok():
        abort(400)
    try:
        price = int(round(float(request.form["price"]) * 100))
        stock = int(request.form["stock"])
        label = clean(request.form["label"], 30)
    except (KeyError, ValueError):
        abort(400)
    if price < 0 or stock < 0 or not label:
        abort(400)
    db().execute("UPDATE packs SET label=?, price=?, stock=?, active=? WHERE id=?",
                 (label, price, stock, 1 if request.form.get("active") else 0, pid))
    db().commit()
    return redirect(url_for("admin", tab="products"))


@app.post("/admin/coupon")
@admin_required
def admin_coupon():
    if not csrf_ok():
        abort(400)
    code = clean(request.form.get("code"), 30).upper()
    try:
        pct = max(1, min(90, int(request.form.get("percent", 0))))
    except ValueError:
        abort(400)
    if code:
        db().execute("INSERT OR REPLACE INTO coupons(code,percent,min_subtotal,active) VALUES(?,?,0,?)",
                     (code, pct, 1 if request.form.get("active", "1") else 0))
        db().commit()
    return redirect(url_for("admin", tab="products"))


@app.get("/admin/orders.csv")
@admin_required
def admin_csv():
    rows = db().execute("SELECT order_no,created,name,phone,email,city,pin,state,biz_name,gstin,ship,pay,pay_status,status,subtotal,discount,total FROM orders ORDER BY id DESC").fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(rows[0].keys() if rows else ["order_no"])
    for r in rows:
        w.writerow([r[k] / 100 if k in ("subtotal", "discount", "total") else r[k] for k in r.keys()])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=orders.csv"})


@app.after_request
def headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.errorhandler(404)
def nf(_):
    return page("legal.html", title="Page not found", body="We couldn't find that page."), 404


@app.errorhandler(429)
def too_many(_):
    if request.path.startswith("/api/"):
        return jsonify(errors={"form": "Too many attempts. Please try again in a few minutes."}), 429
    return "Too many requests", 429


init_db()

if __name__ == "__main__":
    for label, value in GENERATED:
        print(f"\n  >> {label} (saved in instance/): {value}\n")
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")),
            debug=os.environ.get("FLASK_DEBUG") == "1")
