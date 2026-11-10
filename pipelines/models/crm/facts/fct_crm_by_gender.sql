{{ config(
    materialized = 'materialized_table',
    distributed_by={'columns': ['gender'], 'buckets': 1},
   
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
    COALESCE(gender,'M') as gender,
    COUNT(distinct customer_id)           AS gender_count
FROM {{ ref('dim_customers') }}
GROUP BY gender