# Olist E-Commerce Data Dictionary & Validated Baselines

This document outlines the real schema, entity relationships, caveats, and audited reference metrics for the Olist dataset in PostgreSQL (`olist_db`).

---

## 1. Validated Reference Metrics (Ground Truth)

All metrics below have been audited directly against the live PostgreSQL database (`olist_db`):

| Metric | Validated Ground Truth | Calculation / Context |
| :--- | :--- | :--- |
| **Total Registered Orders** | **99,441** | `COUNT(*)` / `COUNT(DISTINCT order_id)` from `orders` table |
| **Orders with Items (Purchased)** | **98,666** | `COUNT(DISTINCT order_id)` from `order_items` table |
| **Orders without Line Items** | **775** | Orders canceled/unavailable before fulfillment (603 unavailable, 164 canceled, 5 created, 2 invoiced, 1 shipped) |
| **Total Merchandise Revenue** | **R$ 13,591,643.70** | `SUM(price)` across all `order_items` (excludes freight) |
| **Delivered Orders** | **96,478** | `WHERE order_status = 'delivered'` (all 96,478 exist in `order_items`) |
| **Delivery Rate (Registered)** | **97.02%** | 96,478 delivered / 99,441 total registered orders |
| **Delivery Rate (Purchased)** | **97.78%** | 96,478 delivered / 98,666 orders with line items |
| **Total Order Items** | **112,650** | `COUNT(*)` from `order_items` |
| **Average Item Price** | **R$ 120.65** | `AVG(price)` across `order_items` |
| **Total Freight Value**| **R$ 2,251,909.54** | `SUM(freight_value)` across `order_items` |
| **Average Freight / Item** | **R$ 19.99** | `AVG(freight_value)` across `order_items` |
| **Average Product Weight** | **2,276.47 g** (~2.28 kg) | `AVG(product_weight_g)` across registered `products` |
| **Unique Customers** | **96,096** | `COUNT(DISTINCT customer_unique_id)` |
| **Total Customer Addresses** | **99,441** | `COUNT(customer_id)` (1 checkout token per registered order) |
| **Repeat Customers** | **2,997** customers | Customers with $\ge 2$ distinct orders (`order_count > 1`) |
| **Repeat Customer Rate** | **3.12%** (3.1188%) | 2,997 repeat buyers / 96,096 unique customer IDs |
| **Active Sellers** | **3,095** | `COUNT(DISTINCT seller_id)` |
| **Total Products** | **32,951** | `COUNT(DISTINCT product_id)` |
| **Product Categories** | **73** | `COUNT(DISTINCT product_category_name)` |
| **Overall Review Score** | **4.0864** (~4.09★) | `AVG(review_score)` across all 99,224 rows |
| **Total Reviews** | **99,224** | Rows in `order_reviews` (98,410 unique `review_id`) |
| **Reviews with Text** | **42,687** | `WHERE review_comment_message IS NOT NULL` (43.0% of all reviews) |
| **Written Review Score** | **3.70★** | `AVG(review_score)` for reviews with text |
| **Negative Written Reviews** | **10,861** | Unique `review_id` with rating 1 or 2 and text |
| **Date Range** | **2016-09-04 to 2018-10-17** | `order_purchase_timestamp` span |

---

## 2. Table Specifications

### 2.1 `orders` (Grain: 1 row per order)
- `order_id` (VARCHAR PK): Unique order identifier.
- `customer_id` (VARCHAR FK $\rightarrow$ `customers.customer_id`): Per-order customer identifier.
- `order_status` (VARCHAR): Status (`delivered`, `shipped`, `canceled`, `invoiced`, `processing`, `created`, `approved`, `unavailable`).
- `order_purchase_timestamp` (TIMESTAMP): Purchase timestamp.
- `order_approved_at` (TIMESTAMP): Payment approval timestamp.
- `order_delivered_carrier_date` (TIMESTAMP): Handoff to postal/carrier.
- `order_delivered_customer_date` (TIMESTAMP): Actual delivery timestamp to customer.
- `order_estimated_delivery_date` (TIMESTAMP): Promised delivery estimate.

### 2.2 `order_items` (Grain: 1 row per item in order)
- `order_id` (VARCHAR FK $\rightarrow$ `orders.order_id`): Parent order.
- `order_item_id` (INT): Sequential item number within order (1, 2, ...).
- `product_id` (VARCHAR FK $\rightarrow$ `products.product_id`): Sold product.
- `seller_id` (VARCHAR FK $\rightarrow$ `sellers.seller_id`): Fulfilling merchant.
- `shipping_limit_date` (TIMESTAMP): Seller fulfillment deadline.
- `price` (DECIMAL): Item purchase price in BRL.
- `freight_value` (DECIMAL): Freight charged for this specific item.

### 2.3 `customers` (Grain: 1 row per customer order address)
- `customer_id` (VARCHAR PK): Per-order customer token.
- `customer_unique_id` (VARCHAR): True citizen/customer identifier (use this for repeat customer analysis!).
- `customer_zip_code_prefix` (INT): Zip prefix.
- `customer_city` (VARCHAR): City name.
- `customer_state` (VARCHAR): 2-letter state code (e.g., `SP`, `RJ`, `MG`).

### 2.4 `order_reviews` (Grain: 1 row per review submission)
- `review_id` (VARCHAR): Review token.
- `order_id` (VARCHAR FK $\rightarrow$ `orders.order_id`): Reviewed order.
- `review_score` (INT): Rating 1 to 5 stars.
- `review_comment_title` (VARCHAR): Review heading in Portuguese.
- `review_comment_message` (TEXT): Free-form review text in Portuguese.
- `review_creation_date` (TIMESTAMP): Form generation timestamp.
- `review_answer_timestamp` (TIMESTAMP): Customer submission timestamp.

### 2.5 `order_payments` (Grain: 1 row per payment installment/slip)
- `order_id` (VARCHAR FK $\rightarrow$ `orders.order_id`).
- `payment_sequential` (INT): Sequence number.
- `payment_type` (VARCHAR): `credit_card`, `boleto`, `voucher`, `debit_card`, `not_defined`.
- `payment_installments` (INT): Number of monthly installments.
- `payment_value` (DECIMAL): Transaction value.

### 2.6 `products` (Grain: 1 row per product SKU)
- `product_id` (VARCHAR PK).
- `product_category_name` (VARCHAR): Category name in Portuguese.
- Dimensions: `product_name_lenght`, `product_description_lenght`, `product_photos_qty`, `product_weight_g`, `product_length_cm`, `product_height_cm`, `product_width_cm`.

### 2.7 `sellers` (Grain: 1 row per merchant)
- `seller_id` (VARCHAR PK).
- `seller_zip_code_prefix` (INT).
- `seller_city` (VARCHAR).
- `seller_state` (VARCHAR).

### 2.8 `product_category_name_translation`
- `product_category_name` (VARCHAR PK): Portuguese category name.
- `product_category_name_english` (VARCHAR): English translation (71 entries mapped).

### 2.9 `geolocation`
- Coordinates and state prefixes (`geolocation_lat`, `geolocation_lng`, `geolocation_city`, `geolocation_state`).

---

## 3. Critical Analytical Warnings & Joins

1. **Revenue Calculation**: Always compute revenue as `SUM(oi.price)`. Do not use `order_payments.payment_value` for product revenue because payment value includes freight, vouchers, and installment interest.
2. **Double-Counting Avoidance**: When joining `orders`, `order_items`, and `order_payments`, items and payments fan out independently. Always aggregate `order_items` and `order_payments` in CTEs before joining!
3. **Repeat Customers**: Always count distinct `c.customer_unique_id`, never `c.customer_id`.
4. **Delivered Status**: Delivery performance metrics must filter `order_status = 'delivered'` and ensure delivery timestamps are non-null.
