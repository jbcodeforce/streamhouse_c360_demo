
-- After editing this query, you MUST run `dbt run --full-refresh` to deploy the change.
-- Schema-drift detection only checks columns, types, and WITH options — query logic
-- changes are not detected and will be silently skipped on a normal `dbt run`.
{{ config(
    materialized = 'streaming_table',
    distributed_by={'columns': ['transaction_id'], 'buckets': 1},
    with= {
        'changelog.mode': 'append',
        'kafka.cleanup-policy': 'delete',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    },
    pre_hook=[
        "ALTER TABLE {{ source('cdc', 'transactions') }} SET ( 'changelog.mode' = 'append')"
    ]
) }}
WITH relevant_tx AS (
    SELECT
        transaction_id, 
        account_id, 
        customer_id, 
        transaction_type, 
        amount, 
        currency,
        description as comments, 
        merchant_name,
        merchant_category,
        channel, 
        `status`, 
        CAST(REPLACE(REPLACE(transacted_at, 'T', ' '), 'Z', '') AS TIMESTAMP_LTZ(6)) AS transacted_at,
        card_id,
        use_chip,
        merchant_city,
        merchant_state,
        zip as merchant_zip
    FROM  {{ source('cdc', 'transactions') }}
       WHERE status <> 'CANCELLED'
       AND merchant_state IS NOT NULL
       AND zip IS NOT NULL
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
)
SELECT
  transaction_id, 
  account_id, 
  customer_id, 
  transaction_type, 
  amount, 
  currency,
  comments, 
  merchant_name,
  merchant_category,
  channel,
  `status`, 
  transacted_at,
  card_id,
  use_chip,
  merchant_city,
  merchant_state,
  merchant_zip,
  currency_code_numeric,
  currency_name
FROM tx_currency
