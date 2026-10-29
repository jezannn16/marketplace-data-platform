select
    id as order_id,
    (payload ->> 'product_id')::bigint as product_id,
    (payload ->> 'quantity')::integer as quantity,
    (payload ->> 'total_minor')::numeric / 100 as order_total_rub,
    payload ->> 'currency' as currency,
    payload ->> 'status' as status,
    (payload ->> 'created_at')::timestamptz as created_at,
    ((payload ->> 'created_at')::timestamptz at time zone 'UTC')::date as order_date_utc,
    updated_at
from {{ source('marketplace_raw', 'orders') }}
