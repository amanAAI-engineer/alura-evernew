# ALURA EverNew — full-stack website

Your 8 designed pages, now a working store: **Flask (Python) + SQLite**.

## Run it
```bash
pip install -r requirements.txt
python app.py            # → http://127.0.0.1:5000
```
First run prints your **admin password** (also saved in `instance/admin_password.txt`). Admin panel: `/admin`.

## What works
| Page | Real behaviour |
|---|---|
| Shop | Pack/qty picker, add to cart / buy now, pincode delivery check (`/api/pincode`) |
| Cart | Saved in the browser; every price is recalculated by the server; coupons (`WELCOME10` sample), undo remove |
| Checkout | Server-side validation (phone, email, PIN, state, GSTIN), standard/express delivery, UPI/card/net banking/COD, stock check, free-shipping threshold |
| Confirmation | Private link per order, delivery estimate, **GST invoice** (`/invoice/<order>`, print → PDF) |
| Business | Bulk enquiry form → database |
| About & Contact | Contact form → database |
| Admin `/admin` | Orders (update status, invoice link, CSV export), enquiries, messages, edit pack prices/stock, coupons |

Emails (order confirmation, dispatch) are always logged to the `outbox` table; set the `SMTP_*` variables to actually send them.

## Things you must fill in before launching
1. **Prices** — your design had placeholders, so I seeded *sample* prices (500 ml ₹399, 1 L ₹699, 5 L ₹2,999) and sample shipping (₹60 / ₹150). Change prices in **/admin → Products**; shipping fees/ETAs are in `SHIPPING` in `app.py`.
2. **Company details** — copy `.env.example` values into your environment (phone, email, address, GSTIN, state). They feed the footer, contact page and invoices.
3. **Payments** — `PAYMENT_MODE=demo` uses a *fake* payment page (no money moves). To take real payments, integrate Razorpay/Cashfree/PayU in the block marked `payment (DEMO gateway)` in `app.py`: create the gateway order in `pay_page`, verify the signed callback/webhook, then call `mark_paid(order_no)`. Don't go live without this. (COD works as-is.)
4. **GST** — prices are treated as GST-inclusive at `GST_RATE` (18%). Confirm the rate/HSN code and invoice format with your accountant.
5. **Legal pages** — Privacy/Terms/Shipping/Returns are short starter text (`LEGAL` in `app.py`). Replace with reviewed copy.
6. **Content placeholders** kept from your design: coverage per pack, shelf life, protection duration (FAQ), company story, product/before-after photos (drop images in `static/img/`).

## Deploying
```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:8000 app:app
```
Put it behind HTTPS (Nginx/Caddy or a host like Render/Railway/a VPS). Keep `instance/` on a persistent disk — it holds the database and secrets. The built-in rate limiter is per-process; use a proxy-level limiter for heavier traffic.

## Test
`python tests/smoke.py` — 40+ checks across pages, pricing, orders, payment, invoice, forms and admin.

## Structure
`app.py` (all backend) · `templates/` (pages) · `static/css/site.css` · `static/js/site.js` (cart + forms) · `tests/smoke.py`
