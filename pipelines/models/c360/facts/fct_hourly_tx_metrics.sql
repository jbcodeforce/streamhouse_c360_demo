{{ config(
    materialized = 'materialized_table',
    distributed_by={'columns': ['account_id', 'window_start', 'window_end'], 'buckets': 1},
    with= {
        'changelog.mode': 'append',
        'kafka.cleanup-policy': 'delete',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    }
) }}


with completed_tx as (
  select * from {{ ref('dim_transactions') }} where status = 'COMPLETED'
)
SELECT
    account_id,
    window_start,
    window_end,
    '1_HOUR' AS window_type,
    COUNT(*) AS tx_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS avg_amount,
    MIN(amount) AS min_amount,
    MAX(amount) AS max_amount
FROM TABLE(
    TUMBLE(TABLE completed_tx, DESCRIPTOR(transacted_at), INTERVAL '1' HOUR)
)
GROUP BY account_id, window_start, window_end;