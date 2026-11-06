{{ config(
    materialized = 'streaming_table',
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
SELECT customer_segment,
       COUNT(distinct customer_id)           AS customer_count,
       SUM(total_balance) AS total_balance
FROM {{ ref('fct_c360_profile') }}
GROUP BY customer_segment