"use strict";

const formatNumber = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat().format(number) : "—";
};

async function getData(url) {
  return window.Api.get(url);
}

function showError(element, error) {
  element.innerHTML = `<div class="error-state">Unable to load data<small>${escapeHtml(error.message)}</small></div>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function setMetric(name, value, failed = false) {
  const target = document.querySelector(`[data-metric="${name}"]`);
  const card = document.querySelector(`[data-metric-card="${name}"]`);
  if (target) target.textContent = failed ? "ERR" : formatNumber(value);
  if (failed && card) card.classList.add("has-error");
}

function statusClass(value) {
  if (["received", "processed", "active", "receipt", "in stock"].includes(String(value).toLowerCase())) return "good";
  if (["cancelled", "overdue", "issue"].includes(String(value).toLowerCase())) return "danger";
  if (["submitted", "partially_received", "draft", "adjustment", "reorder"].includes(String(value).toLowerCase())) return "warn";
  return "";
}

function renderTable(container, rows, columns, emptyMessage) {
  if (!rows.length) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(emptyMessage)}<small>No records were returned by the API.</small></div>`;
    return;
  }
  const headings = columns.map((column) => `<th scope="col">${escapeHtml(column.label)}</th>`).join("");
  const body = rows.map((row) => `<tr>${columns.map((column) => {
    const value = row[column.key];
    const content = value == null || value === "" ? "—" : escapeHtml(value);
    return `<td>${column.status
      ? `<span class="status-badge ${statusClass(value)}">${content}</span>`
      : `<span class="${column.mono ? "mono" : ""}">${content}</span>`}</td>`;
  }).join("")}</tr>`).join("");
  container.innerHTML = `<table><thead><tr>${headings}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderReorderChart(container, rows) {
  if (!rows.length) {
    container.innerHTML = '<div class="empty-state">No reorder alerts<small>All reported inventory lines are above reorder level.</small></div>';
    return;
  }
  const items = rows.slice(0, 6);
  const max = Math.max(...items.map((row) => Number(row.quantity_on_hand) || 0), 1);
  container.innerHTML = items.map((row) => {
    const label = row.sku || row.material_name || `Material ${row.material_id}`;
    const quantity = Number(row.quantity_on_hand) || 0;
    return `<div class="bar-row"><span class="bar-label" title="${escapeHtml(label)}">${escapeHtml(label)}</span><span class="bar-track" aria-label="${quantity} units on hand"><span class="bar-fill" style="width:${Math.max(quantity / max * 100, 2)}%"></span></span><span class="bar-quantity">${formatNumber(quantity)} on hand</span></div>`;
  }).join("");
}

function renderSupplierSignals(container, rows) {
  if (!rows.length) {
    container.innerHTML = '<div class="empty-state">No supplier records<small>Supplier report returned no rows.</small></div>';
    return;
  }
  container.innerHTML = rows.slice(0, 5).map((supplier) => {
    const delays = Number(supplier.delayed_deliveries) || 0;
    const rejection = supplier.rejection_rate_percent == null ? null : Number(supplier.rejection_rate_percent);
    const signaled = delays > 0 || (rejection !== null && rejection > 0);
    const rejectionText = rejection === null ? "—" : `${rejection.toFixed(1)}% rejected`;
    return `<div class="signal-row"><span class="signal-name">${escapeHtml(supplier.supplier_name || supplier.supplier_code || "Supplier")}</span><span class="signal-stat ${delays ? "alert" : ""}">${formatNumber(delays)} delayed</span><span class="signal-stat ${rejection > 0 ? "alert" : ""}">${rejectionText}${signaled ? " · !" : ""}</span></div>`;
  }).join("");
}

function renderRecentTransactions(container, rows) {
  renderTable(container, rows.slice(0, 5), [
    { key: "material_name", label: "MATERIAL" },
    { key: "warehouse_code", label: "LOCATION", mono: true },
    { key: "quantity_delta", label: "CHANGE" },
    { key: "transaction_type", label: "TYPE", status: true },
  ], "No inventory transactions");
}

function updateClock() {
  const target = document.querySelector("[data-clock]");
  if (target) target.textContent = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date());
}

async function loadDashboard() {
  const lowStockChart = document.querySelector("[data-reorder-chart]");
  const supplierSignals = document.querySelector("[data-supplier-signals]");
  const recentOrders = document.querySelector("[data-recent-orders]");
  const recentTransactions = document.querySelector("[data-recent-transactions]");

  const requests = [
    ["suppliers", "/api/suppliers", (rows) => setMetric("suppliers", rows.length)],
    ["materials", "/api/materials", (rows) => setMetric("materials", rows.length)],
    ["warehouses", "/api/warehouses", (rows) => setMetric("warehouses", rows.length)],
    ["inventory", "/api/inventory", (rows) => setMetric("inventory", rows.length)],
    ["low-stock", "/api/inventory/low-stock", (rows) => {
      setMetric("low-stock", rows.length);
      renderReorderChart(lowStockChart, rows);
    }],
    ["purchase-orders", "/api/purchase-orders", (rows) => {
      setMetric("purchase-orders", rows.filter((row) => ["submitted", "partially_received"].includes(row.status)).length);
      renderTable(recentOrders, rows.slice(-6).reverse(), [
        { key: "po_number", label: "ORDER", mono: true },
        { key: "supplier_name", label: "SUPPLIER" },
        { key: "ordered_at", label: "ORDERED", mono: true },
        { key: "expected_delivery_date", label: "EXPECTED", mono: true },
        { key: "status", label: "STATUS", status: true },
      ], "No purchase orders");
    }],
    ["pending-deliveries", "/api/deliveries", (rows) => {
      setMetric("pending-deliveries", rows.filter((row) => !row.receipt_processed_at).length);
    }],
    ["overdue", "/api/reports/overdue-purchase-orders", (rows) => setMetric("overdue", rows.length)],
    ["supplier-signals", "/api/reports/supplier-performance", (rows) => renderSupplierSignals(supplierSignals, rows)],
    ["transactions", "/api/inventory/transactions", (rows) => renderRecentTransactions(recentTransactions, rows)],
  ];
  const results = await Promise.allSettled(requests.map(([, url]) => getData(url)));
  results.forEach((result, index) => {
    const [name, , render] = requests[index];
    if (result.status === "fulfilled") render(result.value);
    else {
      if (["suppliers", "materials", "warehouses", "inventory", "low-stock", "purchase-orders", "pending-deliveries", "overdue"].includes(name)) setMetric(name, null, true);
      if (name === "low-stock") showError(lowStockChart, result.reason);
      if (name === "purchase-orders") showError(recentOrders, result.reason);
      if (name === "supplier-signals") showError(supplierSignals, result.reason);
      if (name === "transactions") showError(recentTransactions, result.reason);
    }
  });
  const updated = document.querySelector("[data-last-updated]");
  if (updated) updated.textContent = `Updated ${new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date())} UTC`;
}

function initNavigation() {
  const button = document.querySelector(".menu-toggle");
  const sidebar = document.querySelector(".sidebar");
  if (!button || !sidebar) return;
  button.addEventListener("click", () => {
    const open = sidebar.classList.toggle("is-open");
    button.setAttribute("aria-expanded", String(open));
    button.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
  });
  document.addEventListener("click", (event) => {
    if (!sidebar.contains(event.target) && !button.contains(event.target)) {
      sidebar.classList.remove("is-open");
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-label", "Open navigation");
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.classList.contains("is-open")) {
      sidebar.classList.remove("is-open");
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-label", "Open navigation");
      button.focus();
    }
  });
}

const PAGE_CONFIG = {
  inventory: {
    title: "Inventory", intro: "Live stock balances and reorder thresholds. Stock is updated only by the inspected receiving workflow.",
    endpoint: "/api/inventory", readOnly: true, columns: [
      ["sku", "SKU", true], ["material_name", "MATERIAL"], ["warehouse_code", "WAREHOUSE", true],
      ["quantity_on_hand", "ON HAND"], ["reorder_level", "REORDER AT"], ["stock_status", "STOCK STATUS", false, "status"],
      ["updated_at", "LAST UPDATED", true],
    ],
    extra: { title: "Inventory transaction history", endpoint: "/api/inventory/transactions", columns: [["occurred_at", "DATE", true], ["sku", "SKU", true], ["material_name", "MATERIAL"], ["warehouse_code", "WAREHOUSE", true], ["transaction_type", "TYPE", false, "status"], ["quantity_delta", "CHANGE"], ["delivery_number", "DELIVERY", true]] },
  },
  suppliers: {
    title: "Suppliers", intro: "Supplier directory and lead-time information connected to procurement records.",
    endpoint: "/api/suppliers", columns: [["supplier_code", "CODE", true], ["supplier_name", "SUPPLIER"], ["contact_name", "CONTACT"], ["email", "EMAIL"], ["lead_time_days", "LEAD TIME"], ["is_active", "ACTIVE", false, "boolean"]],
    form: { title: "Add supplier", fields: [
      { name: "supplier_code", label: "SUPPLIER CODE", required: true }, { name: "supplier_name", label: "SUPPLIER NAME", required: true },
      { name: "contact_name", label: "CONTACT NAME", nullable: true }, { name: "email", label: "EMAIL", type: "email", nullable: true },
      { name: "phone", label: "PHONE", nullable: true }, { name: "lead_time_days", label: "LEAD TIME (DAYS)", type: "number", value: "0" },
      { name: "is_active", label: "ACTIVE SUPPLIER", type: "checkbox" }, { name: "address", label: "ADDRESS", type: "textarea", full: true, nullable: true },
    ] }, editable: ["supplier_name", "contact_name", "email", "phone", "address", "lead_time_days", "is_active"], keys: (row) => row.supplier_id,
  },
  materials: {
    title: "Materials", intro: "Material master data, reorder levels and safety-stock definitions.",
    endpoint: "/api/materials", columns: [["sku", "SKU", true], ["material_name", "MATERIAL"], ["category", "CATEGORY"], ["unit_of_measure", "UNIT"], ["reorder_level", "REORDER AT"], ["safety_stock", "SAFETY STOCK"]],
    form: { title: "Add material", fields: [
      { name: "sku", label: "SKU", required: true }, { name: "material_name", label: "MATERIAL NAME", required: true },
      { name: "category", label: "CATEGORY", nullable: true }, { name: "unit_of_measure", label: "UNIT OF MEASURE", required: true },
      { name: "reorder_level", label: "REORDER LEVEL", type: "number", value: "0" }, { name: "safety_stock", label: "SAFETY STOCK", type: "number", value: "0" },
      { name: "is_active", label: "ACTIVE MATERIAL", type: "checkbox" },
    ] }, editable: ["material_name", "category", "unit_of_measure", "reorder_level", "safety_stock", "is_active"], keys: (row) => row.material_id,
  },
  warehouses: {
    title: "Warehouses", intro: "Locations available for inventory and inbound shipment receiving.",
    endpoint: "/api/warehouses", columns: [["warehouse_code", "CODE", true], ["warehouse_name", "WAREHOUSE"], ["location", "LOCATION"], ["is_active", "ACTIVE", false, "boolean"]],
    form: { title: "Add warehouse", fields: [
      { name: "warehouse_code", label: "WAREHOUSE CODE", required: true }, { name: "warehouse_name", label: "WAREHOUSE NAME", required: true },
      { name: "location", label: "LOCATION", required: true }, { name: "is_active", label: "ACTIVE WAREHOUSE", type: "checkbox" },
    ] }, editable: ["warehouse_name", "location", "is_active"], keys: (row) => row.warehouse_id,
  },
  "purchase-orders": {
    title: "Purchase orders", intro: "Order register with supplier, expected delivery and line-item details.",
    endpoint: "/api/purchase-orders", columns: [["po_number", "ORDER", true], ["supplier_name", "SUPPLIER"], ["ordered_at", "ORDERED", true], ["expected_delivery_date", "EXPECTED", true], ["status", "STATUS", false, "status"], ["line_count", "LINES"]],
    form: { title: "Create purchase order", fields: [
      { name: "po_number", label: "PO NUMBER", required: true }, { name: "supplier_id", label: "SUPPLIER", type: "select", source: "/api/suppliers", value: "supplier_id", text: (row) => `${row.supplier_code} · ${row.supplier_name}`, required: true },
      { name: "ordered_at", label: "ORDERED DATE", type: "date", required: true }, { name: "expected_delivery_date", label: "EXPECTED DELIVERY", type: "date" },
      { name: "status", label: "INITIAL STATUS", type: "select", options: [["draft", "Draft"], ["submitted", "Submitted"]], required: true },
    ], lines: "order" }, details: (row) => `/api/purchase-orders/${row.purchase_order_id}`,
  },
  shipments: {
    title: "Shipments", intro: "Inbound shipment tracking linked to an existing purchase order and receiving location.",
    endpoint: "/api/shipments", columns: [["shipment_number", "SHIPMENT", true], ["po_number", "PURCHASE ORDER", true], ["warehouse_name", "WAREHOUSE"], ["carrier", "CARRIER"], ["tracking_number", "TRACKING", true], ["estimated_delivery_at", "EST. ARRIVAL", true]],
    form: { title: "Register shipment", fields: [
      { name: "shipment_number", label: "SHIPMENT NUMBER", required: true }, { name: "purchase_order_id", label: "PURCHASE ORDER", type: "select", source: "/api/purchase-orders", value: "purchase_order_id", text: (row) => `${row.po_number} · ${row.supplier_name}`, required: true },
      { name: "warehouse_id", label: "RECEIVING WAREHOUSE", type: "select", source: "/api/warehouses", value: "warehouse_id", text: (row) => `${row.warehouse_code} · ${row.warehouse_name}`, required: true },
      { name: "tracking_number", label: "TRACKING NUMBER", nullable: true }, { name: "carrier", label: "CARRIER", nullable: true },
      { name: "shipped_at", label: "SHIPPED AT", type: "datetime-local" }, { name: "estimated_delivery_at", label: "ESTIMATED ARRIVAL", type: "datetime-local" },
    ] }, details: (row) => `/api/shipments/${row.shipment_id}`,
  },
  deliveries: {
    title: "Deliveries", intro: "Record received quantities against shipment purchase-order lines, then process inspected stock.",
    endpoint: "/api/deliveries", columns: [["delivery_number", "DELIVERY", true], ["shipment_number", "SHIPMENT", true], ["po_number", "PURCHASE ORDER", true], ["received_at", "RECEIVED", true], ["receipt_processed_at", "PROCESSED AT", true]],
    form: { title: "Record delivery", fields: [
      { name: "delivery_number", label: "DELIVERY NUMBER", required: true }, { name: "shipment_id", label: "SHIPMENT", type: "select", source: "/api/shipments", value: "shipment_id", text: (row) => `${row.shipment_number} · ${row.po_number}`, required: true },
      { name: "received_at", label: "RECEIVED AT", type: "datetime-local", required: true }, { name: "notes", label: "NOTES", type: "textarea", full: true },
    ], lines: "delivery" }, details: (row) => `/api/deliveries/${row.delivery_id}`, process: true,
  },
  inspections: {
    title: "Quality inspections", intro: "Record accepted and rejected quantities for each received delivery line before processing.",
    endpoint: null, inspections: true,
    form: { title: "Record inspection", fields: [
      { name: "delivery_id", label: "DELIVERY", type: "select", source: "/api/deliveries", value: "delivery_id", text: (row) => `${row.delivery_number} · ${row.received_at}`, required: true },
      { name: "delivery_item_id", label: "DELIVERY LINE", type: "select", options: [], required: true },
      { name: "accepted_qty", label: "ACCEPTED QUANTITY", type: "number", required: true },
      { name: "rejected_qty", label: "REJECTED QUANTITY", type: "number", required: true },
      { name: "inspected_at", label: "INSPECTED AT", type: "datetime-local" }, { name: "notes", label: "NOTES", type: "textarea", full: true },
    ] },
  },
  "risk-reports": {
    title: "Reports & analytics", intro: "Operational reports based on supplier performance, stock thresholds, receiving transactions and overdue purchase orders.",
    reports: true,
  },
};

function fieldMarkup(field) {
  const type = field.type || "text";
  const common = `id="field-${escapeHtml(field.name)}" name="${escapeHtml(field.name)}" ${field.required ? "required" : ""}`;
  if (type === "textarea") return `<textarea ${common} rows="2"></textarea>`;
  if (type === "checkbox") return `<input ${common} type="checkbox" checked>`;
  if (type === "select") {
    const options = field.options
      ? field.options.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("")
      : `<option value="">Loading choices…</option>`;
    return `<select ${common} data-source="${escapeHtml(field.source || "")}" data-value-key="${escapeHtml(field.value || "")}" data-label-source="${field.source ? "lookup" : "static"}">${options}</select>`;
  }
  return `<input ${common} type="${escapeHtml(type)}" ${type === "number" ? 'min="0" step="1"' : ""} ${field.value !== undefined ? `value="${escapeHtml(field.value)}"` : ""} ${field.required ? "aria-required=true" : ""}>`;
}

function renderForm(container, form) {
  container.innerHTML = form.fields.map((field) => `
    <div class="field ${field.full ? "full-width" : ""}">
      <label for="field-${escapeHtml(field.name)}">${escapeHtml(field.label)}${field.required ? " *" : ""}</label>
      ${fieldMarkup(field)}
    </div>`).join("");
  if (form.lines) {
    const heading = form.lines === "order" ? "PURCHASE ORDER LINES" : "RECEIVED LINES";
    const labels = form.lines === "order"
      ? "<span>Material</span><span>Quantity</span><span>Unit cost</span><span></span>"
      : "<span>Purchase order line</span><span>Quantity received</span><span></span>";
    container.insertAdjacentHTML("beforeend", `<div class="line-builder" data-line-builder data-line-type="${form.lines}"><div class="line-builder-heading"><span>${heading}</span><button class="line-add" type="button" data-add-line>+ Add line</button></div><div class="line-item-labels">${labels}</div><div data-line-items></div></div>`);
  }
}

function fieldValue(form, name) {
  return form.elements.namedItem(name);
}

function inputElement(name, type, required = false) {
  const minimum = type === "number" ? (name === "line_cost" ? 0 : 1) : "";
  const labels = {
    line_material: "Material",
    line_item: "Purchase order line",
    line_quantity: "Quantity",
    line_cost: "Unit cost",
  };
  return `<input name="${escapeHtml(name)}" aria-label="${labels[name]}" type="${type}" ${type === "number" ? `min="${minimum}" step="${name === "line_cost" ? "0.01" : "1"}"` : ""} ${required ? "required" : ""}>`;
}

function addLine(container, lineType, materials = []) {
  const holder = container.querySelector("[data-line-items]");
  const select = lineType === "order"
    ? `<select name="line_material" aria-label="Material" required><option value="">Choose material…</option>${materials.map((row) => `<option value="${escapeHtml(row.material_id)}">${escapeHtml(row.sku)} · ${escapeHtml(row.material_name)}</option>`).join("")}</select>`
    : '<select name="line_item" aria-label="Purchase order line" required disabled><option value="">Choose shipment first…</option></select>';
  const inputs = lineType === "order"
    ? `${inputElement("line_quantity", "number", true)}${inputElement("line_cost", "number", true)}`
    : `${inputElement("line_quantity", "number", true)}`;
  const row = document.createElement("div");
  row.className = "line-item";
  row.innerHTML = `${select}${inputs}<button type="button" aria-label="Remove line">×</button>`;
  row.querySelector("button").addEventListener("click", () => row.remove());
  holder.append(row);
  return row;
}

function tableMarkup(rows, columns, { actions = false, empty = "No records found." } = {}) {
  if (!rows.length) return `<div class="empty-state">${escapeHtml(empty)}<small>No matching records were returned by the API.</small></div>`;
  const th = columns.map((column) => `<th scope="col">${escapeHtml(column[1])}</th>`).join("");
  const body = rows.map((row, index) => `<tr data-row-search="${escapeHtml(columns.map(([key]) => row[key]).join(" "))}">${columns.map(([key, label, mono, kind]) => {
    const raw = row[key];
    if (kind === "boolean") return `<td><span class="status-badge ${raw ? "good" : "warn"}">${raw ? "ACTIVE" : "INACTIVE"}</span></td>`;
    if (kind === "status") return `<td><span class="status-badge ${statusClass(raw)}">${escapeHtml(raw || "—")}</span></td>`;
    return `<td><span class="${mono ? "mono" : ""}">${raw == null || raw === "" ? "—" : escapeHtml(raw)}</span></td>`;
  }).join("")}${actions ? `<td><div class="record-actions">${actions(row, index)}</div></td>` : ""}</tr>`).join("");
  const actionHeader = actions ? "<th scope=\"col\">ACTIONS</th>" : "";
  return `<table><thead><tr>${th}${actionHeader}</tr></thead><tbody>${body}</tbody></table>`;
}

function registerFilter(container, filter) {
  filter.oninput = () => {
    const term = filter.value.trim().toLowerCase();
    container.querySelectorAll("tbody tr").forEach((row) => {
      row.hidden = !row.dataset.rowSearch.toLowerCase().includes(term);
    });
  };
}

function renderRecordDetail(record) {
  const fields = Object.entries(record).filter(([, value]) => !Array.isArray(value));
  const summary = fields.map(([key, value]) => `<div><dt>${escapeHtml(key.replaceAll("_", " "))}</dt><dd>${value == null || value === "" ? "—" : escapeHtml(value)}</dd></div>`).join("");
  const items = Array.isArray(record.items)
    ? `<div class="detail-items"><h3>Line items</h3>${tableMarkup(record.items, [
      ["sku", "SKU", true],
      ["material_name", "MATERIAL"],
      ["quantity_ordered", "ORDERED"],
      ["quantity_received", "RECEIVED"],
      ["unit_cost", "UNIT COST"],
    ])}</div>`
    : "";
  return `<div class="record-detail"><dl>${summary}</dl>${items}</div>`;
}

function pathFor(config, row) {
  return typeof config.keys(row) === "string"
    ? `${config.endpoint}/${config.keys(row)}`
    : `${config.endpoint}/${config.keys(row)}`;
}

function getEntityActions(config, row, index, records) {
  const buttons = [];
  if (config.editable) buttons.push(`<button type="button" class="button button-subtle" data-action="edit" data-index="${index}">EDIT</button>`);
  if (config.details) buttons.push(`<button type="button" class="button button-subtle" data-action="details" data-index="${index}">DETAILS</button>`);
  if (config.process && !row.receipt_processed_at) buttons.push(`<button type="button" class="button button-primary" data-action="process" data-index="${index}">PROCESS</button>`);
  if (config.editable) buttons.push(`<button type="button" class="button button-danger" data-action="delete" data-index="${index}">DELETE</button>`);
  return buttons.join("");
}

function setFormMessage(target, message, success = false) {
  target.textContent = message;
  target.classList.toggle("success", success);
}

async function initManagementPage(root, page, config) {
  const title = document.querySelector("[data-page-title]");
  const intro = document.querySelector("[data-page-intro]");
  const panel = document.querySelector("[data-form-panel]");
  const table = document.querySelector("[data-record-table]");
  const form = document.querySelector("[data-record-form]");
  const fieldsHolder = document.querySelector("[data-form-fields]");
  const message = document.querySelector("[data-form-message]");
  const filter = document.querySelector("[data-filter]");
  const count = document.querySelector("[data-record-count]");
  const records = [];
  let lookup = {};
  let editing = null;
  title.textContent = config.title;
  intro.textContent = config.intro;
  document.querySelector("[data-register-title]").textContent = config.reports ? "Supplier performance" : config.inspections ? "Delivery inspections" : `${config.title} register`;

  if (config.reports) {
    panel.hidden = true;
    filter.closest("label").hidden = true;
    table.innerHTML = `<div class="report-grid">
      <article class="panel"><div class="panel-heading"><div><p class="eyebrow">QUALITY &amp; DELIVERY</p><h2>Supplier performance</h2></div></div><div class="table-wrap" data-supplier-report><div class="loading-state">Loading supplier performance…</div></div></article>
      <article class="panel"><div class="panel-heading"><div><p class="eyebrow">STOCK CONTROL</p><h2>Reorder report</h2></div></div><div class="table-wrap" data-reorder-report><div class="loading-state">Loading reorder report…</div></div></article>
      <article class="panel"><div class="panel-heading"><div><p class="eyebrow">DELIVERY EXPOSURE</p><h2>Overdue purchase orders</h2></div></div><div class="table-wrap" data-overdue-report><div class="loading-state">Loading overdue orders…</div></div></article>
      <article class="panel"><div class="panel-heading"><div><p class="eyebrow">INVENTORY AUDIT</p><h2>Recent transactions</h2></div></div><div class="table-wrap" data-transaction-report><div class="loading-state">Loading inventory transactions…</div></div></article>
    </div>`;
    const reportTargets = [
      {
        selector: "[data-supplier-report]",
        url: "/api/reports/supplier-performance",
        columns: [["supplier_code", "CODE", true], ["supplier_name", "SUPPLIER"], ["delivery_count", "DELIVERIES"], ["delayed_deliveries", "DELAYED"], ["rejection_rate_percent", "REJECTION %"]],
        empty: "No supplier performance records.",
      },
      {
        selector: "[data-reorder-report]",
        url: "/api/inventory/low-stock",
        columns: [["sku", "SKU", true], ["material_name", "MATERIAL"], ["warehouse_code", "WAREHOUSE", true], ["quantity_on_hand", "ON HAND"], ["reorder_level", "REORDER AT"]],
        empty: "No reorder alerts.",
      },
      {
        selector: "[data-overdue-report]",
        url: "/api/reports/overdue-purchase-orders",
        columns: [["po_number", "ORDER", true], ["supplier_name", "SUPPLIER"], ["expected_delivery_date", "EXPECTED", true], ["quantity_outstanding", "OUTSTANDING"], ["status", "STATUS", false, "status"]],
        empty: "No overdue purchase orders.",
      },
      {
        selector: "[data-transaction-report]",
        url: "/api/inventory/transactions",
        columns: [["occurred_at", "DATE", true], ["sku", "SKU", true], ["warehouse_code", "WAREHOUSE", true], ["transaction_type", "TYPE", false, "status"], ["quantity_delta", "CHANGE"]],
        empty: "No inventory transactions.",
      },
    ];
    const results = await Promise.allSettled(reportTargets.map(({ url }) => getData(url)));
    results.forEach((result, index) => {
      const target = table.querySelector(reportTargets[index].selector);
      if (result.status === "fulfilled") {
        target.innerHTML = tableMarkup(result.value, reportTargets[index].columns, { empty: reportTargets[index].empty });
      } else showError(target, result.reason);
    });
    const successfulReports = results.filter((result) => result.status === "fulfilled").length;
    count.textContent = `${successfulReports} OF ${reportTargets.length} REPORTS AVAILABLE`;
    return;
  }

  if (config.form) {
    document.querySelector("[data-form-title]").textContent = config.form.title;
    renderForm(fieldsHolder, config.form);
    if (config.inspections) {
      const deliverySelect = fieldValue(form, "delivery_id");
      const lineSelect = fieldValue(form, "delivery_item_id");
      lineSelect.disabled = true;
      lineSelect.innerHTML = '<option value="">Choose a delivery first…</option>';
      deliverySelect.addEventListener("change", async () => {
        lineSelect.innerHTML = '<option value="">Loading delivery lines…</option>';
        lineSelect.disabled = true;
        if (!deliverySelect.value) {
          lineSelect.innerHTML = '<option value="">Choose a delivery first…</option>';
          return;
        }
        try {
          const delivery = await getData(`/api/deliveries/${encodeURIComponent(deliverySelect.value)}`);
          const available = (delivery.items || []).filter((item) => item.quality_inspection_id == null);
          lineSelect.innerHTML = '<option value="">Choose an uninspected line…</option>' + available.map((item) => `<option value="${escapeHtml(item.delivery_item_id)}" data-received-qty="${escapeHtml(item.quantity_received)}">${escapeHtml(item.sku)} · ${escapeHtml(item.material_name)} · ${escapeHtml(item.quantity_received)} received</option>`).join("");
          lineSelect.disabled = available.length === 0;
          if (!available.length) setFormMessage(message, "Every line on this delivery has already been inspected.");
        } catch (error) {
          lineSelect.innerHTML = '<option value="">Unable to load delivery lines</option>';
          setFormMessage(message, error.message);
        }
      });
    }
    if (config.form.lines === "order") {
      try {
        lookup.materials = await getData("/api/materials");
      } catch (error) {
        setFormMessage(message, error.message);
        lookup.materials = [];
      }
      addLine(fieldsHolder, "order", lookup.materials);
      fieldsHolder.querySelector("[data-add-line]").addEventListener("click", () => addLine(fieldsHolder, "order", lookup.materials));
    } else if (config.form.lines === "delivery") {
      addLine(fieldsHolder, "delivery");
      fieldsHolder.querySelector("[data-add-line]").addEventListener("click", () => addLine(fieldsHolder, "delivery"));
      const shipmentSelect = fieldValue(form, "shipment_id");
      shipmentSelect.addEventListener("change", async () => {
        const orderId = lookup.shipments?.find((row) => String(row.shipment_id) === shipmentSelect.value)?.purchase_order_id;
        lookup.orderLines = [];
        for (const lineSelect of fieldsHolder.querySelectorAll('[name="line_item"]')) {
          lineSelect.disabled = true;
          lineSelect.innerHTML = '<option value="">Loading purchase-order lines…</option>';
        }
        if (!orderId) return;
        try {
          const order = await getData(`/api/purchase-orders/${encodeURIComponent(orderId)}`);
          lookup.orderLines = order.items || [];
          for (const lineSelect of fieldsHolder.querySelectorAll('[name="line_item"]')) {
            lineSelect.innerHTML = '<option value="">Choose a purchase-order line…</option>' + lookup.orderLines.map((item) => {
              const remaining = Number(item.quantity_ordered) - Number(item.quantity_received);
              return `<option value="${escapeHtml(item.purchase_order_item_id)}" ${remaining <= 0 ? "disabled" : ""}>${escapeHtml(item.sku)} · ${escapeHtml(item.material_name)} · ${formatNumber(remaining)} remaining</option>`;
            }).join("");
            lineSelect.disabled = false;
          }
        } catch (error) {
          setFormMessage(message, error.message);
        }
      });
    }
  } else panel.hidden = true;

  if (config.form) {
    const selects = [...fieldsHolder.querySelectorAll("select[data-source]")];
    for (const select of selects) {
      const field = config.form.fields.find((item) => item.name === select.name);
      if (field?.source === "/api/shipments") {
        try {
          lookup.shipments = await getData(field.source);
          select.innerHTML = '<option value="">Choose a record…</option>' + lookup.shipments.map((row) => `<option value="${escapeHtml(row.shipment_id)}">${escapeHtml(field.text(row))}</option>`).join("");
        } catch (error) {
          select.innerHTML = '<option value="">Could not load shipments</option>';
          setFormMessage(message, error.message);
        }
      } else if (field) {
        try {
          const choices = await getData(field.source);
          select.innerHTML = '<option value="">Choose a record…</option>' + choices.map((row) => `<option value="${escapeHtml(row[field.value])}">${escapeHtml(field.text(row))}</option>`).join("");
        } catch (error) {
          select.innerHTML = `<option value="">Could not load ${escapeHtml(field.label.toLowerCase())}</option>`;
          setFormMessage(message, error.message);
        }
      }
    }
  }

  const loadRegister = async () => {
    table.innerHTML = '<div class="loading-state">Reading the live register…</div>';
    try {
      if (config.inspections) {
        const rows = await getData("/api/inspections");
        count.textContent = `${rows.length} INSPECTIONS`;
        table.innerHTML = tableMarkup(rows, [["delivery_number", "DELIVERY", true], ["po_number", "PURCHASE ORDER", true], ["sku", "SKU", true], ["material_name", "MATERIAL"], ["quantity_received", "RECEIVED"], ["accepted_qty", "ACCEPTED"], ["rejected_qty", "REJECTED"], ["inspected_at", "INSPECTED AT", true]], { empty: "No quality inspections recorded." });
        return;
      }
      let loaded = await getData(config.endpoint);
      if (config.readOnly) {
        const [materials, warehouses, reorder] = await Promise.all([
          getData("/api/materials"), getData("/api/warehouses"), getData("/api/inventory/low-stock"),
        ]);
        const materialById = new Map(materials.map((row) => [String(row.material_id), row]));
        const warehouseById = new Map(warehouses.map((row) => [String(row.warehouse_id), row]));
        const reorderKeys = new Set(reorder.map((row) => `${row.material_id}/${row.warehouse_id}`));
        loaded = loaded.map((row) => {
          const material = materialById.get(String(row.material_id));
          const warehouse = warehouseById.get(String(row.warehouse_id));
          return {
            ...row,
            sku: material?.sku,
            material_name: material?.material_name,
            reorder_level: material?.reorder_level,
            warehouse_code: warehouse?.warehouse_code,
            stock_status: reorderKeys.has(`${row.material_id}/${row.warehouse_id}`) ? "Reorder" : "In stock",
          };
        });
      }
      records.splice(0, records.length, ...loaded);
      count.textContent = `${loaded.length} RECORDS`;
      if (config.editable || config.details || config.process) {
        table.innerHTML = tableMarkup(loaded, config.columns, { actions: (row, index) => getEntityActions(config, row, index, loaded) });
      } else table.innerHTML = tableMarkup(loaded, config.columns);
      if (filter) registerFilter(table, filter);
    } catch (error) {
      count.textContent = "REGISTER UNAVAILABLE";
      showError(table, error);
    }
  };

  if (config.extra) {
    const extra = document.querySelector("[data-supplementary]");
    extra.hidden = false;
    document.querySelector("[data-supplementary-title]").textContent = config.extra.title;
    try {
      const rows = await getData(config.extra.endpoint);
      document.querySelector("[data-supplementary-table]").innerHTML = tableMarkup(rows, config.extra.columns, { empty: "No reorder alerts." });
    } catch (error) {
      showError(document.querySelector("[data-supplementary-table]"), error);
    }
  }

  if (config.editable) {
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "button button-subtle";
    editButton.textContent = "CANCEL EDIT";
    editButton.hidden = true;
    editButton.dataset.cancelEdit = "true";
    editButton.addEventListener("click", () => {
      editing = null;
      form.reset();
      document.querySelector("[data-submit-label]").textContent = "ADD TO REGISTER";
      editButton.hidden = true;
      setFormMessage(message, "");
    });
    form.querySelector(".button-primary").insertAdjacentElement("afterend", editButton);
  }

  table.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const row = records[Number(button.dataset.index)];
    if (!row) return;
    const action = button.dataset.action;
    button.disabled = true;
    try {
      if (action === "details") {
        const detail = await getData(config.details(row));
        const existing = button.closest("tr").nextElementSibling;
        if (existing?.classList.contains("detail-row")) { existing.remove(); return; }
        const detailRow = document.createElement("tr");
        detailRow.className = "detail-row";
        const cell = document.createElement("td");
        cell.colSpan = config.columns.length + 1;
        cell.innerHTML = renderRecordDetail(detail);
        detailRow.append(cell);
        button.closest("tr").after(detailRow);
      } else if (action === "process") {
        if (!window.confirm(`Process delivery ${row.delivery_number}? This applies accepted inspection quantities to inventory.`)) return;
        await window.Api.post(`/api/deliveries/${encodeURIComponent(row.delivery_id)}/process`);
        const [inventory, orders] = await Promise.allSettled([
          getData("/api/inventory"),
          getData("/api/purchase-orders"),
        ]);
        const refreshMessage = inventory.status === "fulfilled" && orders.status === "fulfilled"
          ? `Refreshed ${inventory.value.length} inventory balances and ${orders.value.length} purchase orders.`
          : [
            inventory.status === "rejected" ? `Inventory refresh failed: ${inventory.reason.message}` : "",
            orders.status === "rejected" ? `Purchase-order refresh failed: ${orders.reason.message}` : "",
          ].filter(Boolean).join(" ");
        setFormMessage(message, `Delivery processed. ${refreshMessage}`, true);
        await loadRegister();
      } else if (action === "delete") {
        if (!window.confirm(`Delete this ${config.title.toLowerCase()} record?`)) return;
        await window.Api.delete(pathFor(config, row));
        setFormMessage(message, "Record deleted.", true);
        await loadRegister();
      } else if (action === "edit") {
        editing = row;
        for (const input of [...form.elements]) {
          if (input.name && config.editable.includes(input.name)) {
            if (input.type === "checkbox") input.checked = Boolean(row[input.name]);
            else input.value = row[input.name] ?? "";
          }
        }
        document.querySelector("[data-submit-label]").textContent = "Save changes";
        form.querySelector("[data-cancel-edit]").hidden = false;
        setFormMessage(message, `Editing record ${config.keys(row)}.`);
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      setFormMessage(message, error.message);
    } finally {
      button.disabled = false;
    }
  });

  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      setFormMessage(message, "");
      const submit = form.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        let payload;
        if (config.form.lines === "order") {
          const lines = [...fieldsHolder.querySelectorAll(".line-item")].map((line) => ({
            material_id: Number(line.querySelector('[name="line_material"]').value),
            quantity_ordered: Number(line.querySelector('[name="line_quantity"]').value),
            unit_cost: line.querySelector('[name="line_cost"]').value,
          }));
          if (new Set(lines.map((line) => line.material_id)).size !== lines.length) {
            throw new Error("Choose each material only once per purchase order.");
          }
          payload = {
            po_number: fieldValue(form, "po_number").value,
            supplier_id: Number(fieldValue(form, "supplier_id").value),
            ordered_at: fieldValue(form, "ordered_at").value,
            expected_delivery_date: fieldValue(form, "expected_delivery_date").value || null,
            status: fieldValue(form, "status").value,
            items: lines,
          };
        } else if (config.form.lines === "delivery") {
          const lines = [...fieldsHolder.querySelectorAll(".line-item")].map((line) => ({
            purchase_order_item_id: Number(line.querySelector('[name="line_item"]').value),
            quantity_received: Number(line.querySelector('[name="line_quantity"]').value),
          }));
          if (new Set(lines.map((line) => line.purchase_order_item_id)).size !== lines.length) {
            throw new Error("Choose each purchase-order line only once per delivery.");
          }
          for (const line of lines) {
            const orderLine = lookup.orderLines?.find((item) => Number(item.purchase_order_item_id) === line.purchase_order_item_id);
            const remaining = orderLine ? Number(orderLine.quantity_ordered) - Number(orderLine.quantity_received) : 0;
            if (!orderLine || line.quantity_received > remaining) {
              throw new Error("A received quantity exceeds the remaining amount on its purchase-order line.");
            }
          }
          payload = {
            delivery_number: fieldValue(form, "delivery_number").value,
            shipment_id: Number(fieldValue(form, "shipment_id").value),
            received_at: fieldValue(form, "received_at").value,
            notes: fieldValue(form, "notes").value || null,
            items: lines,
          };
        } else if (config.inspections) {
          const selectedLine = fieldValue(form, "delivery_item_id").selectedOptions[0];
          const received = Number(selectedLine?.dataset.receivedQty);
          const accepted = Number(fieldValue(form, "accepted_qty").value);
          const rejected = Number(fieldValue(form, "rejected_qty").value);
          if (accepted + rejected !== received) {
            throw new Error(`Accepted and rejected quantities must total ${formatNumber(received)} received.`);
          }
          payload = {
            delivery_item_id: Number(fieldValue(form, "delivery_item_id").value),
            accepted_qty: accepted,
            rejected_qty: rejected,
            inspected_at: fieldValue(form, "inspected_at").value || null,
            notes: fieldValue(form, "notes").value || null,
          };
        } else {
          payload = {};
          config.form.fields.forEach((field) => {
            const input = fieldValue(form, field.name);
            if (!input) return;
            let value = input.type === "checkbox" ? input.checked : input.value;
            if (value === "" && field.nullable) value = null;
            if (value === "" && !field.required) return;
            if (["number", "select"].includes(field.type) && value !== null) value = Number(value);
            payload[field.name] = value;
          });
          if (editing) {
            payload = Object.fromEntries(Object.entries(payload).filter(([key]) => config.editable.includes(key)));
          }
        }
        const url = editing ? pathFor(config, editing) : config.endpoint || `/api/deliveries/${encodeURIComponent(fieldValue(form, "delivery_id").value)}/inspections`;
        if (editing) await window.Api.patch(url, payload);
        else await window.Api.post(url, payload);
        setFormMessage(message, editing ? "Changes saved." : "Record added to the live register.", true);
        if (!editing) form.reset();
        else {
          editing = null;
          document.querySelector("[data-submit-label]").textContent = "Save record";
          form.querySelector("[data-cancel-edit]").hidden = true;
        }
        if (!editing && config.form.lines === "order") {
          fieldsHolder.querySelectorAll(".line-item").forEach((line) => line.remove());
          addLine(fieldsHolder, "order", lookup.materials);
        }
        if (config.form.lines === "delivery") {
          if (!editing) {
            fieldsHolder.querySelectorAll(".line-item").forEach((line) => line.remove());
            addLine(fieldsHolder, "delivery");
          }
          fieldsHolder.querySelectorAll('[name="line_item"]').forEach((select) => {
            select.disabled = true;
            select.innerHTML = '<option value="">Choose shipment first…</option>';
          });
          lookup.orderLines = [];
        }
        if (config.inspections) {
          const lineSelect = fieldValue(form, "delivery_item_id");
          lineSelect.disabled = true;
          lineSelect.innerHTML = '<option value="">Choose a delivery first…</option>';
        }
        await loadRegister();
      } catch (error) {
        setFormMessage(message, error.message);
      } finally {
        submit.disabled = false;
      }
    });
  }
  await loadRegister();
}

updateClock();
window.setInterval(updateClock, 1000);
initNavigation();
if (document.querySelector("[data-reorder-chart]")) loadDashboard();
const pageRoot = document.querySelector("[data-page]");
if (pageRoot && PAGE_CONFIG[pageRoot.dataset.page]) {
  initManagementPage(pageRoot, pageRoot.dataset.page, PAGE_CONFIG[pageRoot.dataset.page]);
}
