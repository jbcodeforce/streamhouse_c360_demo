-- Flink SQL: CEP Pattern 1 — Fraud Probe
--
-- Detects: on the same account, a small charge (amount <= 10.00, a card-
-- verification test) immediately followed by one or more large charges
-- (amount >= 500.00) within a 1-hour event-time window.
--
-- Input:  src_transactions (append, earliest-offset)
-- Output: one row per match — fct_fraud_probe (append, delete-cleanup)
--
-- After editing this query, you MUST run `dbt run --full-refresh` to deploy.

{{ config(
    materialized = 'streaming_table',
    distributed_by={'columns': ['account_id'], 'buckets': 1},
    with= {
        'changelog.mode': 'append',
        'kafka.cleanup-policy': 'delete',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    }
) }}

SELECT *
FROM {{ ref('src_transactions') }}
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY `$rowtime`
    MEASURES
        PROBE.account_id        AS probe_account_id,
        PROBE.customer_id       AS customer_id,
        PROBE.transacted_at     AS probe_time,
        PROBE.amount            AS probe_amount,
        LAST(OTHER_TX.transacted_at) AS last_large_time,
        LAST(OTHER_TX.amount)      AS last_large_amount,
        COUNT(OTHER_TX.amount)          AS large_count
    ONE ROW PER MATCH
    AFTER MATCH SKIP TO NEXT ROW
    PATTERN (PROBE LARGE_TX OTHER_TX)
    WITHIN INTERVAL '1' HOUR
    DEFINE
        PROBE AS amount <= 10.00,
        LARGETX AS amount >= 500.00,
        OTHER_TX AS amount >= 499.00 
  )