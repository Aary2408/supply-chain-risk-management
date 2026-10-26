# Supply Chain Risk & Inventory Management System

A college DBMS course project for tracking suppliers, materials, inventory, purchase orders, deliveries, quality inspections, and supply risks.

## Project structure

```text
.
├── app.py                    # Flask API and application factory
├── database.py               # Environment-based MySQL connection
├── database/
│   ├── schema.sql            # Tables, constraints, indexes, views, triggers, procedure
│   └── seed_data.sql         # Demonstration records
├── templates/                # Dashboard and management page templates
├── static/
│   ├── css/app.css           # Vintage terminal theme and responsive layouts
│   └── js/app.js             # API-connected dashboard and page interactions
├── tests/                    # Database and Flask tests
├── .env.example              # Safe placeholders only; no real credentials
├── .gitignore
├── requirements.txt
└── README.md
```

The project includes a MySQL schema and seed data, a Flask JSON API, a responsive browser-based operations console, and automated API and homepage tests.

## Implementation plan

1. **Database foundation (this milestone):** Create normalized MySQL tables with primary/foreign keys, unique and check constraints, useful indexes, reporting views, validation triggers, and an atomic delivery-receiving procedure. Add realistic sample records.
2. **Flask foundation (Phase 2):** Provide environment-based database access, validation, CRUD APIs for suppliers, materials, warehouses, and inventory, plus health and reporting endpoints.
3. **Core management screens:** Implement suppliers, materials, warehouses, purchase orders, and multi-item order entry with server-side validation.
4. **Inventory and receiving:** Add inventory/reorder screens and shipment/delivery workflows. Process a receipt in a database transaction; only inspected accepted quantities increase available stock, and a delivery cannot be processed twice.
5. **Risk, dashboard, and reports:** Use the reporting views and SQL queries for supplier delay/quality analysis, inventory alerts, dashboard summaries, and reports.
6. **Verification and handoff:** Add focused tests for constraints, parameterized queries, receipt rollback/idempotency, inventory changes, and report results; document application setup and screenshots/use cases.

## Database setup (MySQL 8.0.16+)

The schema uses MySQL `CHECK` constraints, which are enforced starting with MySQL 8.0.16. The scripts create and select the `supply_chain_risk_management` database.

### GitHub Codespaces with Docker Compose

Docker and Docker Compose must be available in the Codespace. Copy the example environment file and replace both placeholder passwords with unique local values:

```bash
cp .env.example .env
```

Start MySQL 8 and wait for its health check:

```bash
docker compose up -d --wait mysql
```

Import the schema first, then the demonstration data. The seed script is intended to be imported once into a fresh schema:

```bash
docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' < database/schema.sql
docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' < database/seed_data.sql
```

Verify the tables, foreign keys, low-stock view, and supplier-performance view:

```bash
docker compose exec mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -D supply_chain_risk_management -e "
SHOW TABLES;
SELECT COUNT(*) AS foreign_key_count
 FROM information_schema.table_constraints
 WHERE constraint_schema = DATABASE() AND constraint_type = '\''FOREIGN KEY'\'';
SELECT * FROM v_inventory_reorder_status WHERE reorder_required = 1;
SELECT * FROM v_supplier_performance
 WHERE delayed_deliveries > 0 OR rejected_quantity > 0;
"'
```

The database is also available from the Codespace at `127.0.0.1:3306`. The schema script creates and selects `supply_chain_risk_management`; the SQL files do not need to be edited.

## Phase 2: Flask API

The API connects to the existing `supply_chain_risk_management` database. It does not create or alter database tables or views. Install Python 3.10 or newer and the project dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For Docker Compose in Codespaces, make sure MySQL is running, then load the local environment variables and start Flask:

```bash
docker compose up -d --wait mysql
set -a
source .env
set +a
flask --app app run --debug --host=0.0.0.0 --port=5000
```

Open `http://127.0.0.1:5000/dashboard` (or the forwarded port in Codespaces) for the dashboard. The `/dashboard` route always serves the browser UI; the root route also serves it to HTML clients and continues to return its JSON status document to clients that request JSON or do not explicitly prefer HTML. The console provides inventory, suppliers, materials, warehouses, purchase orders, shipments, deliveries, quality inspections, and risk-report pages. It reads and writes through the existing `/api/...` endpoints; dashboard totals, reorder charts, and reports are derived from API responses, not seeded in the browser.

The connection module reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`. If `DB_USER` or `DB_PASSWORD` is unset, the corresponding `MYSQL_USER` or `MYSQL_PASSWORD` from the Compose `.env` file is used. Database name defaults to `supply_chain_risk_management`; host and port default to `127.0.0.1` and `3306`. Do not commit `.env` or put real credentials in source code.

Run the automated tests without requiring a live database connection:

```bash
python -m unittest discover -s tests -v
```

Available routes:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Check MySQL connectivity |
| GET, POST | `/api/suppliers` | List or create suppliers |
| GET, PUT, PATCH, DELETE | `/api/suppliers/<supplier_id>` | Retrieve, update, or delete a supplier |
| GET, POST | `/api/materials` | List or create materials |
| GET, PUT, PATCH, DELETE | `/api/materials/<material_id>` | Retrieve, update, or delete a material |
| GET, POST | `/api/warehouses` | List or create warehouses |
| GET, PUT, PATCH, DELETE | `/api/warehouses/<warehouse_id>` | Retrieve, update, or delete a warehouse |
| GET, POST | `/api/inventory` | List or create inventory records |
| GET, PUT, PATCH, DELETE | `/api/inventory/<material_id>/<warehouse_id>` | Retrieve, update, or delete an inventory record |
| GET, POST | `/api/purchase-orders` | List or create orders with material line items |
| GET | `/api/purchase-orders/<purchase_order_id>` | Retrieve an order and received line quantities |
| GET, POST | `/api/shipments` | List or create shipments linked to purchase orders |
| GET | `/api/shipments/<shipment_id>` | Retrieve shipment tracking details |
| GET, POST | `/api/deliveries` | List or record partial/complete deliveries |
| GET | `/api/deliveries/<delivery_id>` | Retrieve a delivery and its inspection results |
| GET, POST | `/api/deliveries/<delivery_id>/inspections` | List or record quality inspections |
| POST | `/api/deliveries/<delivery_id>/process` | Process inspected receipt quantities into inventory |
| GET | `/api/inventory/low-stock` | Query `v_inventory_reorder_status` |
| GET | `/api/reports/supplier-performance` | Query supplier delivery and quality metrics |
| GET | `/api/reports/overdue-purchase-orders` | List overdue orders with outstanding quantities |

Send create and update bodies as JSON. Purchase order creation includes a non-empty `items` array of `{material_id, quantity_ordered, unit_cost}` entries. Delivery creation includes a non-empty `items` array of `{purchase_order_item_id, quantity_received}` entries. Each inspection must identify its `delivery_item_id`; accepted plus rejected quantities must exactly match that delivery line. Process each delivery only after every line has been inspected. Processing invokes the schema's `process_delivery` procedure, which atomically increases stock only by accepted quantities, records receipt inventory transactions, updates order status, and prevents duplicate processing. Receipt recording is serialized by purchase order and rejects quantities exceeding ordered totals.

Inventory records use `material_id` and `warehouse_id` as their composite key; updates cannot change those keys. The API uses HTTP 400 for invalid input, 404 for missing resources, 409 for database constraint conflicts or invalid workflow state, and 503 when the database is unavailable or an operation fails. The supplier report counts all deliveries, computes delay only when an estimated delivery time is available, and calculates rejection metrics from inspections. The overdue report includes submitted or partially received orders past their expected date that still have outstanding quantities.

Stop the service without removing its data, then restart it later:

```bash
docker compose stop mysql
docker compose up -d --wait mysql
```

The second command starts the service again and waits until MySQL is healthy. The named `mysql_data` volume preserves the database across stops and container recreation. `docker compose down` also retains the volume; do not use `docker compose down -v` if you want to keep the data.

### Native MySQL installation

Alternatively, with a local MySQL 8.0.16+ server, create the schema and import the seed data:

```bash
mysql -u root -p < database/schema.sql
mysql -u root -p < database/seed_data.sql
```

To inspect the tables, views, and example inventory:

```sql
USE supply_chain_risk_management;
SHOW TABLES;
SELECT * FROM v_inventory_reorder_status WHERE reorder_required = 1;
SELECT * FROM v_supplier_performance;
```

The receiving procedure is `process_delivery(delivery_id)`. The Flask API invokes it after every delivery line has a quality inspection whose accepted and rejected quantities equal the received quantity. It atomically adds accepted quantities to inventory, records inventory transactions, updates the purchase-order status, and marks the delivery processed. A second call for that delivery raises an error instead of applying stock twice.

The SQL is intentionally organized and named for readability during DBMS evaluation. The Flask API uses parameterized SQL and transactions for the order, shipment, delivery, and inspection workflows.
