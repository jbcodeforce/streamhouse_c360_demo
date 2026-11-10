
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
WITH relevant_tx AS (
    SELECT
        *,
        CAST(transacted_at AS DATE) as transaction_date
    FROM {{ ref('src_transactions') }}
)
SELECT
  transaction_id, 
  account_id, 
  customer_id, 
  card_id,
  transaction_type, 
  amount, 
  currency,
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
FROM relevant_tx
