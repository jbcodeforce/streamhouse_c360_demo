
-- After editing this query, you MUST run `dbt run --full-refresh` to deploy the change.
-- Schema-drift detection only checks columns, types, and WITH options — query logic
-- changes are not detected and will be silently skipped on a normal `dbt run`.
{{ config(
    materialized = 'materialized_table',
    with= {
        'changelog.mode': 'upsert',
        'connector': 'confluent',
        'kafka.cleanup-policy': 'delete',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    }
   ) 
}}

select 
    account_id,
    customer_id,
    account_number, 
    account_type, 
    balance,
    to_timestamp_ltz(`opened_date`) as opened_date,
    status    
from {{ source('cdc', 'accounts')}}

where status <> 'SUSPENDED'

