select
    id as stock_id,
    (payload ->> 'product_id')::bigint as product_id,
    payload ->> 'warehouse' as warehouse,
    (payload ->> 'quantity')::integer as quantity,
    (payload ->> 'observed_at')::timestamptz as observed_at,
    ((payload ->> 'observed_at')::timestamptz at time zone 'UTC')::date as observed_date_utc,
    updated_at
from {{ source('marketplace_raw', 'stocks') }}
