-- Crossroads schema. Applied statement by statement on an autocommit connection, because
-- continuous aggregates cannot be created inside a transaction block. Money is NUMERIC(12,2).
-- Do not put a semicolon inside a comment or a string in this file.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS customers (
  id text PRIMARY KEY,
  display_name text NOT NULL,
  first_name text NOT NULL,
  zip text NOT NULL,
  lat double precision NOT NULL,
  lng double precision NOT NULL,
  nessie_customer_id text UNIQUE
);

CREATE TABLE IF NOT EXISTS vehicles (
  customer_id text PRIMARY KEY REFERENCES customers (id),
  year int NOT NULL,
  make text NOT NULL,
  model text NOT NULL,
  trim text NOT NULL,
  vehicle_class text NOT NULL CHECK (vehicle_class IN ('sedan', 'suv', 'truck')),
  original_price numeric(12,2) NOT NULL,
  purchase_date date NOT NULL,
  current_odometer int NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts (
  customer_id text PRIMARY KEY REFERENCES customers (id),
  type text NOT NULL CHECK (type IN ('lease', 'loan')),
  start_date date NOT NULL,
  end_date date NOT NULL,
  term_months int NOT NULL,
  months_left int NOT NULL,
  monthly_payment numeric(12,2) NOT NULL,
  apr numeric(6,3),
  balance numeric(12,2),
  money_factor numeric(8,6),
  cap_cost numeric(12,2),
  residual numeric(12,2),
  mileage_allowance_total int,
  overage_fee_per_mile numeric(6,3)
);

CREATE TABLE IF NOT EXISTS accounts (
  nessie_account_id text PRIMARY KEY,
  customer_id text NOT NULL REFERENCES customers (id),
  kind text NOT NULL CHECK (kind IN ('checking', 'savings')),
  balance numeric(12,2) NOT NULL,
  synced_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (customer_id, kind)
);
-- 'nessie' when read back from the real Capital One Nessie API, 'demo' when from the in-memory fake.
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'demo' CHECK (source IN ('nessie', 'demo'));

CREATE TABLE IF NOT EXISTS bills (
  nessie_bill_id text PRIMARY KEY,
  customer_id text NOT NULL REFERENCES customers (id),
  payee text NOT NULL,
  monthly_amount numeric(12,2) NOT NULL,
  UNIQUE (customer_id, payee)
);

CREATE TABLE IF NOT EXISTS income (
  nessie_deposit_id text PRIMARY KEY,
  customer_id text NOT NULL REFERENCES customers (id),
  deposited_on date NOT NULL,
  monthly_amount numeric(12,2) NOT NULL,
  source text NOT NULL DEFAULT 'Payroll',
  UNIQUE (customer_id, deposited_on)
);

CREATE TABLE IF NOT EXISTS listing_cache (
  make text NOT NULL,
  model text NOT NULL,
  year int NOT NULL,
  zip text NOT NULL,
  low numeric(12,2) NOT NULL,
  median numeric(12,2) NOT NULL,
  high numeric(12,2) NOT NULL,
  n_listings int NOT NULL,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (make, model, year, zip)
);
-- 'serpapi' for a quote read from real Google results through SerpApi, 'demo' for the synthetic stand-in.
ALTER TABLE listing_cache ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'demo' CHECK (source IN ('serpapi', 'demo'));

CREATE TABLE IF NOT EXISTS dealer_cache (
  zip text NOT NULL,
  name text NOT NULL,
  address text NOT NULL,
  hours text,
  rating numeric(3,1),
  lat double precision NOT NULL,
  lng double precision NOT NULL,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (zip, name, address)
);

CREATE TABLE IF NOT EXISTS explanation_cache (
  facts_hash text PRIMARY KEY,
  text text NOT NULL,
  source text NOT NULL CHECK (source IN ('gemini', 'template')),
  verified boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_snapshot (
  customer_id text PRIMARY KEY REFERENCES customers (id),
  computed_at timestamptz NOT NULL DEFAULT now(),
  path text,
  five_year_cost numeric(12,2),
  baseline_cost numeric(12,2),
  retained boolean NOT NULL DEFAULT false,
  revenue numeric(12,2) NOT NULL DEFAULT 0,
  explanation_verified boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS odometer_readings (
  ts timestamptz NOT NULL,
  customer_id text NOT NULL REFERENCES customers (id),
  odometer int NOT NULL,
  PRIMARY KEY (customer_id, ts)
);

CREATE TABLE IF NOT EXISTS payments (
  ts timestamptz NOT NULL,
  customer_id text NOT NULL REFERENCES customers (id),
  amount numeric(12,2) NOT NULL,
  principal numeric(12,2) NOT NULL,
  interest numeric(12,2) NOT NULL,
  PRIMARY KEY (customer_id, ts)
);

CREATE TABLE IF NOT EXISTS transactions (
  ts timestamptz NOT NULL,
  customer_id text NOT NULL REFERENCES customers (id),
  amount numeric(12,2) NOT NULL,
  category text NOT NULL,
  nessie_purchase_id text NOT NULL,
  UNIQUE (nessie_purchase_id, ts)
);

SELECT create_hypertable('odometer_readings', 'ts', if_not_exists => TRUE);

SELECT create_hypertable('payments', 'ts', if_not_exists => TRUE);

SELECT create_hypertable('transactions', 'ts', if_not_exists => TRUE);

CREATE MATERIALIZED VIEW IF NOT EXISTS monthly_miles
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT customer_id, time_bucket('1 month', ts) AS month, max(odometer) AS odometer
FROM odometer_readings
GROUP BY customer_id, time_bucket('1 month', ts)
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS monthly_payments
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT customer_id, time_bucket('1 month', ts) AS month,
       sum(amount) AS amount, sum(principal) AS principal, sum(interest) AS interest
FROM payments
GROUP BY customer_id, time_bucket('1 month', ts)
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS monthly_spend
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT customer_id, time_bucket('1 month', ts) AS month, category, sum(amount) AS amount
FROM transactions
GROUP BY customer_id, time_bucket('1 month', ts), category
WITH NO DATA;

-- Tiger Data compression: chunks older than 30 days are compressed in the background, one customer's
-- readings together (segment by customer, order by time). The continuous aggregates above keep serving
-- the trend charts, and the app reads compressed and uncompressed chunks the same way.
ALTER TABLE odometer_readings SET (
  timescaledb.compress, timescaledb.compress_segmentby = 'customer_id', timescaledb.compress_orderby = 'ts');
ALTER TABLE payments SET (
  timescaledb.compress, timescaledb.compress_segmentby = 'customer_id', timescaledb.compress_orderby = 'ts');
ALTER TABLE transactions SET (
  timescaledb.compress, timescaledb.compress_segmentby = 'customer_id', timescaledb.compress_orderby = 'ts');

SELECT add_compression_policy('odometer_readings', INTERVAL '30 days', if_not_exists => TRUE);

SELECT add_compression_policy('payments', INTERVAL '30 days', if_not_exists => TRUE);

SELECT add_compression_policy('transactions', INTERVAL '30 days', if_not_exists => TRUE);
