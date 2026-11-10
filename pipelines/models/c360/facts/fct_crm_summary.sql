{{ config(
    materialized = 'materialized_table',
    distributed_by={'columns': ['qscope'], 'buckets': 1},
   
    with= {
        'changelog.mode': 'upsert',
        'connector': 'confluent',
        'kafka.cleanup-policy': 'compact',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    }
) }}


with all_records AS (
  SELECT *, CAST('ALL' AS STRING) AS qscope FROM {{ ref('fct_c360_profile') }}
)
SELECT
  qscope,
  COUNT(distinct customer_id)                      AS total_customers,
  SUM(account_count)                               AS total_accounts,
  SUM(total_balance)                               AS total_balance,
  SUM(txn_count)                                   AS total_transactions,
  SUM(txn_total)                                   AS total_txn_amount,
  AVG(yearly_income)                   AS avg_income,
  SUM(CASE WHEN missing_email_flag=1 THEN 1 ELSE 0 END) AS missing_email,
  SUM(CASE WHEN missing_phone_flag=1 THEN 1 ELSE 0 END) AS missing_phone,
  SUM(CASE WHEN missing_email_flag=0 AND missing_phone_flag=0 THEN 1 ELSE 0 END) AS complete
FROM all_records
GROUP BY qscope