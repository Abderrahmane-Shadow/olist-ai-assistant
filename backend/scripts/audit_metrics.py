import sqlalchemy
from app.database import SessionLocal

db = SessionLocal()
def q(sql):
    return db.execute(sqlalchemy.text(sql)).fetchall()

print('TOTAL_ROWS_ORDERS:', q('SELECT COUNT(*) FROM orders')[0][0])
print('DISTINCT_ORDER_ID_ORDERS:', q('SELECT COUNT(DISTINCT order_id) FROM orders')[0][0])
print('DISTINCT_ORDER_ID_ORDER_ITEMS:', q('SELECT COUNT(DISTINCT order_id) FROM order_items')[0][0])
missing_items = q('SELECT COUNT(*) FROM orders WHERE order_id NOT IN (SELECT DISTINCT order_id FROM order_items)')[0][0]
print('ORDERS_WITHOUT_ITEMS:', missing_items)
print('STATUS_OF_ORDERS_WITHOUT_ITEMS:', q('SELECT order_status, COUNT(*) FROM orders WHERE order_id NOT IN (SELECT DISTINCT order_id FROM order_items) GROUP BY order_status ORDER BY COUNT(*) DESC'))
print('DELIVERED_ORDERS_ALL:', q("SELECT COUNT(*) FROM orders WHERE order_status = 'delivered'")[0][0])
print('DELIVERED_WITH_ITEMS:', q("SELECT COUNT(DISTINCT o.order_id) FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.order_status = 'delivered'")[0][0])
print('TOTAL_ORDER_ITEMS:', q('SELECT COUNT(*) FROM order_items')[0][0])
print('TOTAL_REVENUE:', q('SELECT SUM(price) FROM order_items')[0][0])
print('TOTAL_FREIGHT:', q('SELECT SUM(freight_value) FROM order_items')[0][0])
print('TOTAL_CUSTOMER_ROWS:', q('SELECT COUNT(customer_id) FROM customers')[0][0])
print('UNIQUE_CUSTOMERS:', q('SELECT COUNT(DISTINCT customer_unique_id) FROM customers')[0][0])

repeat_sql = """
WITH cust_counts AS (
    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) as order_count
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_unique_id
)
SELECT 
    COUNT(*) as total_customers_with_orders,
    COUNT(CASE WHEN order_count > 1 THEN 1 END) as repeat_customers,
    ROUND(COUNT(CASE WHEN order_count > 1 THEN 1 END) * 100.0 / COUNT(*), 4) as repeat_pct
FROM cust_counts
"""
rep = q(repeat_sql)[0]
print(f'REPEAT_CUSTOMERS: total={rep[0]}, repeat={rep[1]}, pct={rep[2]}%')
db.close()
