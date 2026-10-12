import os
import sqlite3
import secrets
import string
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'available',  -- available, sold
            order_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',  -- pending, paid, cancelled
            card_id INTEGER,
            payment_method TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (card_id) REFERENCES cards(id)
        )
    """)
    # Default admin
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    # Insert default admin if not exists
    c.execute("SELECT COUNT(*) FROM admins")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO admins (username, password) VALUES (?, ?)", ("admin", "admin123"))
    conn.commit()
    conn.close()

def generate_card_code(length=16):
    chars = string.ascii_uppercase + string.digits
    return "-".join(["".join(secrets.choice(chars) for _ in range(4)) for _ in range(4)])

@app.route("/")
def index():
    conn = get_db()
    products = conn.execute("""
        SELECT p.*, 
               (SELECT COUNT(*) FROM cards WHERE product_id = p.id AND status = 'available') as stock
        FROM products p
        ORDER BY p.id DESC
    """).fetchall()
    conn.close()
    return render_template("index.html", products=products)

@app.route("/product/<int:pid>")
def product_detail(pid):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if not product:
        return "商品不存在", 404
    stock = conn.execute("SELECT COUNT(*) FROM cards WHERE product_id = ? AND status = 'available'", (pid,)).fetchone()[0]
    conn.close()
    return render_template("product.html", product=product, stock=stock)

@app.route("/buy/<int:pid>", methods=["GET", "POST"])
def buy(pid):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if not product:
        return "商品不存在", 404
    stock = conn.execute("SELECT COUNT(*) FROM cards WHERE product_id = ? AND status = 'available'", (pid,)).fetchone()[0]
    if stock <= 0:
        flash("库存不足", "error")
        return redirect(url_for("product_detail", pid=pid))
    
    if request.method == "POST":
        # Create pending order
        order_id = conn.execute(
            "INSERT INTO orders (product_id, amount, status) VALUES (?, ?, 'pending')",
            (pid, product["price"])
        ).lastrowid
        conn.commit()
        conn.close()
        return redirect(url_for("pay", order_id=order_id))
    
    conn.close()
    return render_template("buy.html", product=product, stock=stock)

@app.route("/pay/<int:order_id>")
def pay(order_id):
    conn = get_db()
    order = conn.execute("""
        SELECT o.*, p.name as product_name 
        FROM orders o 
        JOIN products p ON o.product_id = p.id 
        WHERE o.id = ?
    """, (order_id,)).fetchone()
    conn.close()
    if not order or order["status"] != "pending":
        return "订单无效", 404
    return render_template("pay.html", order=order)

@app.route("/pay/confirm/<int:order_id>", methods=["POST"])
def confirm_pay(order_id):
    method = request.form.get("method", "模拟支付")
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ? AND status = 'pending'", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"success": False, "msg": "订单无效"}), 400
    
    # Find an available card
    card = conn.execute(
        "SELECT * FROM cards WHERE product_id = ? AND status = 'available' LIMIT 1",
        (order["product_id"],)
    ).fetchone()
    if not card:
        conn.close()
        return jsonify({"success": False, "msg": "库存不足"}), 400
    
    # Assign card and mark paid
    conn.execute(
        "UPDATE cards SET status = 'sold', order_id = ? WHERE id = ?",
        (order_id, card["id"])
    )
    conn.execute(
        "UPDATE orders SET status = 'paid', card_id = ?, payment_method = ?, paid_at = CURRENT_TIMESTAMP WHERE id = ?",
        (card["id"], method, order_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "redirect": url_for("order_result", order_id=order_id)})

@app.route("/order/<int:order_id>")
def order_result(order_id):
    conn = get_db()
    order = conn.execute("""
        SELECT o.*, p.name as product_name, c.code as card_code
        FROM orders o
        JOIN products p ON o.product_id = p.id
        LEFT JOIN cards c ON o.card_id = c.id
        WHERE o.id = ?
    """, (order_id,)).fetchone()
    conn.close()
    if not order:
        return "订单不存在", 404
    return render_template("order.html", order=order)

# Admin routes
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        conn = get_db()
        admin = conn.execute("SELECT * FROM admins WHERE username = ? AND password = ?", (username, password)).fetchone()
        conn.close()
        if admin:
            session["admin"] = True
            session["admin_user"] = username
            return redirect(url_for("admin_dashboard"))
        else:
            flash("用户名或密码错误", "error")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    products = conn.execute("SELECT * FROM products").fetchall()
    recent_orders = conn.execute("""
        SELECT o.*, p.name as product_name 
        FROM orders o JOIN products p ON o.product_id = p.id 
        ORDER BY o.id DESC LIMIT 20
    """).fetchall()
    stats = conn.execute("""
        SELECT 
            (SELECT COUNT(*) FROM products) as product_count,
            (SELECT COUNT(*) FROM cards WHERE status='available') as available_cards,
            (SELECT COUNT(*) FROM orders WHERE status='paid') as paid_orders,
            (SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='paid') as total_revenue
    """).fetchone()
    conn.close()
    return render_template("admin.html", products=products, recent_orders=recent_orders, stats=stats)

@app.route("/admin/product/add", methods=["POST"])
@admin_required
def add_product():
    name = request.form.get("name")
    description = request.form.get("description", "")
    price = float(request.form.get("price", 0))
    if not name or price <= 0:
        flash("请填写有效的商品信息", "error")
        return redirect(url_for("admin_dashboard"))
    conn = get_db()
    conn.execute("INSERT INTO products (name, description, price) VALUES (?, ?, ?)", (name, description, price))
    conn.commit()
    conn.close()
    flash("商品添加成功", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/cards/generate", methods=["POST"])
@admin_required
def generate_cards():
    product_id = int(request.form.get("product_id"))
    count = int(request.form.get("count", 10))
    if count <= 0 or count > 1000:
        flash("数量无效", "error")
        return redirect(url_for("admin_dashboard"))
    conn = get_db()
    generated = 0
    for _ in range(count):
        code = generate_card_code()
        try:
            conn.execute("INSERT INTO cards (product_id, code) VALUES (?, ?)", (product_id, code))
            generated += 1
        except sqlite3.IntegrityError:
            continue  # rare collision
    conn.commit()
    conn.close()
    flash(f"成功生成 {generated} 张卡密", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/cards/<int:product_id>")
@admin_required
def view_cards(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    cards = conn.execute("SELECT * FROM cards WHERE product_id = ? ORDER BY id DESC", (product_id,)).fetchall()
    conn.close()
    return render_template("admin_cards.html", product=product, cards=cards)

# Initialize DB on startup
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
