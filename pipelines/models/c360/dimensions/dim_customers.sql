
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

SELECT 
    customer_id,
    first_name,
    last_name,
    date_of_birth,
    gender,
    registration_date,
    customer_segment,
    customer_since,
    city,
    `state`,
    postal_code,
    country,
    per_capita_income,
    retirement_age,
    event_ts,
    TIMESTAMPDIFF(YEAR, date_of_birth, event_ts) birth_year,
    TIMESTAMPDIFF(MONTH, date_of_birth, event_ts) birth_month,
    TIMESTAMPDIFF(DAY, registration_date, event_ts) as days_since_registration,
     CASE
        WHEN TIMESTAMPDIFF(YEAR, date_of_birth, event_ts)  < 25 THEN 'Gen Z'
        WHEN TIMESTAMPDIFF(YEAR, date_of_birth, event_ts)  < 40 THEN 'Millennial'
        WHEN TIMESTAMPDIFF(YEAR, date_of_birth, event_ts) < 55 THEN 'Gen X'
        ELSE 'Boomer+' END AS generation_segment,
    CASE
        WHEN retirement_age IS NULL THEN CAST(NULL AS INT)
        ELSE CAST(GREATEST(retirement_age - TIMESTAMPDIFF(YEAR, date_of_birth, event_ts), 0) AS INT)
        END AS years_to_retirement,
    CASE
        WHEN per_capita_income IS NULL THEN 'UNKNOWN'
        WHEN per_capita_income < 70000 THEN 'LOW'
        WHEN per_capita_income < 120000 THEN 'MIDDLE'
        ELSE 'HIGH' END AS income_band,
    CASE
        WHEN email IS NULL
        OR email = '' THEN 1
        ELSE 0 END AS missing_email_flag,
     CASE
        WHEN phone IS NULL
        OR phone = '' THEN 1
        ELSE 0 END AS missing_phone_flag
FROM {{ ref('src_customers') }}