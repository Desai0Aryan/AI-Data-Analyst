-- Fully deterministic seed data (no random()), so evaluation answers never drift.
-- Q4 2025 is deliberately shaped: products 1-5 DECLINE sharply vs Q3 2025,
-- products 6-10 GROW. That gives "biggest revenue decline last quarter" a real answer.

INSERT INTO categories(id, name) VALUES
 (1,'Electronics'),(2,'Home & Kitchen'),(3,'Sports & Outdoors'),(4,'Books'),(5,'Beauty');

INSERT INTO products(id, name, category_id, list_price, cost, discontinued) VALUES
 (1,'Wireless Earbuds',1,79.99,32.00,false),
 (2,'4K Action Camera',1,199.00,95.00,false),
 (3,'Smart Watch',1,249.00,120.00,false),
 (4,'Bluetooth Speaker',1,59.00,24.00,false),
 (5,'Laptop Stand',1,45.00,15.00,false),
 (6,'Portable Charger',1,35.00,12.00,false),
 (7,'Noise-Cancelling Headphones',1,299.00,140.00,false),
 (8,'E-Reader',1,129.00,60.00,false),
 (9,'Webcam HD',1,69.00,28.00,true),
 (10,'Mechanical Keyboard',1,119.00,50.00,false),
 (11,'Air Fryer',2,89.00,38.00,false),
 (12,'Espresso Machine',2,349.00,170.00,false),
 (13,'Robot Vacuum',2,279.00,130.00,false),
 (14,'Cast Iron Skillet',2,39.00,14.00,false),
 (15,'Blender Pro',2,99.00,41.00,false),
 (16,'Memory Foam Pillow',2,49.00,18.00,false),
 (17,'Knife Set',2,129.00,52.00,false),
 (18,'Electric Kettle',2,34.00,13.00,false),
 (19,'Slow Cooker',2,59.00,25.00,true),
 (20,'Toaster Oven',2,109.00,47.00,false),
 (21,'Yoga Mat',3,29.00,9.00,false),
 (22,'Camping Tent',3,189.00,84.00,false),
 (23,'Running Shoes',3,119.00,48.00,false),
 (24,'Insulated Water Bottle',3,27.00,8.00,false),
 (25,'Dumbbell Set',3,149.00,66.00,false),
 (26,'Hiking Backpack',3,99.00,40.00,false),
 (27,'Resistance Bands',3,19.00,5.00,false),
 (28,'Cycling Helmet',3,69.00,28.00,false),
 (29,'Jump Rope',3,15.00,4.00,true),
 (30,'Trekking Poles',3,59.00,23.00,false),
 (31,'Data Engineering Handbook',4,54.00,19.00,false),
 (32,'Cookbook: Weeknight Dinners',4,29.00,10.00,false),
 (33,'Mystery Novel Box Set',4,42.00,15.00,false),
 (34,'Intro to Statistics',4,89.00,35.00,false),
 (35,'Illustrated Atlas',4,49.00,18.00,false),
 (36,'Vitamin C Serum',5,32.00,9.00,false),
 (37,'Hydrating Moisturizer',5,28.00,8.00,false),
 (38,'Sunscreen SPF 50',5,19.00,5.00,false),
 (39,'Hair Dryer',5,89.00,35.00,false),
 (40,'Beard Grooming Kit',5,36.00,12.00,true);

-- 200 customers; every 7th has an unknown signup channel (NULL).
INSERT INTO customers(id, name, email, country, segment, signup_channel, created_at)
SELECT
  i,
  (ARRAY['Ava','Liam','Noah','Emma','Olivia','Mason','Sophia','Lucas','Mia','Ethan',
         'Amelia','Logan','Harper','Elijah','Ella','James','Chloe','Aiden','Grace','Leo'])[1 + (i % 20)]
    || ' ' ||
  (ARRAY['Smith','Johnson','Garcia','Brown','Davis','Martinez','Lopez','Wilson','Anderson','Taylor',
         'Thomas','Moore','Jackson','Martin','Lee','Perez','Thompson','White','Harris','Clark'])[1 + ((i * 7) % 20)],
  'customer' || i || '@example.com',
  (ARRAY['United States','Canada','United Kingdom','Germany','France','Australia','Japan','Brazil'])[1 + (i % 8)],
  (ARRAY['consumer','consumer','consumer','business','enterprise'])[1 + (i % 5)],
  CASE WHEN i % 7 = 0 THEN NULL
       ELSE (ARRAY['organic','paid_search','social','referral','email'])[1 + (i % 5)] END,
  DATE '2023-06-01' + ((i * 37) % 500)
FROM generate_series(1, 200) AS i;

-- 6000 orders spread over 2024-01-01 .. 2025-12-31 (731 days).
-- 5% cancelled, 5% refunded.
INSERT INTO orders(id, customer_id, order_date, status)
SELECT
  i,
  1 + ((i * 31) % 200),
  DATE '2024-01-01' + ((i * 7919) % 731),
  CASE WHEN i % 20 = 0 THEN 'cancelled'
       WHEN i % 20 = 1 THEN 'refunded'
       ELSE 'completed' END
FROM generate_series(1, 6000) AS i;

-- 1-3 line items per order.
-- Q4 2025 shaping: items for products 1-5 are dropped 2 out of 3 times (decline);
-- products 6-10 get a duplicate boost line (growth).
WITH raw_items AS (
  SELECT
    o.id AS order_id,
    o.order_date,
    k,
    1 + ((o.id * k * 17 + k * 5) % 40) AS product_id
  FROM orders o
  CROSS JOIN LATERAL generate_series(1, 1 + (o.id % 3)) AS k
),
shaped AS (
  SELECT * FROM raw_items
  WHERE NOT (
    order_date >= DATE '2025-10-01' AND product_id BETWEEN 1 AND 5 AND (order_id % 3) <> 0
  )
  UNION ALL
  SELECT order_id, order_date, k + 10, product_id
  FROM raw_items
  WHERE order_date >= DATE '2025-10-01' AND product_id BETWEEN 6 AND 10
)
INSERT INTO order_items(id, order_id, product_id, quantity, unit_price, discount)
SELECT
  row_number() OVER (ORDER BY s.order_id, s.k),
  s.order_id,
  s.product_id,
  1 + ((s.order_id * s.k) % 4),
  p.list_price,
  CASE WHEN (s.order_id + s.k) % 5 = 0 THEN 0.10
       WHEN (s.order_id + s.k) % 7 = 0 THEN 0.15
       ELSE NULL END
FROM shaped s
JOIN products p ON p.id = s.product_id;

ANALYZE;
