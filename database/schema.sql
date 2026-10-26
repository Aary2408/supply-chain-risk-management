CREATE DATABASE IF NOT EXISTS supply_chain_risk_management
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE supply_chain_risk_management;

CREATE TABLE suppliers (
    supplier_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    supplier_code VARCHAR(30) NOT NULL,
    supplier_name VARCHAR(150) NOT NULL,
    contact_name VARCHAR(120),
    email VARCHAR(254),
    phone VARCHAR(30),
    address VARCHAR(500),
    lead_time_days INT UNSIGNED NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (supplier_id),
    UNIQUE KEY uq_suppliers_code (supplier_code),
    UNIQUE KEY uq_suppliers_email (email)
) ENGINE=InnoDB;

CREATE TABLE materials (
    material_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(50) NOT NULL,
    material_name VARCHAR(150) NOT NULL,
    category VARCHAR(100),
    unit_of_measure VARCHAR(30) NOT NULL,
    reorder_level INT UNSIGNED NOT NULL DEFAULT 0,
    safety_stock INT UNSIGNED NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (material_id),
    UNIQUE KEY uq_materials_sku (sku)
) ENGINE=InnoDB;

CREATE TABLE warehouses (
    warehouse_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    warehouse_code VARCHAR(30) NOT NULL,
    warehouse_name VARCHAR(150) NOT NULL,
    location VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (warehouse_id),
    UNIQUE KEY uq_warehouses_code (warehouse_code)
) ENGINE=InnoDB;

CREATE TABLE inventory (
    material_id BIGINT UNSIGNED NOT NULL,
    warehouse_id BIGINT UNSIGNED NOT NULL,
    quantity_on_hand INT UNSIGNED NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (material_id, warehouse_id),
    CONSTRAINT fk_inventory_material
        FOREIGN KEY (material_id) REFERENCES materials (material_id),
    CONSTRAINT fk_inventory_warehouse
        FOREIGN KEY (warehouse_id) REFERENCES warehouses (warehouse_id)
) ENGINE=InnoDB;

CREATE TABLE purchase_orders (
    purchase_order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    po_number VARCHAR(40) NOT NULL,
    supplier_id BIGINT UNSIGNED NOT NULL,
    ordered_at DATE NOT NULL,
    expected_delivery_date DATE,
    status ENUM('draft', 'submitted', 'partially_received', 'received', 'cancelled')
        NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (purchase_order_id),
    UNIQUE KEY uq_purchase_orders_number (po_number),
    KEY idx_purchase_orders_supplier_status (supplier_id, status),
    CONSTRAINT fk_purchase_orders_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id),
    CONSTRAINT chk_purchase_orders_expected_date
        CHECK (expected_delivery_date IS NULL OR expected_delivery_date >= ordered_at)
) ENGINE=InnoDB;

CREATE TABLE purchase_order_items (
    purchase_order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    purchase_order_id BIGINT UNSIGNED NOT NULL,
    material_id BIGINT UNSIGNED NOT NULL,
    quantity_ordered INT UNSIGNED NOT NULL,
    unit_cost DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (purchase_order_item_id),
    UNIQUE KEY uq_po_items_order_material (purchase_order_id, material_id),
    KEY idx_po_items_material (material_id),
    CONSTRAINT fk_po_items_order
        FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders (purchase_order_id),
    CONSTRAINT fk_po_items_material
        FOREIGN KEY (material_id) REFERENCES materials (material_id),
    CONSTRAINT chk_po_items_quantity CHECK (quantity_ordered > 0),
    CONSTRAINT chk_po_items_unit_cost CHECK (unit_cost >= 0)
) ENGINE=InnoDB;

CREATE TABLE shipments (
    shipment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    shipment_number VARCHAR(40) NOT NULL,
    purchase_order_id BIGINT UNSIGNED NOT NULL,
    warehouse_id BIGINT UNSIGNED NOT NULL,
    tracking_number VARCHAR(100),
    carrier VARCHAR(100),
    shipped_at DATETIME,
    estimated_delivery_at DATETIME,
    PRIMARY KEY (shipment_id),
    UNIQUE KEY uq_shipments_number (shipment_number),
    UNIQUE KEY uq_shipments_tracking (tracking_number),
    KEY idx_shipments_order (purchase_order_id),
    CONSTRAINT fk_shipments_order
        FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders (purchase_order_id),
    CONSTRAINT fk_shipments_warehouse
        FOREIGN KEY (warehouse_id) REFERENCES warehouses (warehouse_id),
    CONSTRAINT chk_shipments_dates
        CHECK (estimated_delivery_at IS NULL OR shipped_at IS NULL
            OR estimated_delivery_at >= shipped_at)
) ENGINE=InnoDB;

CREATE TABLE deliveries (
    delivery_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    delivery_number VARCHAR(40) NOT NULL,
    shipment_id BIGINT UNSIGNED NOT NULL,
    received_at DATETIME NOT NULL,
    receipt_processed_at DATETIME,
    notes VARCHAR(500),
    PRIMARY KEY (delivery_id),
    UNIQUE KEY uq_deliveries_number (delivery_number),
    KEY idx_deliveries_shipment_received (shipment_id, received_at),
    CONSTRAINT fk_deliveries_shipment
        FOREIGN KEY (shipment_id) REFERENCES shipments (shipment_id)
) ENGINE=InnoDB;

CREATE TABLE delivery_items (
    delivery_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    delivery_id BIGINT UNSIGNED NOT NULL,
    purchase_order_item_id BIGINT UNSIGNED NOT NULL,
    quantity_received INT UNSIGNED NOT NULL,
    PRIMARY KEY (delivery_item_id),
    UNIQUE KEY uq_delivery_items_line (delivery_id, purchase_order_item_id),
    KEY idx_delivery_items_po_item (purchase_order_item_id),
    CONSTRAINT fk_delivery_items_delivery
        FOREIGN KEY (delivery_id) REFERENCES deliveries (delivery_id),
    CONSTRAINT fk_delivery_items_po_item
        FOREIGN KEY (purchase_order_item_id)
        REFERENCES purchase_order_items (purchase_order_item_id),
    CONSTRAINT chk_delivery_items_quantity CHECK (quantity_received > 0)
) ENGINE=InnoDB;

CREATE TABLE quality_inspections (
    quality_inspection_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    delivery_item_id BIGINT UNSIGNED NOT NULL,
    inspected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accepted_qty INT UNSIGNED NOT NULL,
    rejected_qty INT UNSIGNED NOT NULL,
    notes VARCHAR(500),
    PRIMARY KEY (quality_inspection_id),
    UNIQUE KEY uq_quality_inspections_delivery_item (delivery_item_id),
    CONSTRAINT fk_quality_inspections_delivery_item
        FOREIGN KEY (delivery_item_id) REFERENCES delivery_items (delivery_item_id),
    CONSTRAINT chk_quality_inspections_quantities
        CHECK (accepted_qty + rejected_qty > 0)
) ENGINE=InnoDB;

CREATE TABLE inventory_transactions (
    inventory_transaction_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    material_id BIGINT UNSIGNED NOT NULL,
    warehouse_id BIGINT UNSIGNED NOT NULL,
    delivery_id BIGINT UNSIGNED,
    transaction_type ENUM('receipt', 'issue', 'adjustment') NOT NULL,
    quantity_delta INT NOT NULL,
    occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes VARCHAR(500),
    PRIMARY KEY (inventory_transaction_id),
    UNIQUE KEY uq_inventory_tx_delivery_material_type
        (delivery_id, material_id, transaction_type),
    KEY idx_inventory_tx_material_time (material_id, occurred_at),
    KEY idx_inventory_tx_warehouse_time (warehouse_id, occurred_at),
    CONSTRAINT fk_inventory_tx_material
        FOREIGN KEY (material_id) REFERENCES materials (material_id),
    CONSTRAINT fk_inventory_tx_warehouse
        FOREIGN KEY (warehouse_id) REFERENCES warehouses (warehouse_id),
    CONSTRAINT fk_inventory_tx_delivery
        FOREIGN KEY (delivery_id) REFERENCES deliveries (delivery_id),
    CONSTRAINT chk_inventory_tx_delta CHECK (quantity_delta <> 0),
    CONSTRAINT chk_inventory_tx_direction CHECK (
        (transaction_type = 'receipt' AND quantity_delta > 0)
        OR (transaction_type = 'issue' AND quantity_delta < 0)
        OR transaction_type = 'adjustment'
    )
) ENGINE=InnoDB;

CREATE TABLE risks (
    risk_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    supplier_id BIGINT UNSIGNED NOT NULL,
    risk_type ENUM('delay', 'quality', 'supply_disruption', 'other') NOT NULL,
    risk_score DECIMAL(5, 2) NOT NULL,
    assessed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(1000) NOT NULL,
    status ENUM('open', 'mitigated', 'closed') NOT NULL DEFAULT 'open',
    PRIMARY KEY (risk_id),
    KEY idx_risks_supplier_assessed (supplier_id, assessed_at),
    KEY idx_risks_status_score (status, risk_score),
    CONSTRAINT fk_risks_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id),
    CONSTRAINT chk_risks_score CHECK (risk_score BETWEEN 0 AND 100)
) ENGINE=InnoDB;

CREATE OR REPLACE VIEW v_inventory_reorder_status AS
SELECT
    m.material_id,
    m.sku,
    m.material_name,
    w.warehouse_id,
    w.warehouse_code,
    w.warehouse_name,
    COALESCE(i.quantity_on_hand, 0) AS quantity_on_hand,
    m.reorder_level,
    m.safety_stock,
    (COALESCE(i.quantity_on_hand, 0) <= m.reorder_level) AS reorder_required
FROM materials AS m
CROSS JOIN warehouses AS w
LEFT JOIN inventory AS i
    ON i.material_id = m.material_id
   AND i.warehouse_id = w.warehouse_id
WHERE m.is_active = TRUE
  AND w.is_active = TRUE;

CREATE OR REPLACE VIEW v_supplier_performance AS
SELECT
    s.supplier_id,
    s.supplier_code,
    s.supplier_name,
    COALESCE(delivery_stats.delivery_count, 0) AS delivery_count,
    COALESCE(delivery_stats.delayed_deliveries, 0) AS delayed_deliveries,
    delivery_stats.average_delay_days,
    COALESCE(quality_stats.inspected_quantity, 0) AS inspected_quantity,
    COALESCE(quality_stats.rejected_quantity, 0) AS rejected_quantity,
    quality_stats.rejection_rate_percent
FROM suppliers AS s
LEFT JOIN (
    SELECT
        po.supplier_id,
        COUNT(*) AS delivery_count,
        SUM(d.received_at > sh.estimated_delivery_at) AS delayed_deliveries,
        AVG(GREATEST(DATEDIFF(d.received_at, sh.estimated_delivery_at), 0))
            AS average_delay_days
    FROM deliveries AS d
    JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
    JOIN purchase_orders AS po ON po.purchase_order_id = sh.purchase_order_id
    WHERE sh.estimated_delivery_at IS NOT NULL
    GROUP BY po.supplier_id
) AS delivery_stats ON delivery_stats.supplier_id = s.supplier_id
LEFT JOIN (
    SELECT
        po.supplier_id,
        SUM(qi.accepted_qty + qi.rejected_qty) AS inspected_quantity,
        SUM(qi.rejected_qty) AS rejected_quantity,
        100.0 * SUM(qi.rejected_qty)
            / NULLIF(SUM(qi.accepted_qty + qi.rejected_qty), 0)
            AS rejection_rate_percent
    FROM quality_inspections AS qi
    JOIN delivery_items AS di ON di.delivery_item_id = qi.delivery_item_id
    JOIN deliveries AS d ON d.delivery_id = di.delivery_id
    JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
    JOIN purchase_orders AS po ON po.purchase_order_id = sh.purchase_order_id
    GROUP BY po.supplier_id
) AS quality_stats ON quality_stats.supplier_id = s.supplier_id;

DELIMITER $$

CREATE TRIGGER trg_delivery_items_before_insert
BEFORE INSERT ON delivery_items
FOR EACH ROW
BEGIN
    DECLARE v_ordered_qty INT UNSIGNED;
    DECLARE v_item_po_id BIGINT UNSIGNED;
    DECLARE v_shipment_po_id BIGINT UNSIGNED;
    DECLARE v_already_received BIGINT UNSIGNED;
    DECLARE v_processed_at DATETIME;

    SELECT poi.quantity_ordered, poi.purchase_order_id, sh.purchase_order_id,
           d.receipt_processed_at
      INTO v_ordered_qty, v_item_po_id, v_shipment_po_id, v_processed_at
    FROM purchase_order_items AS poi
    JOIN deliveries AS d ON d.delivery_id = NEW.delivery_id
    JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
    WHERE poi.purchase_order_item_id = NEW.purchase_order_item_id;

    IF v_processed_at IS NOT NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot add lines to a processed delivery';
    END IF;

    IF v_item_po_id <> v_shipment_po_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Delivery line must belong to its shipment purchase order';
    END IF;

    SELECT COALESCE(SUM(quantity_received), 0)
      INTO v_already_received
    FROM delivery_items
    WHERE purchase_order_item_id = NEW.purchase_order_item_id;

    IF v_already_received + NEW.quantity_received > v_ordered_qty THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Received quantity cannot exceed the ordered quantity';
    END IF;
END$$

CREATE TRIGGER trg_delivery_items_before_update
BEFORE UPDATE ON delivery_items
FOR EACH ROW
BEGIN
    DECLARE v_ordered_qty INT UNSIGNED;
    DECLARE v_item_po_id BIGINT UNSIGNED;
    DECLARE v_shipment_po_id BIGINT UNSIGNED;
    DECLARE v_already_received BIGINT UNSIGNED;
    DECLARE v_processed_at DATETIME;

    SELECT poi.quantity_ordered, poi.purchase_order_id, sh.purchase_order_id,
           d.receipt_processed_at
      INTO v_ordered_qty, v_item_po_id, v_shipment_po_id, v_processed_at
    FROM purchase_order_items AS poi
    JOIN deliveries AS d ON d.delivery_id = NEW.delivery_id
    JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
    WHERE poi.purchase_order_item_id = NEW.purchase_order_item_id;

    IF v_processed_at IS NOT NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot change lines in a processed delivery';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM quality_inspections
        WHERE delivery_item_id = OLD.delivery_item_id
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Remove the quality inspection before changing its delivery line';
    END IF;

    IF v_item_po_id <> v_shipment_po_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Delivery line must belong to its shipment purchase order';
    END IF;

    SELECT COALESCE(SUM(quantity_received), 0)
      INTO v_already_received
    FROM delivery_items
    WHERE purchase_order_item_id = NEW.purchase_order_item_id
      AND delivery_item_id <> OLD.delivery_item_id;

    IF v_already_received + NEW.quantity_received > v_ordered_qty THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Received quantity cannot exceed the ordered quantity';
    END IF;
END$$

CREATE TRIGGER trg_quality_inspections_before_insert
BEFORE INSERT ON quality_inspections
FOR EACH ROW
BEGIN
    DECLARE v_received_qty INT UNSIGNED;
    DECLARE v_processed_at DATETIME;

    SELECT di.quantity_received, d.receipt_processed_at
      INTO v_received_qty, v_processed_at
    FROM delivery_items AS di
    JOIN deliveries AS d ON d.delivery_id = di.delivery_id
    WHERE di.delivery_item_id = NEW.delivery_item_id;

    IF v_processed_at IS NOT NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot inspect a processed delivery';
    END IF;

    IF NEW.accepted_qty + NEW.rejected_qty <> v_received_qty THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Accepted and rejected quantities must equal quantity received';
    END IF;
END$$

CREATE TRIGGER trg_quality_inspections_before_update
BEFORE UPDATE ON quality_inspections
FOR EACH ROW
BEGIN
    DECLARE v_received_qty INT UNSIGNED;
    DECLARE v_processed_at DATETIME;

    SELECT di.quantity_received, d.receipt_processed_at
      INTO v_received_qty, v_processed_at
    FROM delivery_items AS di
    JOIN deliveries AS d ON d.delivery_id = di.delivery_id
    WHERE di.delivery_item_id = NEW.delivery_item_id;

    IF v_processed_at IS NOT NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot change an inspection for a processed delivery';
    END IF;

    IF NEW.accepted_qty + NEW.rejected_qty <> v_received_qty THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Accepted and rejected quantities must equal quantity received';
    END IF;
END$$

CREATE TRIGGER trg_quality_inspections_before_delete
BEFORE DELETE ON quality_inspections
FOR EACH ROW
BEGIN
    DECLARE v_processed_at DATETIME;

    SELECT d.receipt_processed_at
      INTO v_processed_at
    FROM delivery_items AS di
    JOIN deliveries AS d ON d.delivery_id = di.delivery_id
    WHERE di.delivery_item_id = OLD.delivery_item_id;

    IF v_processed_at IS NOT NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot remove an inspection from a processed delivery';
    END IF;
END$$

CREATE PROCEDURE process_delivery(IN p_delivery_id BIGINT UNSIGNED)
BEGIN
    DECLARE v_processed_at DATETIME DEFAULT NULL;
    DECLARE v_warehouse_id BIGINT UNSIGNED;
    DECLARE v_purchase_order_id BIGINT UNSIGNED;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_not_found = TRUE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT d.receipt_processed_at, sh.warehouse_id, sh.purchase_order_id
      INTO v_processed_at, v_warehouse_id, v_purchase_order_id
    FROM deliveries AS d
    JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
    WHERE d.delivery_id = p_delivery_id
    FOR UPDATE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Delivery does not exist';
    END IF;

    IF v_processed_at IS NOT NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Delivery has already been processed';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM delivery_items WHERE delivery_id = p_delivery_id
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Delivery must contain at least one received line';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM delivery_items AS di
        LEFT JOIN quality_inspections AS qi
            ON qi.delivery_item_id = di.delivery_item_id
        WHERE di.delivery_id = p_delivery_id
          AND qi.quality_inspection_id IS NULL
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Every delivery line must have a quality inspection';
    END IF;

    INSERT INTO inventory (material_id, warehouse_id, quantity_on_hand)
    SELECT poi.material_id, v_warehouse_id, SUM(qi.accepted_qty)
    FROM delivery_items AS di
    JOIN purchase_order_items AS poi
        ON poi.purchase_order_item_id = di.purchase_order_item_id
    JOIN quality_inspections AS qi ON qi.delivery_item_id = di.delivery_item_id
    WHERE di.delivery_id = p_delivery_id
    GROUP BY poi.material_id
    HAVING SUM(qi.accepted_qty) > 0
    ON DUPLICATE KEY UPDATE
        quantity_on_hand = inventory.quantity_on_hand + VALUES(quantity_on_hand),
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO inventory_transactions (
        material_id,
        warehouse_id,
        delivery_id,
        transaction_type,
        quantity_delta,
        notes
    )
    SELECT poi.material_id,
           v_warehouse_id,
           p_delivery_id,
           'receipt',
           SUM(qi.accepted_qty),
           'Accepted quantity received after quality inspection'
    FROM delivery_items AS di
    JOIN purchase_order_items AS poi
        ON poi.purchase_order_item_id = di.purchase_order_item_id
    JOIN quality_inspections AS qi ON qi.delivery_item_id = di.delivery_item_id
    WHERE di.delivery_id = p_delivery_id
    GROUP BY poi.material_id
    HAVING SUM(qi.accepted_qty) > 0;

    UPDATE purchase_orders AS po
    SET po.status = CASE
        WHEN EXISTS (
            SELECT 1
            FROM purchase_order_items AS poi
            WHERE poi.purchase_order_id = v_purchase_order_id
        )
        AND NOT EXISTS (
            SELECT 1
            FROM purchase_order_items AS poi
            WHERE poi.purchase_order_id = v_purchase_order_id
              AND poi.quantity_ordered > COALESCE((
                  SELECT SUM(di.quantity_received)
                  FROM delivery_items AS di
                  JOIN deliveries AS d ON d.delivery_id = di.delivery_id
                  JOIN shipments AS sh ON sh.shipment_id = d.shipment_id
                  WHERE di.purchase_order_item_id = poi.purchase_order_item_id
                    AND sh.purchase_order_id = v_purchase_order_id
                    AND (d.receipt_processed_at IS NOT NULL
                         OR d.delivery_id = p_delivery_id)
              ), 0)
        ) THEN 'received'
        ELSE 'partially_received'
    END
    WHERE po.purchase_order_id = v_purchase_order_id;

    UPDATE deliveries
    SET receipt_processed_at = CURRENT_TIMESTAMP
    WHERE delivery_id = p_delivery_id;

    COMMIT;
END$$

DELIMITER ;
