# Olist AI Assistant - REST API Reference

The backend is built with FastAPI and runs by default on `http://localhost:8000`. Interactive Swagger UI is available at `/docs` and ReDoc at `/redoc`.

---

## 1. System Health

### `GET /health`
Returns the operational health of the backend, database connection, and AI models.

**Response `200 OK`**:
```json
{
  "status": "healthy",
  "environment": "development",
  "database": "connected",
  "model": "gemini-3.8-flash",
  "timestamp": "2026-11-21T15:50:00Z"
}
```

---

## 2. Conversational Chat Engine

### `POST /api/chat`
Processes natural language analytics questions, executes safe dynamic Text-to-SQL or customer review intelligence, and returns grounded answers, charts, and metric cards.

**Request Body**:
```json
{
  "message": "What were the top 5 product categories by revenue in 2017?",
  "conversation_id": "optional-uuid-string",
  "history": [
    {
      "role": "user",
      "text": "What is the total revenue?"
    },
    {
      "role": "assistant",
      "text": "The total revenue across all orders is R$ 13,591,643.70."
    }
  ]
}
```

**Response `200 OK`**:
```json
{
  "text": "In 2017, the top 5 product categories generated significant revenue led by **bed_bath_table** (R$ 843,210.15) and **health_beauty** (R$ 721,432.80)...",
  "source": "postgresql",
  "intent": "top_categories_by_revenue",
  "metrics": [
    {
      "label": "Top Category",
      "value": "Bed Bath & Table",
      "subtext": "R$ 843,210.15 in 2017"
    }
  ],
  "breakdown": {
    "title": "Top 5 Categories by 2017 Revenue",
    "items": [
      { "label": "bed_bath_table", "value": "R$ 843,210.15", "percentage": 14.2 },
      { "label": "health_beauty", "value": "R$ 721,432.80", "percentage": 12.1 }
    ]
  },
  "chart": {
    "type": "bar",
    "title": "Top 5 Categories by Revenue (2017)",
    "x_key": "category",
    "y_keys": ["revenue"],
    "data": [
      { "category": "bed_bath_table", "revenue": 843210.15 },
      { "category": "health_beauty", "revenue": 721432.80 }
    ],
    "unit": "R$"
  },
  "columns": ["category", "revenue", "order_count"],
  "rows": [
    { "category": "bed_bath_table", "revenue": 843210.15, "order_count": 9412 }
  ],
  "sql_query": "SELECT COALESCE(t.product_category_name_english, p.product_category_name) AS category, ROUND(SUM(oi.price), 2) AS revenue FROM orders o JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id LEFT JOIN product_category_name_translation t ON p.product_category_name = t.product_category_name WHERE EXTRACT(YEAR FROM o.order_purchase_timestamp) = 2017 GROUP BY 1 ORDER BY 2 DESC LIMIT 5;",
  "language": "en"
}
```

---

## 3. Customer Review Intelligence

### `GET /api/reviews/complaints`
Returns the classified breakdown of customer complaints across 8 operational taxonomies, with dynamically calculated percentages.

**Query Parameters**:
- `category` (optional, string): Filter by English product category name.

**Response `200 OK`**:
```json
{
  "total_negative_written_reviews": 10861,
  "categories": [
    {
      "id": "delivery_delay",
      "label": "Delivery Delays & Missing Package",
      "count": 4812,
      "percentage": 44.3,
      "sample_quote": "Meu produto nunca foi entregue, já passou mais de um mês do prazo."
    },
    {
      "id": "damaged_defective",
      "label": "Damaged or Defective Items",
      "count": 1824,
      "percentage": 16.8,
      "sample_quote": "O produto veio com defeito e não liga."
    }
  ]
}
```

### `GET /api/reviews/semantic-search`
Performs Portuguese full-text search over customer reviews using PostgreSQL GIN indexing.

**Query Parameters**:
- `q` (required, string): Search phrase or keywords.
- `limit` (optional, default 10): Max reviews to return.
- `min_score` (optional, int): Filter by review rating (1–5).

**Response `200 OK`**:
```json
{
  "query": "qualidade ruim",
  "total_matches": 1420,
  "reviews": [
    {
      "review_id": "abc123",
      "order_id": "xyz789",
      "score": 1,
      "title": "Péssima qualidade",
      "comment": "Material muito frágil, quebrou no primeiro uso.",
      "creation_date": "2018-03-15",
      "category": "bed_bath_table",
      "customer_state": "SP"
    }
  ]
}
```
