 SELECT 
    customer_id,
    first_name,
    last_name,
    email,
    phone,
    date_of_birth,
    gender,
    created_at as registration_date,
    segment as customer_segment,
    address,
    city,
    state,
    postal_code,
    country,
    `$rowtime` as event_ts, -- propagate src ts to downstream
    ROW_NUMBER() OVER (
        PARTITION BY customer_id 
        ORDER BY `$rowtime` DESC
    ) AS row_num
FROM `cdc.public.customers`