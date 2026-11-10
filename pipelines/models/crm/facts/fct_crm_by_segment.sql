{{ config(
    materialized = 'materialized_table',
    distributed_by={'columns': ['customer_segment'], 'buckets': 1},
   
    with= {
        'changelog.mode': 'upsert',
        'connector': 'confluent',
        'kafka.cleanup-policy': 'compact',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    }
) }}
SELECT 
        COALESCE(customer_segment, 'PRIVATE') as  customer_segment,
       COUNT(distinct customer_id)           AS customer_count,
       SUM(account_balance) AS account_balance
FROM {{ ref('dim_customers') }}
GROUP BY customer_segment