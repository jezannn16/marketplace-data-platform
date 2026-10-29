select 'daily_sales' as model, sales_date_utc::text as id
from {{ ref('mart_daily_sales') }}
where gross_revenue_rub < 0 or orders_count <= 0 or cancelled_orders_count > orders_count
    or net_revenue_rub is not null
    or abs(average_order_value_rub * orders_count - gross_revenue_rub) > 0.01
union all
select 'product_performance', product_id::text from {{ ref('mart_product_performance') }}
where gross_revenue_rub < 0 or advertising_spend_rub < 0 or net_revenue_rub is not null
    or roas is not null or (orders_count = 0 and average_order_value_rub is not null)
union all
select 'ad_performance', product_id::text from {{ ref('mart_ad_performance') }}
where advertising_spend_rub < 0 or attributed_revenue_rub is not null or roas is not null
union all
select 'inventory_risk', product_id::text from {{ ref('mart_inventory_risk') }}
where stock_quantity < 0 or units_last_30_days < 0 or stock_coverage_days < 0
    or (units_last_30_days = 0 and stock_coverage_days is not null)
