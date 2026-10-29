select ad_date, product_id, campaign_id
from {{ ref('mart_ad_performance') }}
group by ad_date, product_id, campaign_id
having count(*) > 1
