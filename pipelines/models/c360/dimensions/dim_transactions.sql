
-- After editing this query, you MUST run `dbt run --full-refresh` to deploy the change.
-- Schema-drift detection only checks columns, types, and WITH options — query logic
-- changes are not detected and will be silently skipped on a normal `dbt run`.
{{ config(
    materialized = 'materialized_table',
    distributed_by={'columns': ['transaction_id'], 'buckets': 1},
    with= {
        'changelog.mode': 'append',
        'kafka.cleanup-policy': 'delete',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    }
) }}
-- Reference-data enrichment uses snapshot lateral joins: each reference table
-- (seeds `currency_codes`, `country_codes`, and customers) is read once, up to
-- its current end, then joined to every streaming transaction. The seeds must be
-- loaded first (`dbt seed`). Country comes from the customer, as transactions
-- only carry a currency: transaction -> customer.country -> country_codes.
WITH relevant_tx AS (
    SELECT
        *,
        CAST(transacted_at AS DATE) as transaction_date
    FROM {{ ref('src_transactions') }}
),
tx_currency AS (
    SELECT
        t.*,
        cur.currency_code_numeric,
        cur.currency_name
    FROM relevant_tx AS t
    LEFT JOIN LATERAL SNAPSHOT(
        input => TABLE {{ ref('currency_codes') }},
        on_time => DESCRIPTOR($rowtime),
        load_completed_idle_timeout => INTERVAL '30' SECONDS
    ) AS cur
    ON t.currency = cur.currency_code
),
tx_customer AS (
    SELECT
        t.*,
        cust.country AS customer_country
    FROM tx_currency AS t
    LEFT JOIN LATERAL SNAPSHOT(
        input => TABLE {{ ref('src_customers') }},
        on_time => DESCRIPTOR($rowtime),
        load_completed_idle_timeout => INTERVAL '30' SECONDS
    ) AS cust
    ON t.customer_id = cust.customer_id
),
enriched_tx AS (
    SELECT
        t.*,
        ctry.country_code_alpha3 AS customer_country_alpha3,
        ctry.country_name AS customer_country_name
    FROM tx_customer AS t
    LEFT JOIN LATERAL SNAPSHOT(
        input => TABLE {{ ref('country_codes') }},
        on_time => DESCRIPTOR($rowtime),
        load_completed_idle_timeout => INTERVAL '30' SECONDS
    ) AS ctry
    ON t.customer_country = ctry.country_code
)
SELECT
  transaction_id,
  account_id,
  customer_id,
  card_id,
  transaction_type,
  amount,
  currency,
  currency_code_numeric,
  currency_name,
  customer_country,
  customer_country_alpha3,
  customer_country_name,
  comments, 
  merchant_name,
  merchant_category,
  use_chip,
  merchant_city,
  merchant_state,
  merchant_zip,
  channel, 
  `status`, 
  transacted_at,
  CAST(transaction_date AS DATE) as transaction_date_only,
  HOUR(transaction_date) as transaction_hour,
  DAYOFWEEK(transaction_date) as day_of_week,
  MONTH(transaction_date) as transaction_month,
  QUARTER(transaction_date) as transaction_quarter,
  YEAR(transaction_date) as transaction_year,
  CASE 
        WHEN amount < 200 THEN 'Small'
        WHEN amount < 500 THEN 'Medium'
        WHEN amount < 1500 THEN 'Large'
        ELSE 'XLarge'
    END as order_size_category
FROM enriched_tx
