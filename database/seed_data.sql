USE supply_chain_risk_management;

INSERT INTO suppliers (
    supplier_id, supplier_code, supplier_name, contact_name, email, phone,
    address, lead_time_days
) VALUES
    (1, 'SUP-001', 'Northstar Components', 'Maya Patel',
     'maya@northstar.example', '+1-555-0101',
     '1200 Industrial Way, Portland, OR', 7),
    (2, 'SUP-002', 'Evergreen Packaging', 'Luis Romero',
     'luis@evergreen.example', '+1-555-0102',
     '48 Mill Road, Eugene, OR', 10),
    (3, 'SUP-003', 'Cascade Fasteners', 'Ava Chen',
     'ava@cascade.example', '+1-555-0103',
     '900 Foundry Avenue, Salem, OR', 5);

INSERT INTO materials (
    material_id, sku, material_name, category, unit_of_measure,
    reorder_level, safety_stock
) VALUES
    (1, 'PCB-100', 'Control board assembly', 'Electronics', 'unit', 50, 25),
    (2, 'PKG-220', 'Reusable shipping carton', 'Packaging', 'unit', 40, 20),
    (3, 'FST-310', 'Stainless steel bolt M8', 'Fasteners', 'unit', 100, 50),
    (4, 'CAB-415', 'Shielded power cable, 2 m', 'Electronics', 'unit', 30, 15);

INSERT INTO warehouses (warehouse_id, warehouse_code, warehouse_name, location)
VALUES
    (1, 'WH-PORT', 'Portland Main Warehouse', 'Portland, OR'),
    (2, 'WH-EUG', 'Eugene Distribution Center', 'Eugene, OR');

INSERT INTO inventory (material_id, warehouse_id, quantity_on_hand)
VALUES
    (1, 1, 80),
    (2, 1, 30),
    (3, 1, 240),
    (4, 2, 12);

INSERT INTO inventory_transactions (
    material_id, warehouse_id, transaction_type, quantity_delta, occurred_at, notes
) VALUES
    (1, 1, 'adjustment', 80, '2026-09-01 08:00:00', 'Opening balance'),
    (2, 1, 'adjustment', 30, '2026-09-01 08:00:00', 'Opening balance'),
    (3, 1, 'adjustment', 240, '2026-09-01 08:00:00', 'Opening balance'),
    (4, 2, 'adjustment', 12, '2026-09-01 08:00:00', 'Opening balance');

INSERT INTO purchase_orders (
    purchase_order_id, po_number, supplier_id, ordered_at,
    expected_delivery_date, status
) VALUES
    (1, 'PO-2026-1001', 1, '2026-09-01', '2026-09-10', 'submitted'),
    (2, 'PO-2026-1002', 2, '2026-09-05', '2026-09-25', 'submitted');

INSERT INTO purchase_order_items (
    purchase_order_item_id, purchase_order_id, material_id, quantity_ordered, unit_cost
) VALUES
    (1, 1, 1, 100, 42.50),
    (2, 1, 2, 50, 6.25),
    (3, 2, 3, 300, 0.18);

INSERT INTO shipments (
    shipment_id, shipment_number, purchase_order_id, warehouse_id,
    tracking_number, carrier, shipped_at, estimated_delivery_at
) VALUES
    (1, 'SHP-2026-501', 1, 1, 'NSC-TRACK-501', 'Regional Freight',
     '2026-09-02 09:00:00', '2026-09-10 17:00:00'),
    (2, 'SHP-2026-502', 2, 1, 'EVG-TRACK-502', 'Evergreen Logistics',
     '2026-09-08 11:30:00', '2026-09-25 17:00:00');

INSERT INTO deliveries (delivery_id, delivery_number, shipment_id, received_at, notes)
VALUES
    (1, 'DEL-2026-701', 1, '2026-09-12 14:20:00',
     'Partial delivery; cartons and boards inspected at receiving dock');

INSERT INTO delivery_items (
    delivery_item_id, delivery_id, purchase_order_item_id, quantity_received
) VALUES
    (1, 1, 1, 40),
    (2, 1, 2, 20);

INSERT INTO quality_inspections (
    quality_inspection_id, delivery_item_id, inspected_at,
    accepted_qty, rejected_qty, notes
) VALUES
    (1, 1, '2026-09-12 15:00:00', 38, 2, 'Two boards failed functional test'),
    (2, 2, '2026-09-12 15:20:00', 18, 2, 'Two cartons had damaged corners');

INSERT INTO risks (risk_id, supplier_id, risk_type, risk_score, assessed_at, description)
VALUES
    (1, 1, 'delay', 68.00, '2026-09-13 09:00:00',
     'Recent shipment arrived two days after the estimated delivery date'),
    (2, 1, 'quality', 24.00, '2026-09-13 09:00:00',
     'A small number of boards were rejected during inspection'),
    (3, 2, 'supply_disruption', 32.00, '2026-09-13 09:00:00',
     'Monitor upcoming packaging shipment for seasonal capacity constraints');

CALL process_delivery(1);
