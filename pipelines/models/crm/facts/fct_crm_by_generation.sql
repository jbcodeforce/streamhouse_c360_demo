{{ config(
    materialized = 'materialized_table',
    distributed_by={'columns': ['generation_segment'], 'buckets': 1},
   
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
    COALESCE(generation_segment, 'Millennial') as generation_segment,
    COUNT(distinct customer_id)           AS generation_count
FROM {{ ref('dim_customers') }}
GROUP BY generation_segment