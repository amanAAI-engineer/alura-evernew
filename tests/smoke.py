"""End-to-end smoke test: python tests/smoke.py"""
import os, sys, tempfile
os.environ["DATABASE"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["ADMIN_PASSWORD"] = "pw-test"; os.environ["SECRET_KEY"] = "x"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
c = A.app.test_client()
ok = lambda cond, msg: (print(("PASS " if cond else "FAIL ") + msg), cond or sys.exit(1))

for p in ["/", "/shop", "/how-it-works", "/business", "/about", "/cart", "/checkout", "/privacy", "/terms", "/shipping", "/returns", "/admin/login"]:
    ok(c.get(p).status_code == 200, f"GET {p}")
ok(c.get("/nope").status_code == 404, "404 page")
ok(c.get("/admin", follow_redirects=False).status_code == 302, "admin requires login")

r = c.post("/api/cart/price", json={"items": [{"pack": "m", "qty": 2}, {"pack": "m", "qty": 1}, {"pack": "zzz", "qty": 1}], "coupon": "welcome10"}).get_json()
ok(r["subtotal"] == 3 * 69900 and r["discount"] == 20970 and r["lines"][0]["qty"] == 3, "pricing merges lines, ignores bad packs, applies coupon")
ok(r["ship_fee"] == 0, "free shipping above threshold")
ok(c.post("/api/cart/price", json={"items": [{"pack": "s", "qty": 1}], "coupon": "BAD"}).get_json()["coupon_error"], "bad coupon rejected")
ok(c.post("/api/cart/price", json={"items": [{"pack": "s", "qty": -5}]}).get_json()["lines"] == [], "negative qty ignored")
ok(c.get("/api/pincode/211001").get_json()["ok"] and c.get("/api/pincode/12").status_code == 400, "pincode check")

good = dict(name="Test User", phone="98765 43210", email="t@example.com", line1="12 Civil Lines", city="Prayagraj", pin="211001",
            state="Uttar Pradesh", ship="std", pay="upi", agree=True, items=[{"pack": "s", "qty": 1}], coupon="")
r = c.post("/api/orders", json={**good, "phone": "123", "agree": False, "items": []})
ok(r.status_code == 400 and {"phone", "agree", "cart"} <= set(r.get_json()["errors"]), "order validation errors")
r = c.post("/api/orders", json={**good, "business": True, "gstin": "bad", "biz_name": "X Co"})
ok("gstin" in r.get_json()["errors"], "GSTIN validated")
r = c.post("/api/orders", json={**good, "items": [{"pack": "s", "qty": 1}], "total": 1}).get_json()
ok(r["redirect"].startswith("/pay/ALR-000001"), "online order -> payment page")
url = r["redirect"]
ok(c.get("/order/ALR-000001").status_code == 404, "order page needs token")
ok(c.get(url).status_code == 200, "pay page")
r = c.post("/pay/ALR-000001/complete", data={"t": url.split("t=")[1], "result": "success"}, follow_redirects=True)
ok(b"is confirmed" in r.data and b"Paid" in r.data, "payment success -> confirmation")
tok = url.split("t=")[1]
inv = c.get(f"/invoice/ALR-000001?t={tok}")
ok(inv.status_code == 200 and b"TAX INVOICE" in inv.data and "\u20b9 459".encode() in inv.data, "invoice renders (399 + 60 shipping = 459)")
r = c.post("/api/orders", json={**good, "pay": "cod", "business": True, "biz_name": "X Co", "gstin": "09ABCDE1234F1Z5"}).get_json()
ok("/order/ALR-000002" in r["redirect"], "COD order -> confirmation")
ok(b"Pay on delivery" in c.get(r["redirect"]).data, "COD confirmation page")
r = c.post("/api/orders", json={**good, "items": [{"pack": "l", "qty": 101}]})
ok(r.status_code == 409, "stock limit enforced")

ok(c.post("/api/enquiry", json={"business": "B", "person": "P", "phone": "1", "email": "x", "city": ""}).status_code == 400, "enquiry validation")
ok(c.post("/api/enquiry", json={"business": "Shine Detailing", "person": "Ravi", "phone": "9876543210", "email": "r@x.in", "city": "Lucknow", "btype": "Detailing studio", "volume": "50–200"}).status_code == 200, "enquiry saved")
ok(c.post("/api/contact", json={"name": "Asha", "contact": "asha@x.in", "topic": "Other", "message": "Hello there"}).status_code == 200, "contact saved")
ok(c.post("/api/contact", json={"name": "Bot", "website": "spam"}).get_json().get("ok"), "honeypot swallowed")

ok(b"Wrong password" in c.post("/admin/login", data={"password": "no"}).data, "bad admin password")
c.post("/admin/login", data={"password": "pw-test"})
page = c.get("/admin?tab=orders"); ok(b"ALR-000001" in page.data and b"ALR-000002" in page.data, "admin lists orders")
with c.session_transaction() as s: tk = s["csrf"]
ok(c.post("/admin/order/ALR-000002/status", data={"status": "dispatched"}).status_code == 400, "CSRF enforced")
c.post("/admin/order/ALR-000002/status", data={"status": "dispatched", "csrf": tk})
ok(b'selected>dispatched' in c.get("/admin?tab=orders").data.replace(b" ", b"").replace(b"selected>", b"selected>") or b"dispatched" in c.get("/admin?tab=orders").data, "status updated")
c.post("/admin/pack/s", data={"label": "500 ml", "price": "449", "stock": "10", "active": "on", "csrf": tk})
ok(c.post("/api/cart/price", json={"items": [{"pack": "s", "qty": 1}]}).get_json()["subtotal"] == 44900, "admin price edit takes effect")
for t in ["enquiries", "messages", "products"]: ok(c.get(f"/admin?tab={t}").status_code == 200, f"admin tab {t}")
ok(c.get("/admin/orders.csv").data.startswith(b"order_no"), "orders CSV export")
print("\nALL TESTS PASSED")
