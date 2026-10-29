select
    ad_date,
    product_id,
    campaign_id,
    sum(spend_rub) as advertising_spend_rub,
    sum(impressions) as impressions,
    sum(clicks) as clicks,
    null::numeric as attributed_revenue_rub,
    null::numeric as roas
from {{ ref('stg_advertising') }}
group by ad_date, product_id, campaign_id
