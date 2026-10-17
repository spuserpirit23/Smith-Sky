import os
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request, session
from flask_cors import CORS

from .auth import admin_required, cafe_required, login_required, verify_password
from .db import fetch_all, fetch_one, get_conn


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower()
        == "true",
    )

    origin = os.environ.get("WORDPRESS_ORIGIN", "http://localhost:8080")
    CORS(app, origins=[origin], supports_credentials=True)

    register_routes(app)
    return app


def json_error(message, status=400, code="bad_request"):
    return jsonify({"error": code, "message": message}), status


def require_positive_int(value, label):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a whole number.")
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return parsed


def register_routes(app):
    @app.get("/")
    def index():
        return jsonify({
            "service": "smith-sky-cafe",
            "health": "/api/v1/health",
            "api_prefix": "/api/v1",
        })

    @app.get("/api/v1/health")
    def health():
        db_status = "ok"

        try:
            with get_conn() as conn:
                conn.execute("SELECT 1")
        except Exception:
            app.logger.exception("Database health check failed")
            db_status = "error"

        status_code = 200 if db_status == "ok" else 503

        return jsonify({
            "ok": db_status == "ok",
            "service": "smith-sky-cafe",
            "database": db_status
        }), status_code

    @app.post("/api/v1/auth/login")
    def login():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        user = fetch_one(
            "SELECT id, email, full_name, role, password_hash, active FROM app_users WHERE email = %(email)s",
            {"email": email},
        )
        if not user or not user["active"] or not verify_password(user["password_hash"], password):
            return json_error("Invalid email or password.", 401, "invalid_login")
        session.clear()
        session["user_id"] = user["id"]
        return jsonify({"user": public_user(user)})

    @app.post("/api/v1/auth/logout")
    @login_required
    def logout(user):
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/v1/me")
    @login_required
    def me(user):
        payload = {"user": public_user(user)}
        if user["role"] == "cafe_staff":
            payload["cafe"] = fetch_one(
                """
                SELECT c.id, c.name
                FROM cafe_user_assignments cua
                JOIN cafes c ON c.id = cua.cafe_id
                WHERE cua.user_id = %(user_id)s AND cua.active = true AND c.status = 'active'
                LIMIT 1
                """,
                {"user_id": user["id"]},
            )
        return jsonify(payload)

    @app.get("/api/v1/products")
    @login_required
    def products(user):
        rows = fetch_all(
            """
            SELECT id, sku, name, unit_price_minor, currency, active, low_stock_threshold
            FROM products
            WHERE active = true
            ORDER BY name
            """
        )
        return jsonify({"products": rows})

    @app.get("/api/v1/admin/cafes")
    @admin_required
    def admin_cafes(user):
        rows = fetch_all(
            """
            SELECT c.id, c.name, c.address, c.status, c.created_at,
                   COALESCE(SUM(sm.quantity_delta), 0)::int AS total_stock
            FROM cafes c
            LEFT JOIN stock_movements sm ON sm.cafe_id = c.id AND sm.voided_at IS NULL
            GROUP BY c.id
            ORDER BY c.name
            """
        )
        return jsonify({"cafes": rows})

    @app.post("/api/v1/admin/cafes")
    @admin_required
    def create_cafe(user):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return json_error("Cafe name is required.")
        with get_conn() as conn:
            row = conn.execute(
                """
                INSERT INTO cafes (name, address, status)
                VALUES (%(name)s, %(address)s, 'active')
                RETURNING id, name, address, status, created_at
                """,
                {"name": name, "address": (data.get("address") or "").strip()},
            ).fetchone()
        return jsonify({"cafe": row}), 201

    @app.post("/api/v1/admin/deliveries")
    @admin_required
    def create_delivery(user):
        data = request.get_json(silent=True) or {}
        items = data.get("items") or []
        try:
            cafe_id = require_positive_int(data.get("cafe_id"), "Cafe")
            normalized = normalize_items(items)
        except ValueError as exc:
            return json_error(str(exc))

        reference = (data.get("reference") or "").strip() or None
        notes = (data.get("notes") or "").strip() or None
        delivery_at = data.get("delivery_at") or datetime.now(timezone.utc).isoformat()

        with get_conn() as conn:
            cafe = conn.execute(
                "SELECT id FROM cafes WHERE id = %(cafe_id)s AND status = 'active'",
                {"cafe_id": cafe_id},
            ).fetchone()
            if not cafe:
                return json_error("Cafe was not found.", 404, "not_found")

            delivery = conn.execute(
                """
                INSERT INTO deliveries (cafe_id, delivery_at, created_by, reference, notes, status)
                VALUES (%(cafe_id)s, %(delivery_at)s, %(created_by)s, %(reference)s, %(notes)s, 'posted')
                RETURNING id, cafe_id, delivery_at, reference, notes, status
                """,
                {
                    "cafe_id": cafe_id,
                    "delivery_at": delivery_at,
                    "created_by": user["id"],
                    "reference": reference,
                    "notes": notes,
                },
            ).fetchone()

            for item in normalized:
                try:
                    ensure_product(conn, item["product_id"])
                except ValueError as exc:
                    return json_error(str(exc), 404, "not_found")
                conn.execute(
                    """
                    INSERT INTO delivery_items (delivery_id, product_id, quantity)
                    VALUES (%(delivery_id)s, %(product_id)s, %(quantity)s)
                    """,
                    {"delivery_id": delivery["id"], **item},
                )
                conn.execute(
                    """
                    INSERT INTO stock_movements
                      (cafe_id, product_id, quantity_delta, movement_type, reference_type, reference_id, actor_user_id)
                    VALUES
                      (%(cafe_id)s, %(product_id)s, %(quantity)s, 'delivery', 'delivery', %(delivery_id)s, %(actor)s)
                    """,
                    {
                        "cafe_id": cafe_id,
                        "product_id": item["product_id"],
                        "quantity": item["quantity"],
                        "delivery_id": delivery["id"],
                        "actor": user["id"],
                    },
                )

        return jsonify({"delivery": delivery}), 201

    @app.get("/api/v1/admin/stock")
    @admin_required
    def admin_stock(user):
        cafe_id = request.args.get("cafe_id")
        params = {"cafe_id": int(cafe_id)} if cafe_id else {}
        cafe_filter = "AND c.id = %(cafe_id)s" if cafe_id else ""
        rows = fetch_all(
            f"""
            SELECT c.id AS cafe_id, c.name AS cafe_name, p.id AS product_id, p.name AS product_name,
                   p.low_stock_threshold,
                   COALESCE(SUM(sm.quantity_delta), 0)::int AS available_stock
            FROM cafes c
            CROSS JOIN products p
            LEFT JOIN stock_movements sm
              ON sm.cafe_id = c.id AND sm.product_id = p.id AND sm.voided_at IS NULL
            WHERE c.status = 'active' AND p.active = true {cafe_filter}
            GROUP BY c.id, p.id
            ORDER BY c.name, p.name
            """,
            params,
        )
        return jsonify({"stock": rows, "updated_at": utc_now()})

    @app.get("/api/v1/admin/reports/sales")
    @admin_required
    def admin_sales_report(user):
        rows = fetch_all(
            """
            SELECT c.name AS cafe_name, p.name AS product_name,
                   SUM(si.quantity)::int AS units_sold,
                   SUM(si.quantity * si.unit_price_minor)::bigint AS sales_value_minor,
                   si.currency
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN cafes c ON c.id = s.cafe_id
            JOIN products p ON p.id = si.product_id
            WHERE s.status = 'posted'
            GROUP BY c.name, p.name, si.currency
            ORDER BY c.name, p.name
            """
        )
        return jsonify({"sales": rows})

    @app.post("/api/v1/admin/sales/<int:sale_id>/reverse")
    @admin_required
    def reverse_sale(user, sale_id):
        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "").strip()
        if not reason:
            return json_error("A reversal reason is required.")

        with get_conn() as conn:
            sale = conn.execute(
                """
                SELECT id, cafe_id, status
                FROM sales
                WHERE id = %(sale_id)s
                FOR UPDATE
                """,
                {"sale_id": sale_id},
            ).fetchone()
            if not sale:
                return json_error("Sale was not found.", 404, "not_found")
            if sale["status"] != "posted":
                return json_error("Only posted sales can be reversed.", 409, "already_reversed")

            items = conn.execute(
                """
                SELECT product_id, quantity
                FROM sale_items
                WHERE sale_id = %(sale_id)s
                """,
                {"sale_id": sale_id},
            ).fetchall()
            for item in items:
                conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (sale["cafe_id"], item["product_id"]))

            conn.execute(
                """
                UPDATE sales
                SET status = 'reversed',
                    reversed_by = %(actor)s,
                    reversed_at = now(),
                    reversal_reason = %(reason)s
                WHERE id = %(sale_id)s
                """,
                {"sale_id": sale_id, "actor": user["id"], "reason": reason},
            )

            for item in items:
                conn.execute(
                    """
                    INSERT INTO stock_movements
                      (cafe_id, product_id, quantity_delta, movement_type, reference_type, reference_id, actor_user_id)
                    VALUES
                      (%(cafe_id)s, %(product_id)s, %(quantity)s, 'reversal', 'sale', %(sale_id)s, %(actor)s)
                    """,
                    {
                        "cafe_id": sale["cafe_id"],
                        "product_id": item["product_id"],
                        "quantity": item["quantity"],
                        "sale_id": sale_id,
                        "actor": user["id"],
                    },
                )
        return jsonify({"ok": True, "sale_id": sale_id})

    @get_cafe_stock_route(app)
    def cafe_stock(user, cafe):
        rows = fetch_all(
            """
            SELECT p.id AS product_id, p.name AS product_name, p.sku, p.unit_price_minor, p.currency,
                   p.low_stock_threshold,
                   COALESCE(SUM(sm.quantity_delta), 0)::int AS available_stock
            FROM products p
            LEFT JOIN stock_movements sm
              ON sm.product_id = p.id AND sm.cafe_id = %(cafe_id)s AND sm.voided_at IS NULL
            WHERE p.active = true
            GROUP BY p.id
            ORDER BY p.name
            """,
            {"cafe_id": cafe["id"]},
        )
        return jsonify({"cafe": cafe, "stock": rows, "updated_at": utc_now()})

    @app.post("/api/v1/cafe/sales")
    @cafe_required
    def create_sale(user, cafe):
        data = request.get_json(silent=True) or {}
        items = data.get("items") or []
        try:
            normalized = normalize_items(items)
        except ValueError as exc:
            return json_error(str(exc))

        idempotency_key = (data.get("idempotency_key") or "").strip() or str(uuid.uuid4())
        transaction_ref = f"SS-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id, transaction_ref FROM sales WHERE cafe_id = %(cafe_id)s AND idempotency_key = %(key)s",
                {"cafe_id": cafe["id"], "key": idempotency_key},
            ).fetchone()
            if existing:
                return jsonify({"sale": existing, "duplicate": True})

            stock_by_product = lock_stock_rows(conn, cafe["id"], [i["product_id"] for i in normalized])
            for item in normalized:
                try:
                    product = ensure_product(conn, item["product_id"])
                except ValueError as exc:
                    return json_error(str(exc), 404, "not_found")
                available = stock_by_product.get(item["product_id"], 0)
                if item["quantity"] > available:
                    return json_error(
                        f"{product['name']} has only {available} available.",
                        409,
                        "insufficient_stock",
                    )

            sale = conn.execute(
                """
                INSERT INTO sales (cafe_id, transaction_ref, sold_at, created_by, status, idempotency_key)
                VALUES (%(cafe_id)s, %(transaction_ref)s, now(), %(created_by)s, 'posted', %(idempotency_key)s)
                RETURNING id, cafe_id, transaction_ref, sold_at, status
                """,
                {
                    "cafe_id": cafe["id"],
                    "transaction_ref": transaction_ref,
                    "created_by": user["id"],
                    "idempotency_key": idempotency_key,
                },
            ).fetchone()

            for item in normalized:
                product = ensure_product(conn, item["product_id"])
                conn.execute(
                    """
                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_minor, currency)
                    VALUES (%(sale_id)s, %(product_id)s, %(quantity)s, %(price)s, %(currency)s)
                    """,
                    {
                        "sale_id": sale["id"],
                        "product_id": item["product_id"],
                        "quantity": item["quantity"],
                        "price": product["unit_price_minor"],
                        "currency": product["currency"],
                    },
                )
                conn.execute(
                    """
                    INSERT INTO stock_movements
                      (cafe_id, product_id, quantity_delta, movement_type, reference_type, reference_id, actor_user_id)
                    VALUES
                      (%(cafe_id)s, %(product_id)s, %(quantity_delta)s, 'sale', 'sale', %(sale_id)s, %(actor)s)
                    """,
                    {
                        "cafe_id": cafe["id"],
                        "product_id": item["product_id"],
                        "quantity_delta": -item["quantity"],
                        "sale_id": sale["id"],
                        "actor": user["id"],
                    },
                )

        return jsonify({"sale": sale}), 201

    @app.get("/api/v1/cafe/sales")
    @cafe_required
    def cafe_sales(user, cafe):
        rows = fetch_all(
            """
            SELECT s.id, s.transaction_ref, s.sold_at, s.status,
                   SUM(si.quantity)::int AS item_count,
                   SUM(si.quantity * si.unit_price_minor)::bigint AS total_minor,
                   MIN(si.currency) AS currency
            FROM sales s
            JOIN sale_items si ON si.sale_id = s.id
            WHERE s.cafe_id = %(cafe_id)s
            GROUP BY s.id
            ORDER BY s.sold_at DESC
            LIMIT 100
            """,
            {"cafe_id": cafe["id"]},
        )
        return jsonify({"sales": rows})


def get_cafe_stock_route(app):
    def decorator(fn):
        app.get("/api/v1/cafe/stock")(cafe_required(fn))
        return fn

    return decorator


def public_user(user):
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
    }


def normalize_items(items):
    if not isinstance(items, list) or not items:
        raise ValueError("At least one line item is required.")
    merged = {}
    for item in items:
        product_id = require_positive_int(item.get("product_id"), "Product")
        quantity = require_positive_int(item.get("quantity"), "Quantity")
        merged[product_id] = merged.get(product_id, 0) + quantity
    return [{"product_id": product_id, "quantity": quantity} for product_id, quantity in merged.items()]


def ensure_product(conn, product_id):
    product = conn.execute(
        """
        SELECT id, name, unit_price_minor, currency
        FROM products
        WHERE id = %(product_id)s AND active = true
        """,
        {"product_id": product_id},
    ).fetchone()
    if not product:
        raise ValueError(f"Product {product_id} is inactive or missing.")
    return product


def lock_stock_rows(conn, cafe_id, product_ids):
    # Advisory transaction locks serialize stock decrements per cafe/product.
    for product_id in sorted(set(product_ids)):
        conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (cafe_id, product_id))
    rows = conn.execute(
        """
        SELECT product_id, COALESCE(SUM(quantity_delta), 0)::int AS available_stock
        FROM stock_movements
        WHERE cafe_id = %(cafe_id)s
          AND product_id = ANY(%(product_ids)s)
          AND voided_at IS NULL
        GROUP BY product_id
        """,
        {"cafe_id": cafe_id, "product_ids": list(set(product_ids))},
    ).fetchall()
    return {row["product_id"]: row["available_stock"] for row in rows}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


app = create_app()
