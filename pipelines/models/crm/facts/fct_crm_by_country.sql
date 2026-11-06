{{ config(
    materialized = 'streaming_table',
    distributed_by={'columns': ['country'], 'buckets': 1},
   
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
    country,
    COUNT(distinct customer_id)           AS country_count
FROM {{ ref('fct_c360_profile') }}
GROUP BY country