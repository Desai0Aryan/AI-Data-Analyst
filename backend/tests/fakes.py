class FakeLLM:
    """Scripted LLM: returns canned replies in order and records every call it receives."""
    model = "fake-model"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[tuple[str, list[dict]]] = []

    def complete(self, system, messages):
        self.calls.append((system, [dict(m) for m in messages]))   # snapshot (list is mutated later)
        if not self.replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        return self.replies.pop(0)


def sql_block(sql: str) -> str:
    return f"```sql\n{sql}\n```"


REVENUE = "oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))"

# The correct answer to "Which products had the biggest revenue decline last quarter?"
GOLDEN_DECLINE_SQL = f"""
SELECT p.name AS product,
  ROUND(COALESCE(SUM({REVENUE}) FILTER (WHERE o.order_date >= '2025-07-01' AND o.order_date < '2025-10-01'), 0), 2) AS prev_quarter_revenue,
  ROUND(COALESCE(SUM({REVENUE}) FILTER (WHERE o.order_date >= '2025-10-01' AND o.order_date < '2026-01-01'), 0), 2) AS last_quarter_revenue,
  ROUND(COALESCE(SUM({REVENUE}) FILTER (WHERE o.order_date >= '2025-10-01' AND o.order_date < '2026-01-01'), 0)
      - COALESCE(SUM({REVENUE}) FILTER (WHERE o.order_date >= '2025-07-01' AND o.order_date < '2025-10-01'), 0), 2) AS change
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
WHERE o.status = 'completed'
GROUP BY p.name
ORDER BY change ASC
LIMIT 5
"""
