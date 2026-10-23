-- E-commerce demo schema. Comments are read by the app and fed to the LLM,
-- so they double as documentation for text-to-SQL.

CREATE TABLE categories (
    id   integer PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE products (
    id           integer PRIMARY KEY,
    name         text NOT NULL,
    category_id  integer NOT NULL REFERENCES categories(id),
    list_price   numeric(10,2) NOT NULL,
    cost         numeric(10,2) NOT NULL,
    discontinued boolean NOT NULL DEFAULT false
);

CREATE TABLE customers (
    id             integer PRIMARY KEY,
    name           text NOT NULL,
    email          text NOT NULL UNIQUE,
    country        text NOT NULL,
    segment        text NOT NULL,
    signup_channel text,
    created_at     date NOT NULL
);

CREATE TABLE orders (
    id          integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES customers(id),
    order_date  date NOT NULL,
    status      text NOT NULL
);

CREATE TABLE order_items (
    id         integer PRIMARY KEY,
    order_id   integer NOT NULL REFERENCES orders(id),
    product_id integer NOT NULL REFERENCES products(id),
    quantity   integer NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    discount   numeric(4,2)
);

CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);

COMMENT ON TABLE categories  IS 'Product categories.';
COMMENT ON TABLE products    IS 'Catalog of products sold.';
COMMENT ON TABLE customers   IS 'Registered customers.';
COMMENT ON TABLE orders      IS 'One row per customer order. Dates span 2024-01-01 to 2025-12-31.';
COMMENT ON TABLE order_items IS 'Line items of an order. Revenue = quantity * unit_price * (1 - COALESCE(discount, 0)).';

COMMENT ON COLUMN products.list_price    IS 'Current catalog price; orders use order_items.unit_price instead.';
COMMENT ON COLUMN products.discontinued  IS 'True if the product is no longer sold.';
COMMENT ON COLUMN customers.segment      IS 'Customer segment: consumer, business or enterprise.';
COMMENT ON COLUMN customers.signup_channel IS 'Acquisition channel. NULL when unknown.';
COMMENT ON COLUMN orders.status          IS 'completed, cancelled or refunded. Only completed orders count as revenue.';
COMMENT ON COLUMN order_items.unit_price IS 'Price actually charged per unit at order time.';
COMMENT ON COLUMN order_items.discount   IS 'Fractional discount (0.10 = 10%). NULL means no discount.';
