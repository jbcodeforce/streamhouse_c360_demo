{{ config(
    materialized = 'streaming_table',
    with= {
        'changelog.mode': 'upsert',
        'connector': 'confluent',
        'kafka.cleanup-policy': 'delete',
        'scan.bounded.mode': 'unbounded',
        'scan.startup.mode': 'earliest-offset',
        'value.format': 'avro-registry'
    },
    pre_hook=[
        "ALTER TABLE {{ source('cdc', 'cards') }} SET ( 'changelog.mode' = 'append')",
    ]
   ) 
}}
select
    card_id,
    account_id,
    card_number,
    card_brand,
    card_type,
    has_chip,
    credit_limit,
    TO_TIMESTAMP_LTZ(created_at, 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS''Z''') as created_at
from {{ source('cdc', 'cards')}}
where account_id IS NOT NULL