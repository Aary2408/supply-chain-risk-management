import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import mysql.connector
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from database import get_connection

logger = logging.getLogger(__name__)


@dataclass
class APIError(Exception):
    status_code: int
    message: str


ENTITY_FIELDS = {
    "suppliers": {
        "table": "suppliers",
        "key": ("supplier_id",),
        "required": ("supplier_code", "supplier_name"),
        "fields": {
            "supplier_code": ("string", 30, False),
            "supplier_name": ("string", 150, False),
            "contact_name": ("string", 120, True),
            "email": ("email", 254, True),
            "phone": ("string", 30, True),
            "address": ("string", 500, True),
            "lead_time_days": ("integer", None, False),
            "is_active": ("boolean", None, False),
        },
    },
    "materials": {
        "table": "materials",
        "key": ("material_id",),
        "required": ("sku", "material_name", "unit_of_measure"),
        "fields": {
            "sku": ("string", 50, False),
            "material_name": ("string", 150, False),
            "category": ("string", 100, True),
            "unit_of_measure": ("string", 30, False),
            "reorder_level": ("integer", None, False),
            "safety_stock": ("integer", None, False),
            "is_active": ("boolean", None, False),
        },
    },
    "warehouses": {
        "table": "warehouses",
        "key": ("warehouse_id",),
        "required": ("warehouse_code", "warehouse_name", "location"),
        "fields": {
            "warehouse_code": ("string", 30, False),
            "warehouse_name": ("string", 150, False),
            "location": ("string", 255, False),
            "is_active": ("boolean", None, False),
        },
    },
    "inventory": {
        "table": "inventory",
        "key": ("material_id", "warehouse_id"),
        "required": ("material_id", "warehouse_id", "quantity_on_hand"),
        "fields": {
            "material_id": ("positive_integer", None, False),
            "warehouse_id": ("positive_integer", None, False),
            "quantity_on_hand": ("integer", None, False),
        },
    },
}


def _database_query(sql, params=(), fetch_one=False, write=False):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, params)
        if write:
            connection.commit()
            return {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}
        return cursor.fetchone() if fetch_one else cursor.fetchall()
    except mysql.connector.IntegrityError as exc:
        if connection:
            connection.rollback()
        raise APIError(409, "The request conflicts with existing database data.") from exc
    except mysql.connector.Error as exc:
        if connection:
            connection.rollback()
        api_error = _database_api_error(exc)
        if api_error.status_code == 503:
            logger.exception("Database operation failed")
        else:
            logger.warning("Database rejected operation: %s", exc)
        raise api_error from exc
    except (RuntimeError, ValueError) as exc:
        if connection:
            connection.rollback()
        logger.exception("Database operation failed")
        raise APIError(503, "The database operation could not be completed.") from exc
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def _database_api_error(error):
    if getattr(error, "errno", None) == 1644 or getattr(error, "sqlstate", None) == "45000":
        return APIError(409, "The request conflicts with the current database state.")
    return APIError(503, "The database operation could not be completed.")


def _database_transaction(operation):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        result = operation(connection, cursor)
        connection.commit()
        return result
    except APIError:
        if connection:
            connection.rollback()
        raise
    except mysql.connector.IntegrityError as exc:
        if connection:
            connection.rollback()
        raise APIError(409, "The request conflicts with existing database data.") from exc
    except mysql.connector.Error as exc:
        if connection:
            connection.rollback()
        api_error = _database_api_error(exc)
        if api_error.status_code == 503:
            logger.exception("Database transaction failed")
        else:
            logger.warning("Database rejected transaction: %s", exc)
        raise api_error from exc
    except (RuntimeError, ValueError) as exc:
        if connection:
            connection.rollback()
        logger.exception("Database transaction failed")
        raise APIError(503, "The database operation could not be completed.") from exc
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def _positive_int(value, field, maximum=4294967295):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise APIError(400, f"{field} must be a positive integer.")
    return value


def _nonnegative_int(value, field, maximum=4294967295):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise APIError(400, f"{field} must be a non-negative integer.")
    return value


def _string_value(value, field, max_length, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise APIError(400, f"{field} must be a string.")
    value = value.strip()
    if required and not value:
        raise APIError(400, f"{field} cannot be empty.")
    if len(value) > max_length:
        raise APIError(400, f"{field} must be at most {max_length} characters.")
    return value


def _date_value(value, field, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise APIError(400, f"{field} must be an ISO date.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise APIError(400, f"{field} must be an ISO date (YYYY-MM-DD).") from exc


def _datetime_value(value, field, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise APIError(400, f"{field} must be an ISO datetime.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise APIError(400, f"{field} must be a valid ISO datetime.") from exc
    if parsed.tzinfo is not None:
        raise APIError(400, f"{field} must not include a timezone.")
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _money_value(value, field):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise APIError(400, f"{field} must be a non-negative amount.")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise APIError(400, f"{field} must be a valid amount.") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999.99"):
        raise APIError(400, f"{field} is outside the allowed range.")
    if amount.as_tuple().exponent < -2:
        raise APIError(400, f"{field} may have at most two decimal places.")
    return amount


def _validated_order_items(items):
    if not isinstance(items, list) or not items:
        raise APIError(400, "items must be a non-empty array.")
    validated = []
    materials = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise APIError(400, f"items[{index}] must be an object.")
        if set(item) != {"material_id", "quantity_ordered", "unit_cost"}:
            raise APIError(
                400,
                f"items[{index}] must contain material_id, quantity_ordered, and unit_cost.",
            )
        material_id = _positive_int(item["material_id"], f"items[{index}].material_id",
                                    maximum=18446744073709551615)
        if material_id in materials:
            raise APIError(400, "Each material may appear only once per purchase order.")
        materials.add(material_id)
        validated.append(
            (
                material_id,
                _positive_int(item["quantity_ordered"], f"items[{index}].quantity_ordered"),
                _money_value(item["unit_cost"], f"items[{index}].unit_cost"),
            )
        )
    return validated


def _validate_payload(payload, fields, required):
    if not isinstance(payload, dict):
        raise APIError(400, "The request body must be a JSON object.")

    unknown = set(payload) - set(fields)
    if unknown:
        raise APIError(400, f"Unknown field(s): {', '.join(sorted(unknown))}.")

    missing = set(required) - set(payload)
    if missing:
        raise APIError(400, f"Missing required field(s): {', '.join(sorted(missing))}.")

    validated = {}
    for name, value in payload.items():
        kind, max_length, nullable = fields[name]
        if value is None and nullable:
            validated[name] = None
        elif kind in ("integer", "positive_integer"):
            if isinstance(value, bool) or not isinstance(value, int):
                raise APIError(400, f"{name} must be an integer.")
            minimum = 1 if kind == "positive_integer" else 0
            maximum = (
                18446744073709551615
                if kind == "positive_integer"
                else 4294967295
            )
            if value < minimum or value > maximum:
                raise APIError(400, f"{name} is outside the allowed range.")
            validated[name] = value
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise APIError(400, f"{name} must be true or false.")
            validated[name] = value
        elif kind in ("string", "email"):
            if not isinstance(value, str):
                raise APIError(400, f"{name} must be a string.")
            value = value.strip()
            if not value and not nullable:
                raise APIError(400, f"{name} cannot be empty.")
            if len(value) > max_length:
                raise APIError(400, f"{name} must be at most {max_length} characters.")
            if kind == "email" and value and not re.fullmatch(
                r"[^@\s]+@[^@\s]+\.[^@\s]+", value
            ):
                raise APIError(400, "email must be a valid email address.")
            validated[name] = value
        else:
            raise RuntimeError(f"Unsupported validation type: {kind}")
    return validated


def _json_payload():
    if not request.is_json:
        raise APIError(400, "Content-Type must be application/json.")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError(400, "The request body must be a valid JSON object.")
    return payload


def create_app():
    app = Flask(__name__)

    @app.errorhandler(APIError)
    def handle_api_error(error):
        return jsonify(error={"message": error.message}), error.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify(error={"message": error.description}), error.code

    @app.get("/")
    def homepage():
        if (
            request.accept_mimetypes["text/html"]
            > request.accept_mimetypes["application/json"]
        ):
            return render_template("dashboard.html", active_page="dashboard")
        return jsonify(
            application="Supply Chain Risk & Inventory Management System",
            status="running",
            links={
                "health": "/health",
                "suppliers": "/api/suppliers",
                "materials": "/api/materials",
                "warehouses": "/api/warehouses",
                "inventory": "/api/inventory",
                "low_stock": "/api/inventory/low-stock",
                "supplier_performance": "/api/reports/supplier-performance",
            },
        )

    @app.get("/dashboard")
    def dashboard():
        return render_template("dashboard.html", active_page="dashboard")

    ui_pages = (
        "inventory",
        "suppliers",
        "materials",
        "warehouses",
        "purchase-orders",
        "shipments",
        "deliveries",
        "inspections",
        "risk-reports",
    )

    def render_ui_page(page):
        return render_template("management.html", active_page=page, page=page)

    for page in ui_pages:
        app.add_url_rule(
            f"/{page}",
            endpoint=f"ui_{page.replace('-', '_')}",
            view_func=lambda page=page: render_ui_page(page),
        )

    @app.get("/health")
    def health():
        connection = None
        cursor = None
        try:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return jsonify(status="ok", database="connected")
        except (mysql.connector.Error, RuntimeError, ValueError):
            app.logger.exception("Database health check failed")
            return jsonify(status="error", database="unavailable"), 503
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    @app.get("/api/inventory/low-stock")
    def low_stock():
        rows = _database_query(
            "SELECT * FROM v_inventory_reorder_status "
            "WHERE reorder_required = %s ORDER BY material_id, warehouse_id",
            (1,),
        )
        return jsonify(data=rows)

    @app.get("/api/reports/supplier-performance")
    def supplier_performance():
        rows = _database_query(
            """
            SELECT s.supplier_id, s.supplier_code, s.supplier_name,
                   COALESCE(ds.delivery_count, 0) AS delivery_count,
                   COALESCE(ds.delayed_deliveries, 0) AS delayed_deliveries,
                   ds.average_delay_days,
                   COALESCE(qs.inspected_quantity, 0) AS inspected_quantity,
                   COALESCE(qs.rejected_quantity, 0) AS rejected_quantity,
                   qs.rejection_rate_percent
            FROM suppliers AS s
            LEFT JOIN (
                SELECT po.supplier_id,
                       COUNT(*) AS delivery_count,
                       SUM(CASE
                           WHEN sh.estimated_delivery_at IS NOT NULL
                            AND d.received_at > sh.estimated_delivery_at
                           THEN 1 ELSE 0
                       END) AS delayed_deliveries,
                       AVG(CASE
                           WHEN sh.estimated_delivery_at IS NOT NULL
                           THEN GREATEST(
                               TIMESTAMPDIFF(
                                   SECOND, sh.estimated_delivery_at, d.received_at
                               ) / 86400.0,
                               0
                           )
                       END) AS average_delay_days
                FROM deliveries AS d
                JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
                JOIN purchase_orders AS po
                    ON po.purchase_order_id = sh.purchase_order_id
                GROUP BY po.supplier_id
            ) AS ds ON ds.supplier_id = s.supplier_id
            LEFT JOIN (
                SELECT po.supplier_id,
                       SUM(qi.accepted_qty + qi.rejected_qty) AS inspected_quantity,
                       SUM(qi.rejected_qty) AS rejected_quantity,
                       100.0 * SUM(qi.rejected_qty)
                           / NULLIF(SUM(qi.accepted_qty + qi.rejected_qty), 0)
                           AS rejection_rate_percent
                FROM quality_inspections AS qi
                JOIN delivery_items AS di
                    ON di.delivery_item_id = qi.delivery_item_id
                JOIN deliveries AS d ON d.delivery_id = di.delivery_id
                JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
                JOIN purchase_orders AS po
                    ON po.purchase_order_id = sh.purchase_order_id
                GROUP BY po.supplier_id
            ) AS qs ON qs.supplier_id = s.supplier_id
            ORDER BY s.supplier_id
            """
        )
        return jsonify(data=rows)

    @app.get("/api/reports/overdue-purchase-orders")
    def overdue_purchase_orders():
        rows = _database_query(
            """
            SELECT po.purchase_order_id, po.po_number, po.supplier_id,
                   s.supplier_name, po.ordered_at, po.expected_delivery_date,
                   po.status,
                   SUM(poi.quantity_ordered) AS quantity_ordered,
                   SUM(poi.quantity_ordered - COALESCE(received.quantity_received, 0))
                       AS quantity_outstanding
            FROM purchase_orders AS po
            JOIN suppliers AS s ON s.supplier_id = po.supplier_id
            JOIN purchase_order_items AS poi
                ON poi.purchase_order_id = po.purchase_order_id
            LEFT JOIN (
                SELECT di.purchase_order_item_id,
                       SUM(di.quantity_received) AS quantity_received
                FROM delivery_items AS di
                GROUP BY di.purchase_order_item_id
            ) AS received
                ON received.purchase_order_item_id = poi.purchase_order_item_id
            WHERE po.expected_delivery_date < CURRENT_DATE
              AND po.status IN ('submitted', 'partially_received')
              AND poi.quantity_ordered > COALESCE(received.quantity_received, 0)
            GROUP BY po.purchase_order_id, po.po_number, po.supplier_id,
                     s.supplier_name, po.ordered_at, po.expected_delivery_date,
                     po.status
            ORDER BY po.expected_delivery_date, po.purchase_order_id
            """
        )
        return jsonify(data=rows)

    @app.get("/api/purchase-orders")
    def purchase_orders_list():
        rows = _database_query(
            """
            SELECT po.*, s.supplier_code, s.supplier_name,
                   COUNT(poi.purchase_order_item_id) AS line_count
            FROM purchase_orders AS po
            JOIN suppliers AS s ON s.supplier_id = po.supplier_id
            LEFT JOIN purchase_order_items AS poi
                ON poi.purchase_order_id = po.purchase_order_id
            GROUP BY po.purchase_order_id, s.supplier_code, s.supplier_name
            ORDER BY po.purchase_order_id
            """
        )
        return jsonify(data=rows)

    @app.get("/api/purchase-orders/<int:purchase_order_id>")
    def purchase_orders_get(purchase_order_id):
        order = _database_query(
            """
            SELECT po.*, s.supplier_code, s.supplier_name
            FROM purchase_orders AS po
            JOIN suppliers AS s ON s.supplier_id = po.supplier_id
            WHERE po.purchase_order_id = %s
            """,
            (purchase_order_id,),
            fetch_one=True,
        )
        if order is None:
            raise APIError(404, "Purchase order not found.")
        order["items"] = _database_query(
            """
            SELECT poi.purchase_order_item_id, poi.material_id, m.sku,
                   m.material_name, poi.quantity_ordered, poi.unit_cost,
                   COALESCE(SUM(di.quantity_received), 0) AS quantity_received
            FROM purchase_order_items AS poi
            JOIN materials AS m ON m.material_id = poi.material_id
            LEFT JOIN delivery_items AS di
                ON di.purchase_order_item_id = poi.purchase_order_item_id
            WHERE poi.purchase_order_id = %s
            GROUP BY poi.purchase_order_item_id, poi.material_id, m.sku,
                     m.material_name, poi.quantity_ordered, poi.unit_cost
            ORDER BY poi.purchase_order_item_id
            """,
            (purchase_order_id,),
        )
        return jsonify(data=order)

    @app.post("/api/purchase-orders")
    def purchase_orders_create():
        payload = _json_payload()
        allowed = {
            "po_number", "supplier_id", "ordered_at",
            "expected_delivery_date", "status", "items",
        }
        if set(payload) - allowed:
            raise APIError(400, "The request contains unknown purchase order fields.")
        po_number = _string_value(payload.get("po_number"), "po_number", 40)
        supplier_id = _positive_int(
            payload.get("supplier_id"), "supplier_id", maximum=18446744073709551615
        )
        ordered_at = _date_value(payload.get("ordered_at"), "ordered_at")
        expected_date = _date_value(
            payload.get("expected_delivery_date"), "expected_delivery_date", required=False
        )
        if expected_date is not None and expected_date < ordered_at:
            raise APIError(400, "expected_delivery_date cannot precede ordered_at.")
        status = payload.get("status", "draft")
        if status not in ("draft", "submitted"):
            raise APIError(400, "New purchase orders must be draft or submitted.")
        items = _validated_order_items(payload.get("items"))

        def insert_order(_connection, cursor):
            cursor.execute(
                """
                INSERT INTO purchase_orders
                    (po_number, supplier_id, ordered_at, expected_delivery_date, status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (po_number, supplier_id, ordered_at, expected_date, status),
            )
            order_id = cursor.lastrowid
            cursor.executemany(
                """
                INSERT INTO purchase_order_items
                    (purchase_order_id, material_id, quantity_ordered, unit_cost)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (order_id, material_id, quantity, cost)
                    for material_id, quantity, cost in items
                ],
            )
            return {"purchase_order_id": order_id, "po_number": po_number}

        return jsonify(data=_database_transaction(insert_order)), 201

    @app.get("/api/shipments")
    def shipments_list():
        rows = _database_query(
            """
            SELECT sh.*, po.po_number, w.warehouse_code, w.warehouse_name
            FROM shipments AS sh
            JOIN purchase_orders AS po
                ON po.purchase_order_id = sh.purchase_order_id
            JOIN warehouses AS w ON w.warehouse_id = sh.warehouse_id
            ORDER BY sh.shipment_id
            """
        )
        return jsonify(data=rows)

    @app.get("/api/shipments/<int:shipment_id>")
    def shipments_get(shipment_id):
        row = _database_query(
            """
            SELECT sh.*, po.po_number, w.warehouse_code, w.warehouse_name
            FROM shipments AS sh
            JOIN purchase_orders AS po
                ON po.purchase_order_id = sh.purchase_order_id
            JOIN warehouses AS w ON w.warehouse_id = sh.warehouse_id
            WHERE sh.shipment_id = %s
            """,
            (shipment_id,),
            fetch_one=True,
        )
        if row is None:
            raise APIError(404, "Shipment not found.")
        return jsonify(data=row)

    @app.post("/api/shipments")
    def shipments_create():
        payload = _json_payload()
        allowed = {
            "shipment_number", "purchase_order_id", "warehouse_id",
            "tracking_number", "carrier", "shipped_at", "estimated_delivery_at",
        }
        if set(payload) - allowed:
            raise APIError(400, "The request contains unknown shipment fields.")
        shipment_number = _string_value(payload.get("shipment_number"), "shipment_number", 40)
        order_id = _positive_int(
            payload.get("purchase_order_id"), "purchase_order_id",
            maximum=18446744073709551615,
        )
        warehouse_id = _positive_int(
            payload.get("warehouse_id"), "warehouse_id",
            maximum=18446744073709551615,
        )
        tracking_number = _string_value(
            payload.get("tracking_number"), "tracking_number", 100, required=False
        )
        carrier = _string_value(payload.get("carrier"), "carrier", 100, required=False)
        shipped_at = _datetime_value(payload.get("shipped_at"), "shipped_at")
        estimated_at = _datetime_value(
            payload.get("estimated_delivery_at"), "estimated_delivery_at"
        )
        if shipped_at and estimated_at and estimated_at < shipped_at:
            raise APIError(400, "estimated_delivery_at cannot precede shipped_at.")
        def insert_shipment(_connection, cursor):
            cursor.execute(
                "SELECT status FROM purchase_orders "
                "WHERE purchase_order_id = %s FOR UPDATE",
                (order_id,),
            )
            order = cursor.fetchone()
            if order is None:
                raise APIError(404, "Purchase order not found.")
            if order["status"] in ("cancelled", "received"):
                raise APIError(409, "This purchase order cannot receive another shipment.")
            cursor.execute(
                """
                INSERT INTO shipments
                    (shipment_number, purchase_order_id, warehouse_id, tracking_number,
                     carrier, shipped_at, estimated_delivery_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    shipment_number, order_id, warehouse_id, tracking_number,
                    carrier, shipped_at, estimated_at,
                ),
            )
            return {
                "shipment_id": cursor.lastrowid,
                "shipment_number": shipment_number,
            }

        return jsonify(data=_database_transaction(insert_shipment)), 201

    @app.get("/api/deliveries")
    def deliveries_list():
        rows = _database_query(
            """
            SELECT d.*, sh.shipment_number, sh.purchase_order_id,
                   po.po_number, sh.warehouse_id
            FROM deliveries AS d
            JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
            JOIN purchase_orders AS po
                ON po.purchase_order_id = sh.purchase_order_id
            ORDER BY d.delivery_id
            """
        )
        return jsonify(data=rows)

    @app.get("/api/deliveries/<int:delivery_id>")
    def deliveries_get(delivery_id):
        delivery = _database_query(
            """
            SELECT d.*, sh.shipment_number, sh.purchase_order_id,
                   po.po_number, sh.warehouse_id
            FROM deliveries AS d
            JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
            JOIN purchase_orders AS po
                ON po.purchase_order_id = sh.purchase_order_id
            WHERE d.delivery_id = %s
            """,
            (delivery_id,),
            fetch_one=True,
        )
        if delivery is None:
            raise APIError(404, "Delivery not found.")
        delivery["items"] = _database_query(
            """
            SELECT di.delivery_item_id, di.purchase_order_item_id,
                   poi.material_id, m.sku, m.material_name, di.quantity_received,
                   qi.quality_inspection_id, qi.accepted_qty, qi.rejected_qty,
                   qi.inspected_at, qi.notes AS inspection_notes
            FROM delivery_items AS di
            JOIN purchase_order_items AS poi
                ON poi.purchase_order_item_id = di.purchase_order_item_id
            JOIN materials AS m ON m.material_id = poi.material_id
            LEFT JOIN quality_inspections AS qi
                ON qi.delivery_item_id = di.delivery_item_id
            WHERE di.delivery_id = %s
            ORDER BY di.delivery_item_id
            """,
            (delivery_id,),
        )
        return jsonify(data=delivery)

    @app.post("/api/deliveries")
    def deliveries_create():
        payload = _json_payload()
        allowed = {"delivery_number", "shipment_id", "received_at", "notes", "items"}
        if set(payload) - allowed:
            raise APIError(400, "The request contains unknown delivery fields.")
        delivery_number = _string_value(
            payload.get("delivery_number"), "delivery_number", 40
        )
        shipment_id = _positive_int(
            payload.get("shipment_id"), "shipment_id", maximum=18446744073709551615
        )
        received_at = _datetime_value(
            payload.get("received_at"), "received_at", required=True
        )
        notes = _string_value(payload.get("notes"), "notes", 500, required=False)
        raw_items = payload.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise APIError(400, "items must be a non-empty array.")
        items = []
        line_ids = set()
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict) or set(item) != {
                "purchase_order_item_id", "quantity_received"
            }:
                raise APIError(
                    400,
                    f"items[{index}] must contain purchase_order_item_id and quantity_received.",
                )
            line_id = _positive_int(
                item["purchase_order_item_id"],
                f"items[{index}].purchase_order_item_id",
                maximum=18446744073709551615,
            )
            if line_id in line_ids:
                raise APIError(400, "Each purchase order line may appear only once per delivery.")
            line_ids.add(line_id)
            items.append(
                (line_id, _positive_int(item["quantity_received"], f"items[{index}].quantity_received"))
            )

        def insert_delivery(_connection, cursor):
            cursor.execute(
                """
                SELECT sh.purchase_order_id, sh.warehouse_id, po.status
                FROM shipments AS sh
                JOIN purchase_orders AS po
                    ON po.purchase_order_id = sh.purchase_order_id
                WHERE sh.shipment_id = %s
                FOR UPDATE
                """,
                (shipment_id,),
            )
            shipment = cursor.fetchone()
            if shipment is None:
                raise APIError(404, "Shipment not found.")
            if shipment["status"] in ("cancelled", "received"):
                raise APIError(409, "This purchase order cannot receive another delivery.")

            cursor.execute(
                """
                SELECT purchase_order_item_id, quantity_ordered
                FROM purchase_order_items
                WHERE purchase_order_id = %s
                FOR UPDATE
                """,
                (shipment["purchase_order_id"],),
            )
            order_lines = {
                line["purchase_order_item_id"]: line["quantity_ordered"]
                for line in cursor.fetchall()
            }
            if any(line_id not in order_lines for line_id, _quantity in items):
                raise APIError(400, "Every delivery line must belong to its shipment purchase order.")

            cursor.execute(
                """
                SELECT di.purchase_order_item_id, SUM(di.quantity_received) AS received
                FROM delivery_items AS di
                JOIN deliveries AS d ON d.delivery_id = di.delivery_id
                JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
                WHERE sh.purchase_order_id = %s
                GROUP BY di.purchase_order_item_id
                """,
                (shipment["purchase_order_id"],),
            )
            received_totals = {
                row["purchase_order_item_id"]: row["received"]
                for row in cursor.fetchall()
            }
            for line_id, quantity in items:
                if received_totals.get(line_id, 0) + quantity > order_lines[line_id]:
                    raise APIError(409, "Received quantity cannot exceed the ordered quantity.")

            cursor.execute(
                """
                INSERT INTO deliveries (delivery_number, shipment_id, received_at, notes)
                VALUES (%s, %s, %s, %s)
                """,
                (delivery_number, shipment_id, received_at, notes),
            )
            delivery_id = cursor.lastrowid
            cursor.executemany(
                """
                INSERT INTO delivery_items
                    (delivery_id, purchase_order_item_id, quantity_received)
                VALUES (%s, %s, %s)
                """,
                [
                    (delivery_id, line_id, quantity)
                    for line_id, quantity in items
                ],
            )
            return {"delivery_id": delivery_id, "delivery_number": delivery_number}

        return jsonify(data=_database_transaction(insert_delivery)), 201

    @app.get("/api/deliveries/<int:delivery_id>/inspections")
    def inspections_list(delivery_id):
        rows = _database_query(
            """
            SELECT qi.*, di.delivery_id, di.purchase_order_item_id
            FROM quality_inspections AS qi
            JOIN delivery_items AS di
                ON di.delivery_item_id = qi.delivery_item_id
            WHERE di.delivery_id = %s
            ORDER BY qi.quality_inspection_id
            """,
            (delivery_id,),
        )
        return jsonify(data=rows)

    @app.post("/api/deliveries/<int:delivery_id>/inspections")
    def inspections_create(delivery_id):
        payload = _json_payload()
        allowed = {"delivery_item_id", "accepted_qty", "rejected_qty", "inspected_at", "notes"}
        if set(payload) - allowed:
            raise APIError(400, "The request contains unknown inspection fields.")
        item_id = _positive_int(
            payload.get("delivery_item_id"), "delivery_item_id",
            maximum=18446744073709551615,
        )
        accepted = _nonnegative_int(payload.get("accepted_qty"), "accepted_qty")
        rejected = _nonnegative_int(payload.get("rejected_qty"), "rejected_qty")
        if accepted + rejected == 0 or accepted + rejected > 4294967295:
            raise APIError(400, "Accepted and rejected quantities must total a positive quantity.")
        inspected_at = _datetime_value(
            payload.get("inspected_at"), "inspected_at"
        )
        notes = _string_value(payload.get("notes"), "notes", 500, required=False)

        def insert_inspection(_connection, cursor):
            cursor.execute(
                """
                SELECT d.receipt_processed_at
                FROM deliveries AS d
                JOIN delivery_items AS di ON di.delivery_id = d.delivery_id
                WHERE d.delivery_id = %s AND di.delivery_item_id = %s
                FOR UPDATE
                """,
                (delivery_id, item_id),
            )
            delivery = cursor.fetchone()
            if delivery is None:
                raise APIError(404, "Delivery line not found.")
            if delivery["receipt_processed_at"] is not None:
                raise APIError(409, "A processed delivery cannot be inspected.")
            if inspected_at is None:
                cursor.execute(
                    """
                    INSERT INTO quality_inspections
                        (delivery_item_id, accepted_qty, rejected_qty, notes)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (item_id, accepted, rejected, notes),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO quality_inspections
                        (delivery_item_id, inspected_at, accepted_qty, rejected_qty, notes)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (item_id, inspected_at, accepted, rejected, notes),
                )
            return {"quality_inspection_id": cursor.lastrowid, "delivery_item_id": item_id}

        return jsonify(data=_database_transaction(insert_inspection)), 201

    @app.post("/api/deliveries/<int:delivery_id>/process")
    def deliveries_process(delivery_id):
        def process(_connection, cursor):
            cursor.callproc("process_delivery", [delivery_id])
            for result in cursor.stored_results():
                result.fetchall()
            return {"delivery_id": delivery_id, "status": "processed"}

        return jsonify(data=_database_transaction(process))

    def register_entity_routes(name, config):
        table = config["table"]
        key_fields = config["key"]
        fields = config["fields"]
        required = config["required"]
        collection_path = f"/api/{name}"
        item_path = collection_path + (
            "/<int:item_id>"
            if len(key_fields) == 1
            else "/<int:material_id>/<int:warehouse_id>"
        )

        @app.get(collection_path, endpoint=f"{name}_list")
        def list_items():
            rows = _database_query(
                f"SELECT * FROM {table} ORDER BY {', '.join(key_fields)}"
            )
            return jsonify(data=rows)

        @app.post(collection_path, endpoint=f"{name}_create")
        def create_item():
            payload = _validate_payload(_json_payload(), fields, required)
            columns = tuple(payload)
            placeholders = ", ".join(["%s"] * len(columns))
            result = _database_query(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(payload[column] for column in columns),
                write=True,
            )
            created = dict(payload)
            if len(key_fields) == 1:
                created[key_fields[0]] = result["lastrowid"]
            return jsonify(data=created), 201

        @app.get(item_path, endpoint=f"{name}_get")
        def get_item(**path_keys):
            keys = _path_key_values(key_fields, path_keys)
            where = " AND ".join(f"{field} = %s" for field in key_fields)
            row = _database_query(
                f"SELECT * FROM {table} WHERE {where}",
                tuple(keys[field] for field in key_fields),
                fetch_one=True,
            )
            if row is None:
                raise APIError(404, "Resource not found.")
            return jsonify(data=row)

        @app.route(
            item_path,
            methods=["PUT", "PATCH"],
            endpoint=f"{name}_update",
        )
        def update_item(**path_keys):
            keys = _path_key_values(key_fields, path_keys)
            payload = _json_payload()
            update_fields = fields
            update_required = (
                tuple(field for field in update_fields if field not in key_fields)
                if request.method == "PUT"
                else ()
            )
            validated = _validate_payload(payload, update_fields, update_required)
            if any(field in key_fields for field in validated):
                raise APIError(400, "Resource key fields cannot be changed.")
            if not validated:
                raise APIError(400, "Provide at least one field to update.")
            assignments = ", ".join(f"{field} = %s" for field in validated)
            where = " AND ".join(f"{field} = %s" for field in key_fields)
            params = tuple(validated.values()) + tuple(
                keys[field] for field in key_fields
            )
            result = _database_query(
                f"UPDATE {table} SET {assignments} WHERE {where}",
                params,
                write=True,
            )
            if result["rowcount"] == 0:
                existing = _database_query(
                    f"SELECT 1 FROM {table} WHERE {where}",
                    tuple(keys[field] for field in key_fields),
                    fetch_one=True,
                )
                if existing is None:
                    raise APIError(404, "Resource not found.")
            return jsonify(data={**keys, **validated})

        @app.delete(item_path, endpoint=f"{name}_delete")
        def delete_item(**path_keys):
            keys = _path_key_values(key_fields, path_keys)
            where = " AND ".join(f"{field} = %s" for field in key_fields)
            result = _database_query(
                f"DELETE FROM {table} WHERE {where}",
                tuple(keys[field] for field in key_fields),
                write=True,
            )
            if result["rowcount"] == 0:
                raise APIError(404, "Resource not found.")
            return "", 204

    def _path_key_values(key_fields, path_keys):
        if key_fields == ("material_id", "warehouse_id"):
            return {
                "material_id": path_keys["material_id"],
                "warehouse_id": path_keys["warehouse_id"],
            }
        return {key_fields[0]: path_keys["item_id"]}

    for entity_name, entity_config in ENTITY_FIELDS.items():
        register_entity_routes(entity_name, entity_config)

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
