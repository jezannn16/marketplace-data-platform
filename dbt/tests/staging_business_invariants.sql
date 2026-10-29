select 'orders' as source_name, order_id as id
from {{ ref('stg_orders') }}
where quantity <= 0 or order_total_rub < 0
union all
select 'products', product_id from {{ ref('stg_products') }} where price_rub < 0
union all
select 'stocks', stock_id from {{ ref('stg_stocks') }} where quantity < 0
union all
select 'advertising', advertising_id from {{ ref('stg_advertising') }}
where spend_rub < 0 or clicks < 0 or impressions < 0 or clicks > impressions
