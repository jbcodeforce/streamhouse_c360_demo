{{ config(
    materialized = 'materialized_table',
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
    COALESCE(country,'US') as country,
    COUNT(distinct customer_id)           AS country_count
FROM {{ ref('dim_customers') }}
GROUP BY country