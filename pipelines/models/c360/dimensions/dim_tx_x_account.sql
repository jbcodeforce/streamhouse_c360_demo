{{ config(
    materialized = 'materialized_table',
    start_mode='FROM_BEGINNING', 
    distributed_by={'columns': ['customer_id'], 'buckets': 1},
    with= {
        'changelog.mode': 'upsert',
        'kafka.cleanup-policy': 'compact',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    })
}}
SELECT
  c.customer_id, 
  COALESCE(s.account_count, 0) AS account_count,
  COALESCE(s.total_balance, 0) AS total_balance,
  COALESCE(s.txn_count, 0) AS txn_count,
  COALESCE(s.txn_total, 0) AS txn_total,
  s.last_transacted_at
FROM {{ ref('dim_customers') }} c
LEFT JOIN (
  SELECT 
        customer_id, 
        COUNT(distinct account_id) AS account_count, 
        SUM(balance) AS total_balance,
        SUM(txn_count) AS txn_count, 
        SUM(txn_total) AS txn_total, 
        MAX(last_transacted_at) AS last_transacted_at
  FROM {{ ref('dim_account_tx_agg') }}
  GROUP BY customer_id) s 
ON c.customer_id = s.customer_id