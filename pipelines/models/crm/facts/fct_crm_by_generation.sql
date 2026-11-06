{{ config(
    materialized = 'streaming_table',
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
    generation_segment,
    COUNT(distinct customer_id)           AS generation_count
FROM {{ ref('fct_c360_profile') }}
GROUP BY generation_segment