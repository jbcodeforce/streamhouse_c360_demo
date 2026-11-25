
-- After editing this query, you MUST run `dbt run --full-refresh` to deploy the change.
-- Schema-drift detection only checks columns, types, and WITH options — query logic
-- changes are not detected and will be silently skipped on a normal `dbt run`.
{{ config(
    materialized = 'streaming_table',
    distributed_by={'columns': ['transaction_id'], 'buckets': 1},
    with= {
        'changelog.mode': 'upsert',
        'kafka.cleanup-policy': 'delete',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    }
) }}
-- Transaction dimension has all the columns populated: for example account_id may come from card 
-- Reference-data enrichment uses snapshot lateral joins: each reference table
-- (seeds `currency_codes`, `country_codes`, and customers) is read once, up to
-- its current end, then joined to every streaming transaction. The seeds must be
-- loaded first (`dbt seed`). Country comes from the customer, as transactions
-- only carry a currency: transaction -> customer.country -> country_codes.
WITH all_tx AS (
    SELECT
        transaction_id,
        COALESCE(c.account_id,t.account_id) as account_id,
        customer_id,
        t.card_id,
        CASE WHEN t.card_id is null THEN CONCAT('XACCT_', transaction_type)
        ELSE CONCAT('CARD_', transaction_type)
        END as transaction_type,
        amount,
        currency,
        currency_code_numeric,
        currency_name,
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
        CAST(transacted_at AS DATE) as transaction_date
    FROM {{ ref('src_transactions_v2') }} as t
    LEFT JOIN {{ ref('src_cards') }} as c
    ON t.card_id = c.card_id
),
relevant_tx AS (
    SELECT *
    FROM TO_CHANGELOG(
            input      => TABLE all_tx,
            op         => DESCRIPTOR(op),
            op_mapping => MAP[
                'INSERT',       'c',
                'UPDATE_AFTER', 'u',
                'DELETE',       'd'
            ]
        )
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
