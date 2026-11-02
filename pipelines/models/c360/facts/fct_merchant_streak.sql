-- Flink SQL: CEP Pattern 2 — Merchant Streak
--
-- Detects: a customer makes 3 or more consecutive transactions in the same
-- merchant_category (e.g. three FOOD charges in a row) within a 2-hour
-- event-time window. Signals a habit or loyalty opportunity.
--
-- Input:  src_transactions (append, earliest-offset)
-- Output: one row per match — fct_merchant_streak (append, delete-cleanup)
--
-- After editing this query, you MUST run `dbt run --full-refresh` to deploy.

{{ config(
    materialized = 'streaming_table',
    distributed_by={'columns': ['customer_id'], 'buckets': 1},
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
    PARTITION BY customer_id
    ORDER BY `$rowtime`
    MEASURES
        FIRST(A.customer_id)          AS first_customer_id,
        FIRST(A.merchant_category)    AS streak_category,
        FIRST(A.transacted_at)        AS streak_start,
        LAST(A.transacted_at)         AS streak_end,
        COUNT(A.customer_id)          AS streak_length
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (A{3,} B)
    WITHIN INTERVAL '2' HOUR
    DEFINE
        A AS (COUNT(A.customer_id) = 1
              OR A.merchant_category = LAST(A.merchant_category)),
        B AS (B.merchant_category <> LAST(B.merchant_category))
)
