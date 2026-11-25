
{{ config(
    materialized='streaming_table',
    distributed_by= {'columns': ['customer_id'], 'buckets': 2},
    with={
        'changelog.mode': 'upsert',
        'key.format': 'avro-registry',
        'value.format': 'avro-registry',
        'kafka.cleanup-policy': 'compact',
        'kafka.retention.time': '0',
        'kafka.producer.compression.type': 'snappy',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.fields-include': 'all'
    }
) }}
WITH card_account AS (
  select 
    a.account_id, 
    a.customer_id, 
    a.balance as account_balance, 
    a.credit_limit as account_credit_limit,
    c.card_id,
    c.card_number,
    c.card_brand, 
    c.card_type, 
    c.has_chip, 
    c.credit_limit as card_credit_limit
    from {{ ref('src_accounts') }}  as a 
    JOIN LATERAL SNAPSHOT(
        input => TABLE  {{ ref('src_cards') }},
        on_time => DESCRIPTOR(created_at),
        load_completed_idle_timeout => INTERVAL '5' SECONDS
    ) AS c
    ON a.account_id = c.account_id
),
customers AS (
    SELECT *
    FROM TO_CHANGELOG(
            input      => TABLE {{ ref('src_customers') }},
            op         => DESCRIPTOR(op),
            op_mapping => MAP[
                'INSERT',       'c',
                'UPDATE_AFTER', 'u',
                'DELETE',       'd'
            ]
        )
),

customer_coded AS (
   SELECT 
     c.*, 
     TO_TIMESTAMP_LTZ(c.date_of_birth, 'yyyy-MM-dd') AS dob_ts,
     ctry.country_code_alpha3 AS customer_country_alpha3,
     ctry.country_name AS customer_country_name
    FROM customers as c
    LEFT JOIN LATERAL SNAPSHOT(
        input => TABLE {{ ref('country_codes') }},
        on_time => DESCRIPTOR($rowtime),
        load_completed_idle_timeout => INTERVAL '30' SECONDS
    ) AS ctry
    ON c.country = ctry.country_code
)
SELECT 
    u.customer_id,
    u.first_name,
    u.last_name,
    u.date_of_birth,
    YEAR(u.dob_ts) as birth_year,
    MONTH(u.dob_ts)as birth_month,
    u.gender,
    u.registration_date,
    u.customer_segment,
    u.customer_since,
    u.city,
    u.`state`,
    u.postal_code,
    u.country,
    u.customer_country_alpha3,
    u.customer_country_name,
    u.yearly_income,
    u.retirement_age,
    u.credit_score,
    u.event_ts,
    TIMESTAMPDIFF(DAY, u.registration_date, u.event_ts) as days_since_registration,
     CASE
        WHEN TIMESTAMPDIFF(YEAR, u.dob_ts, u.event_ts)  < 25 THEN 'Gen Z'
        WHEN TIMESTAMPDIFF(YEAR, u.dob_ts, u.event_ts)  < 40 THEN 'Millennial'
        WHEN TIMESTAMPDIFF(YEAR, u.dob_ts, u.event_ts) < 55 THEN 'Gen X'
        ELSE 'Boomer+' END AS generation_segment,
    CASE
        WHEN u.retirement_age IS NULL THEN CAST(57 AS INT)
        ELSE CAST(GREATEST(u.retirement_age - TIMESTAMPDIFF(YEAR, u.dob_ts, u.event_ts), 0) AS INT)
        END AS years_to_retirement,
    CASE
        WHEN u.yearly_income IS NULL THEN 'UNKNOWN'
        WHEN u.yearly_income < 70000 THEN 'LOW'
        WHEN u.yearly_income < 120000 THEN 'MIDDLE'
        ELSE 'HIGH' END AS income_band,
    CASE
        WHEN u.email IS NULL
        OR u.email = '' THEN 1
        ELSE 0 END AS missing_email_flag,
     CASE
        WHEN u.phone IS NULL
        OR u.phone = '' THEN 1
        ELSE 0 END AS missing_phone_flag,
    c.account_id, 
    c.account_balance, 
    c.account_credit_limit,
    c.card_id,
    c.card_number,
    c.card_brand, 
    c.card_type, 
    c.has_chip, 
    c.card_credit_limit
FROM customer_coded as u
    LEFT JOIN card_account as c
    ON u.customer_id = c.customer_id
