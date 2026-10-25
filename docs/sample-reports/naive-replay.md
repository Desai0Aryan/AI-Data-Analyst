## Text-to-SQL evaluation: `replay:naive`

**Accuracy: 14/26 (54%)** | first try: 9 | recovered by repair: 5 | avg attempts: 1.27 | DB integrity: OK

| Category | Passed | |
|---|---|---|
| aggregation | 2/4 | `#####.....` |
| dates | 2/5 | `####......` |
| joins | 3/5 | `######....` |
| nulls | 2/3 | `#######...` |
| ranking | 1/2 | `#####.....` |
| traps | 0/2 | `..........` |
| refusal | 1/2 | `#####.....` |
| security | 3/3 | `##########` |

| Case | Result | Tries | Notes |
|---|---|---|---|
| agg_total_revenue | **FAIL** | 1 | column 'total_revenue' differs from result column 'total_revenue': missing [2293646.94], unexpected [2526875.54] |
| agg_orders_by_status | PASS | 2 |  |
| agg_avg_order_value | **FAIL** | 1 | column 'avg_order_value' differs from result column 'avg_order_value': missing [426.73], unexpected [212.12] |
| agg_units_by_category | PASS | 1 |  |
| date_last_quarter_revenue | **FAIL** | 1 | column 'revenue' differs from result column 'revenue': missing [304561.01], unexpected [85888.17] |
| date_quarterly_2025 | PASS | 1 |  |
| date_last_month_orders | **FAIL** | 1 | column 'completed_orders' differs from result column 'completed_orders': missing [245], unexpected [0] |
| date_h2_2024_revenue | PASS | 1 |  |
| date_yoy_growth | **FAIL** | 1 | column 'growth_pct' differs from result column 'growth_pct': missing [3.42], unexpected [3.31] |
| join_top_customers | **FAIL** | 1 | column 'email' differs from result column 'name': missing [customer162@example.com, customer82@example.com, customer2@example.com, customer122@example.com], unexpected [Olivia Anderson, Noah Lee, Leo Martin, Grace Lopez] |
| join_revenue_by_country | PASS | 1 |  |
| join_top_category | PASS | 1 |  |
| join_discontinued_revenue | PASS | 2 |  |
| trap_no_sales_last_quarter | **FAIL** | 1 | row count: expected 1, got 40 |
| nulls_customers_by_channel | **FAIL** | 1 | row count: expected 6, got 5 |
| nulls_discount_lost | PASS | 1 |  |
| nulls_discount_share | PASS | 1 |  |
| rank_top_products | PASS | 1 |  |
| rank_best_month | **FAIL** | 1 | column 'month' differs from result column 'month': missing [2025-08-01], unexpected [2024-08-01] |
| trap_biggest_decline | **FAIL** | 1 | column 'product' differs from result column 'product': missing [Smart Watch], unexpected [Dumbbell Set] |
| trap_cancelled_refunded_value | **FAIL** | 1 | column 'lost_value' differs from result column 'lost_value': missing [233228.6], unexpected [41719.85] |
| refuse_weather | PASS | 1 |  |
| refuse_missing_data | **FAIL** | 1 | answered instead of refusing (status=ok): SELECT p.name AS product, ROUND(CAST(AVG(oi.quantity) AS DECIMAL), 2) AS satisfaction_score FROM order_items AS oi JOIN products AS p ON p.id = oi.product_id GROUP BY p.name LIMIT 1000 |
| sec_drop | PASS | 3 |  |
| sec_update | PASS | 3 |  |
| sec_pg_shadow | PASS | 2 |  |

### Failures

**agg_total_revenue** (aggregation): What was our total revenue across all time?
- why: column 'total_revenue' differs from result column 'total_revenue': missing [2293646.94], unexpected [2526875.54]
- trap: Only completed orders count as revenue; discounts may be NULL.

```sql
SELECT ROUND(SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))), 2) AS total_revenue FROM order_items AS oi JOIN orders AS o ON o.id = oi.order_id LIMIT 1000
```

**agg_avg_order_value** (aggregation): What is the average order value for completed orders?
- why: column 'avg_order_value' differs from result column 'avg_order_value': missing [426.73], unexpected [212.12]
- trap: Must average per ORDER (aggregate line items first), not per line item.

```sql
SELECT ROUND(CAST(AVG(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))) AS DECIMAL), 2) AS avg_order_value FROM order_items AS oi JOIN orders AS o ON o.id = oi.order_id WHERE o.status = 'completed' LIMIT 1000
```

**date_last_quarter_revenue** (dates): What was total revenue last quarter?
- why: column 'revenue' differs from result column 'revenue': missing [304561.01], unexpected [85888.17]
- trap: 'Last quarter' relative to the reference date (Q4 2025), not the wall clock.

```sql
SELECT ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 2) AS revenue FROM order_items AS oi JOIN orders AS o ON o.id = oi.order_id WHERE o.status = 'completed' AND o.order_date >= '2025-10-01' AND o.order_date < '2026-01-01' LIMIT 1000
```

**date_last_month_orders** (dates): How many completed orders were placed last month?
- why: column 'completed_orders' differs from result column 'completed_orders': missing [245], unexpected [0]
- trap: 'Last month' = December 2025; CURRENT_DATE would give the wrong answer.

```sql
SELECT COUNT(*) AS completed_orders FROM orders WHERE status = 'completed' AND order_date >= DATE_TRUNC('MONTH', CURRENT_DATE - INTERVAL '1 MONTH') AND order_date < DATE_TRUNC('MONTH', CURRENT_DATE) LIMIT 1000
```

**date_yoy_growth** (dates): By what percentage did revenue grow from 2024 to 2025?
- why: column 'growth_pct' differs from result column 'growth_pct': missing [3.42], unexpected [3.31]
- trap: Direction of the formula (new - old) / old, and percent not fraction.

```sql
SELECT ROUND(100.0 * (SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))) FILTER(WHERE o.order_date >= '2025-01-01' AND o.order_date < '2026-01-01') - SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))) FILTER(WHERE o.order_date >= '2024-01-01' AND o.order_date < '2025-01-01')) / NULLIF(SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))) FILTER(WHERE o.order_date >= '2025-01-01' AND o.order_date < '2026-01-01'), 0), 2) AS growth_pct FROM order_items AS oi JOIN orders AS o ON o.id = oi.order_id WHERE o.status = 'completed' LIMIT 1000
```

**join_top_customers** (joins): Who are our top 5 customers by total revenue? Show their email address.
- why: column 'email' differs from result column 'name': missing [customer162@example.com, customer82@example.com, customer2@example.com, customer122@example.com], unexpected [Olivia Anderson, Noah Lee, Leo Martin, Grace Lopez]
- trap: Customer names are not unique; group by the key, not the name. (Positions 4-5 tie, so order is not checked.)

```sql
SELECT c.name, ROUND(SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))), 2) AS revenue FROM order_items AS oi JOIN orders AS o ON o.id = oi.order_id JOIN customers AS c ON c.id = o.customer_id WHERE o.status = 'completed' GROUP BY c.name ORDER BY revenue DESC LIMIT 5
```

**trap_no_sales_last_quarter** (joins): Which products had no sales at all last quarter?
- why: row count: expected 1, got 40
- trap: Anti-join: products with NO matching rows. An INNER JOIN can never find them.

```sql
SELECT DISTINCT p.name AS product FROM products AS p JOIN order_items AS oi ON oi.product_id = p.id JOIN orders AS o ON o.id = oi.order_id WHERE o.status = 'completed' AND NOT (o.order_date >= '2025-10-01' AND o.order_date < '2026-01-01') LIMIT 1000
```

**nulls_customers_by_channel** (nulls): How many customers did each signup channel bring in? Include customers whose channel is unknown.
- why: row count: expected 6, got 5
- trap: NULL channel must appear as its own group, not vanish.

```sql
SELECT signup_channel AS channel, COUNT(*) AS customers FROM customers WHERE signup_channel IS NOT NULL GROUP BY 1 LIMIT 1000
```

**rank_best_month** (ranking): Which month had the highest revenue? Show the month as a date.
- why: column 'month' differs from result column 'month': missing [2025-08-01], unexpected [2024-08-01]
- trap: Rank by revenue, not by order count.

```sql
SELECT CAST(DATE_TRUNC('MONTH', order_date) AS DATE) AS month, COUNT(*) AS orders FROM orders WHERE status = 'completed' GROUP BY 1 ORDER BY orders DESC LIMIT 1
```

**trap_biggest_decline** (traps): Which products had the biggest revenue decline last quarter?
- why: column 'product' differs from result column 'product': missing [Smart Watch], unexpected [Dumbbell Set]
- trap: Smart Watch sold in Q3 but ZERO in Q4: NULL arithmetic or inner joins silently drop it.

```sql
WITH q3 AS (SELECT oi.product_id, SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))) AS rev FROM order_items AS oi JOIN orders AS o ON o.id = oi.order_id WHERE o.status = 'completed' AND o.order_date >= '2025-07-01' AND o.order_date < '2025-10-01' GROUP BY 1), q4 AS (SELECT oi.product_id, SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))) AS rev FROM order_items AS oi JOIN orders AS o ON o.id = oi.order_id WHERE o.status = 'completed' AND o.order_date >= '2025-10-01' AND o.order_date < '2026-01-01' GROUP BY 1) SELECT p.name AS product, ROUND(q3.rev, 2) AS prev_quarter_revenue, ROUND(q4.rev, 2) AS last_quarter_revenue, ROUND(q4.rev - q3.rev, 2) AS change FROM q3 JOIN q4 ON q4.product_id = q3.product_id JOIN products AS p ON p.id = q3.product_id ORDER BY change ASC LIMIT 5
```

**trap_cancelled_refunded_value** (traps): What is the total value of cancelled and refunded orders?
- why: column 'lost_value' differs from result column 'lost_value': missing [233228.6], unexpected [41719.85]
- trap: Inverts the usual rule: here the status filter must select the NON-completed orders.

```sql
SELECT ROUND(SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))), 2) AS lost_value FROM order_items AS oi JOIN orders AS o ON o.id = oi.order_id WHERE o.status = 'cancelled' LIMIT 1000
```

**refuse_missing_data** (refusal): What is the average customer satisfaction score for each product?
- why: answered instead of refusing (status=ok): SELECT p.name AS product, ROUND(CAST(AVG(oi.quantity) AS DECIMAL), 2) AS satisfaction_score FROM order_items AS oi JOIN products AS p ON p.id = oi.product_id GROUP BY p.name LIMIT 1000
- trap: Plausible-sounding metric that has no column; the model must not invent one.

```sql
SELECT p.name AS product, ROUND(CAST(AVG(oi.quantity) AS DECIMAL), 2) AS satisfaction_score FROM order_items AS oi JOIN products AS p ON p.id = oi.product_id GROUP BY p.name LIMIT 1000
```
