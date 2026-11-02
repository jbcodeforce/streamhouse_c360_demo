-- Flink SQL: CEP Pattern 3 — SMB Spike
--
-- Detects: on the same account belonging to an SMB-segment customer, 3 or more
-- consecutive large DEBIT charges (amount >= 200.00) followed by a CREDIT
-- (reversal) within a 1-hour event-time window. Signals a business expense
-- dispute or anomalous spike worth flagging for the relationship manager.
--
-- The SMB filter is applied via a pre-join CTE with src_customers before the
-- MATCH_RECOGNIZE clause (Confluent Cloud Flink SQL dialect requires the
-- MATCH_RECOGNIZE to apply to a simple table reference or CTE, not an inline
-- join + WHERE).
--
-- Input:  src_transactions + src_customers (append + upsert, earliest-offset)
-- Output: one row per match — fct_smb_spike (append, delete-cleanup)
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

WITH smb_transactions AS (
    SELECT
        t.transaction_id,
        t.account_id,
        t.customer_id,
        t.transaction_type,
        t.amount,
        t.currency,
        t.merchant_name,
        t.merchant_category,
        t.`status`,
        t.transacted_at,
        t.`$rowtime`
    FROM  {{ ref('src_transactions') }} t
    JOIN {{ ref('src_customers') }} c ON t.customer_id = c.customer_id
    WHERE c.customer_segment = 'SMB'
),
smb_append AS (
  SELECT *
  FROM TO_CHANGELOG( input => TABLE smb_transactions)
)

SELECT *
FROM smb_append
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY `$rowtime`
    MEASURES
        FIRST(LARGE_TX.account_id)         AS ltx_account_id,
        FIRST(LARGE_TX.customer_id)        AS customer_id,
        FIRST(LARGE_TX.transacted_at)      AS spike_start,
        LAST(LARGE_TX.transacted_at)       AS spike_end,
        COUNT(LARGE_TX.transacted_at)      AS tx_count,
        SUM(LARGE_TX.amount)               AS spike_total,
        REV.amount                      AS reversal_amount,
        REV.transacted_at               AS reversal_time
    ONE ROW PER MATCH
    AFTER MATCH SKIP TO NEXT ROW
    PATTERN (LARGE_TX{3,} REV)
    WITHIN INTERVAL '1' HOUR
    DEFINE
        LARGE_TX AS transaction_type = 'DEBIT' AND amount >= 200.00,
        REV   AS transaction_type = 'CREDIT'
)
