{{ config(
    materialized = 'streaming_table',
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
    gender,
    COUNT(distinct customer_id)           AS gender_count
FROM {{ ref('fct_c360_profile') }}
GROUP BY gender