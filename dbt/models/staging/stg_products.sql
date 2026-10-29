select
    id as product_id,
    payload ->> 'sku' as sku,
    payload ->> 'name' as product_name,
    payload ->> 'category' as category,
    (payload ->> 'price_minor')::numeric / 100 as price_rub,
    payload ->> 'currency' as currency,
    updated_at
from {{ source('marketplace_raw', 'products') }}
