select
    id as advertising_id,
    (payload ->> 'product_id')::bigint as product_id,
    (payload ->> 'campaign_id')::bigint as campaign_id,
    (payload ->> 'date')::date as ad_date,
    (payload ->> 'spend_minor')::numeric / 100 as spend_rub,
    payload ->> 'currency' as currency,
    (payload ->> 'impressions')::integer as impressions,
    (payload ->> 'clicks')::integer as clicks,
    updated_at
from {{ source('marketplace_raw', 'advertising') }}
