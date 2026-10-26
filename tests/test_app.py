import unittest
from unittest.mock import ANY, MagicMock, patch

import mysql.connector
from app import create_app


class APITestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_homepage_returns_application_status_and_api_links(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "application": "Supply Chain Risk & Inventory Management System",
                "status": "running",
                "links": {
                    "health": "/health",
                    "suppliers": "/api/suppliers",
                    "materials": "/api/materials",
                    "warehouses": "/api/warehouses",
                    "inventory": "/api/inventory",
                    "low_stock": "/api/inventory/low-stock",
                    "supplier_performance": "/api/reports/supplier-performance",
                },
            },
        )

    def test_homepage_serves_dashboard_for_html_clients(self):
        response = self.client.get("/", headers={"Accept": "text/html"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Supply chain", response.data)
        self.assertIn(b"data-reorder-chart", response.data)
        self.assertIn(b"/static/css/app.css", response.data)
        self.assertIn(b"/static/js/app.js", response.data)
        self.assertIn("text/html", response.content_type)

    def test_dashboard_route_serves_dashboard_without_content_negotiation(self):
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Supply chain", response.data)
        self.assertIn(b"data-reorder-chart", response.data)
        self.assertIn("text/html", response.content_type)

    def test_management_pages_render_without_database_access(self):
        for path in (
            "/inventory",
            "/suppliers",
            "/materials",
            "/warehouses",
            "/purchase-orders",
            "/shipments",
            "/deliveries",
            "/inspections",
            "/risk-reports",
        ):
            with self.subTest(path=path):
                response = self.client.get(path, headers={"Accept": "text/html"})
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"data-page=", response.data)

    def test_theme_stylesheet_exposes_requested_palette(self):
        response = self.client.get("/static/css/app.css")

        self.assertEqual(response.status_code, 200)
        for color in (
            b"--color-background: #171813",
            b"--color-panel: #22231C",
            b"--color-cream: #E9E0CA",
            b"--color-accent: #A3B18A",
            b"--color-amber: #D9A441",
            b"--color-danger: #D96C5F",
        ):
            with self.subTest(color=color):
                self.assertIn(color, response.data)
        response.close()

    @patch("app.get_connection")
    def test_health_returns_database_status(self, get_connection):
        connection = MagicMock()
        get_connection.return_value = connection

        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(), {"status": "ok", "database": "connected"}
        )
        connection.cursor.return_value.execute.assert_called_once_with("SELECT 1")
        connection.close.assert_called_once()

    @patch("app.get_connection", side_effect=RuntimeError("missing database config"))
    def test_health_reports_unavailable_database(self, _get_connection):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(), {"status": "error", "database": "unavailable"}
        )

    @patch("app.get_connection")
    def test_create_supplier_rejects_missing_required_fields(self, get_connection):
        response = self.client.post(
            "/api/suppliers",
            json={"supplier_code": "SUP-004"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("supplier_name", response.get_json()["error"]["message"])
        get_connection.assert_not_called()

    @patch("app.get_connection")
    def test_create_material_rejects_negative_reorder_level(self, get_connection):
        response = self.client.post(
            "/api/materials",
            json={
                "sku": "NEW-001",
                "material_name": "New material",
                "unit_of_measure": "unit",
                "reorder_level": -1,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reorder_level", response.get_json()["error"]["message"])
        get_connection.assert_not_called()

    def test_inventory_requires_json_content_type(self):
        response = self.client.post(
            "/api/inventory",
            data="{}",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("application/json", response.get_json()["error"]["message"])

    @patch("app.get_connection")
    def test_purchase_order_requires_at_least_one_line(self, get_connection):
        response = self.client.post(
            "/api/purchase-orders",
            json={
                "po_number": "PO-TEST-1",
                "supplier_id": 1,
                "ordered_at": "2026-10-01",
                "items": [],
            },
        )

        self.assertEqual(response.status_code, 400)
        get_connection.assert_not_called()

    @patch("app.get_connection")
    def test_purchase_order_creation_inserts_header_and_all_lines(self, get_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.lastrowid = 42
        get_connection.return_value = connection

        response = self.client.post(
            "/api/purchase-orders",
            json={
                "po_number": "PO-TEST-2",
                "supplier_id": 3,
                "ordered_at": "2026-10-01",
                "expected_delivery_date": "2026-10-20",
                "status": "submitted",
                "items": [
                    {"material_id": 1, "quantity_ordered": 12, "unit_cost": "4.25"},
                    {"material_id": 2, "quantity_ordered": 6, "unit_cost": "2.00"},
                ],
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json()["data"],
            {"purchase_order_id": 42, "po_number": "PO-TEST-2"},
        )
        cursor.executemany.assert_called_once()
        self.assertEqual(
            cursor.executemany.call_args.args[1],
            [(42, 1, 12, 4.25), (42, 2, 6, 2.0)],
        )
        connection.commit.assert_called_once()

    @patch("app.get_connection")
    def test_shipment_creation_checks_and_links_purchase_order(self, get_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = {"status": "submitted"}
        cursor.lastrowid = 33
        get_connection.return_value = connection

        response = self.client.post(
            "/api/shipments",
            json={
                "shipment_number": "SHP-TEST-1",
                "purchase_order_id": 7,
                "warehouse_id": 2,
                "tracking_number": "TRACK-TEST-1",
                "carrier": "Local freight",
                "shipped_at": "2026-10-02T10:00:00",
                "estimated_delivery_at": "2026-10-04T10:00:00",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["data"]["shipment_id"], 33)
        self.assertIn("INSERT INTO shipments", cursor.execute.call_args.args[0])
        connection.commit.assert_called_once()

    @patch("app.get_connection")
    def test_delivery_creation_records_partial_receipt_transactionally(self, get_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = {
            "purchase_order_id": 7,
            "warehouse_id": 2,
            "status": "submitted",
        }
        cursor.fetchall.side_effect = [
            [
                {"purchase_order_item_id": 11, "quantity_ordered": 10},
                {"purchase_order_item_id": 12, "quantity_ordered": 8},
            ],
            [],
        ]
        cursor.lastrowid = 54
        get_connection.return_value = connection

        response = self.client.post(
            "/api/deliveries",
            json={
                "delivery_number": "DEL-TEST-2",
                "shipment_id": 5,
                "received_at": "2026-10-03T09:30:00",
                "items": [
                    {"purchase_order_item_id": 11, "quantity_received": 4},
                    {"purchase_order_item_id": 12, "quantity_received": 3},
                ],
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json()["data"],
            {"delivery_id": 54, "delivery_number": "DEL-TEST-2"},
        )
        cursor.executemany.assert_called_once_with(
            ANY,
            [(54, 11, 4), (54, 12, 3)],
        )
        connection.commit.assert_called_once()

    @patch("app.get_connection")
    def test_delivery_rejects_over_receiving_before_inserting(self, get_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = {
            "purchase_order_id": 7,
            "warehouse_id": 2,
            "status": "partially_received",
        }
        cursor.fetchall.side_effect = [
            [{"purchase_order_item_id": 11, "quantity_ordered": 5}],
            [{"purchase_order_item_id": 11, "received": 2}],
        ]
        get_connection.return_value = connection

        response = self.client.post(
            "/api/deliveries",
            json={
                "delivery_number": "DEL-TEST-1",
                "shipment_id": 5,
                "received_at": "2026-10-10T12:30:00",
                "items": [
                    {"purchase_order_item_id": 11, "quantity_received": 4}
                ],
            },
        )

        self.assertEqual(response.status_code, 409)
        cursor.executemany.assert_not_called()
        connection.rollback.assert_called_once()

    @patch("app.get_connection")
    def test_inspection_records_accepted_and_rejected_quantities(self, get_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = {"receipt_processed_at": None}
        cursor.lastrowid = 19
        get_connection.return_value = connection

        response = self.client.post(
            "/api/deliveries/8/inspections",
            json={
                "delivery_item_id": 21,
                "accepted_qty": 8,
                "rejected_qty": 2,
                "notes": "Two units rejected",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json()["data"],
            {"quality_inspection_id": 19, "delivery_item_id": 21},
        )
        self.assertIn("INSERT INTO quality_inspections", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], (21, 8, 2, "Two units rejected"))
        connection.commit.assert_called_once()

    @patch("app.get_connection")
    def test_delivery_processing_uses_database_procedure(self, get_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.stored_results.return_value = []
        get_connection.return_value = connection

        response = self.client.post("/api/deliveries/14/process")

        self.assertEqual(response.status_code, 200)
        cursor.callproc.assert_called_once_with("process_delivery", [14])
        connection.commit.assert_called_once()

    @patch("app.get_connection")
    def test_already_processed_delivery_returns_conflict(self, get_connection):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.callproc.side_effect = mysql.connector.DatabaseError(
            "Delivery has already been processed", errno=1644, sqlstate="45000"
        )
        get_connection.return_value = connection

        response = self.client.post("/api/deliveries/14/process")

        self.assertEqual(response.status_code, 409)
        connection.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
