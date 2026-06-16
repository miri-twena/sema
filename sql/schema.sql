-- SEMA: PostgreSQL schema for the synthetic ecommerce database.
--
-- Run this once to (re)create all tables. Safe to re-run: it drops existing
-- tables first, so re-running gives you a clean slate (data/load_data.py
-- does this automatically before loading fresh data).
--
-- Table order matters because of foreign keys:
--   products, marketing_campaigns, customers      (no dependencies)
--   -> orders                                       (depends on customers, marketing_campaigns)
--   -> order_items                                  (depends on orders, products)
--   -> website_sessions                             (depends on customers, marketing_campaigns, orders)

-- Drop in reverse-dependency order so DROP doesn't fail on foreign keys.
DROP TABLE IF EXISTS website_sessions;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS marketing_campaigns;
DROP TABLE IF EXISTS products;


-- Customers: who buys.
-- "segment" is stored (New / Returning / VIP) and is derived from each
-- customer's actual order history at data-generation time. It's stored
-- here (like a label computed once and saved) rather than recalculated on
-- every query -- the semantic layer can later define a *second*, live
-- version of "segment" computed on the fly, as a teaching example of two
-- ways to express the same business concept.
CREATE TABLE customers (
    customer_id         SERIAL PRIMARY KEY,
    first_name          TEXT NOT NULL,
    last_name           TEXT NOT NULL,
    email               TEXT UNIQUE NOT NULL,
    signup_date         DATE NOT NULL,
    country             TEXT NOT NULL,
    acquisition_channel TEXT NOT NULL,   -- 'Organic', 'Meta', 'Google', 'Email', 'Direct', 'Referral'
    segment             TEXT NOT NULL    -- 'New', 'Returning', 'VIP'
);

-- Products: what's sold.
CREATE TABLE products (
    product_id      SERIAL PRIMARY KEY,
    product_name    TEXT NOT NULL,
    category        TEXT NOT NULL,       -- e.g. 'Electronics', 'Apparel', 'Accessories'
    unit_price      NUMERIC(10,2) NOT NULL,
    unit_cost       NUMERIC(10,2) NOT NULL,
    launch_date     DATE NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- Marketing campaigns: paid/organic acquisition campaigns.
CREATE TABLE marketing_campaigns (
    campaign_id     SERIAL PRIMARY KEY,
    campaign_name   TEXT NOT NULL,
    channel         TEXT NOT NULL,       -- 'Meta', 'Google', 'Email'
    start_date      DATE NOT NULL,
    end_date        DATE,
    budget          NUMERIC(12,2) NOT NULL,
    spend           NUMERIC(12,2) NOT NULL
);

-- Orders: purchase transactions.
-- total_amount is stored (denormalized) so simple "total revenue" queries
-- don't require joining order_items -- but order_items remains the source
-- of truth for product/category-level analysis. The data generator keeps
-- these consistent.
CREATE TABLE orders (
    order_id        SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date      TIMESTAMP NOT NULL,
    status          TEXT NOT NULL,       -- 'completed', 'refunded', 'cancelled'
    traffic_source  TEXT NOT NULL,       -- 'Organic', 'Meta', 'Google', 'Email', 'Direct', 'Referral'
    campaign_id     INTEGER REFERENCES marketing_campaigns(campaign_id),  -- NULL if not campaign-attributed
    discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    shipping_cost   NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_amount    NUMERIC(12,2) NOT NULL
);

-- Order line items.
CREATE TABLE order_items (
    order_item_id   SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    quantity        INTEGER NOT NULL,
    unit_price      NUMERIC(10,2) NOT NULL  -- price at time of sale
);

-- Website sessions: site visits, used for traffic/conversion analysis.
-- order_id is set only for sessions that converted into a purchase;
-- not every order has a matching session (some "orders" represent
-- purchases attributed without a tracked browsing session).
CREATE TABLE website_sessions (
    session_id      SERIAL PRIMARY KEY,
    customer_id     INTEGER REFERENCES customers(customer_id),   -- NULL if anonymous visitor
    session_start   TIMESTAMP NOT NULL,
    traffic_source  TEXT NOT NULL,
    campaign_id     INTEGER REFERENCES marketing_campaigns(campaign_id),
    device_type     TEXT NOT NULL,       -- 'desktop', 'mobile', 'tablet'
    converted       BOOLEAN NOT NULL DEFAULT FALSE,
    order_id        INTEGER REFERENCES orders(order_id)          -- NULL unless converted = TRUE
);

-- Indexes to keep common analytical queries (and the future agent's
-- queries) fast on a dataset this size.
CREATE INDEX idx_orders_order_date ON orders(order_date);
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_campaign_id ON orders(campaign_id);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
CREATE INDEX idx_website_sessions_session_start ON website_sessions(session_start);
CREATE INDEX idx_website_sessions_customer_id ON website_sessions(customer_id);
CREATE INDEX idx_products_category ON products(category);
