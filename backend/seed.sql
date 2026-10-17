INSERT INTO cafes (id, name, address, status) VALUES
    (1, 'Cafe A', 'Smith & Sky Cafe A', 'active'),
    (2, 'Cafe B', 'Smith & Sky Cafe B', 'active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, woocommerce_product_id, sku, name, unit_price_minor, currency, low_stock_threshold, active) VALUES
    (1, 1001, 'SS-ESP', 'Espresso Blend', 35000, 'INR', 8, true),
    (2, 1002, 'SS-CRS', 'Butter Croissant', 22000, 'INR', 10, true),
    (3, 1003, 'SS-BRW', 'Cold Brew Bottle', 18000, 'INR', 12, true)
ON CONFLICT (id) DO NOTHING;

-- Passwords are PBKDF2-SHA256 hashes for admin12345 and cafe12345.
-- Replace all seeded accounts before production.
INSERT INTO app_users (id, email, full_name, role, password_hash, active) VALUES
    (1, 'admin@smithandsky.local', 'Smith & Sky Admin', 'admin', 'pbkdf2_sha256$600000$smith-sky-admin$704fc6181f8877cd424537f400a18fdb32fc3be501adfa9a2191169f4a45518b', true),
    (2, 'cafe-a@smithandsky.local', 'Cafe A Staff', 'cafe_staff', 'pbkdf2_sha256$600000$smith-sky-cafe$2782017e9fc62a0281d40a50a451f8c87fd4a764b988d69f378573cfe8382d47', true),
    (3, 'cafe-b@smithandsky.local', 'Cafe B Staff', 'cafe_staff', 'pbkdf2_sha256$600000$smith-sky-cafe$2782017e9fc62a0281d40a50a451f8c87fd4a764b988d69f378573cfe8382d47', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO cafe_user_assignments (user_id, cafe_id, active) VALUES
    (2, 1, true),
    (3, 2, true)
ON CONFLICT (user_id, cafe_id) DO NOTHING;

SELECT setval('cafes_id_seq', GREATEST((SELECT MAX(id) FROM cafes), 1));
SELECT setval('products_id_seq', GREATEST((SELECT MAX(id) FROM products), 1));
SELECT setval('app_users_id_seq', GREATEST((SELECT MAX(id) FROM app_users), 1));
