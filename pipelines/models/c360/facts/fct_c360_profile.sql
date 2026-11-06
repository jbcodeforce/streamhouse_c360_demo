{{ config(
    materialized = 'materialized_table',
    distributed_by={'columns': ['customer_id'], 'buckets': 1},
   
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
    c.customer_id,
    c.first_name,
    c.last_name,
    c.customer_segment,
    c.customer_since,
    c.gender,
    c.city,
    c.postal_code,
    c.country,
    c.state,
    c.days_since_registration,
    c.age_years,
    c.generation_segment,
    c.per_capita_income,
    c.retirement_age,
    c.years_to_retirement,
    c.income_band,
    c.missing_email_flag,
    c.missing_phone_flag,
    t.account_count,
    t.total_balance,
    t.txn_count,
    t.txn_total
FROM {{ref('dim_customers') }} c 
LEFT JOIN  {{ ref( 'dim_tx_x_account') }} t
ON c.customer_id = t.customer_id