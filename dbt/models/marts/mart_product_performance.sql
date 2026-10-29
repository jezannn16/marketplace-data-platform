with sales as (
    select
        product_id,
        count(*) as orders_count,
        sum(order_total_rub) as gross_revenue_rub
    from {{ ref('stg_orders') }}
    group by product_id
), ads as (
    select product_id, sum(spend_rub) as advertising_spend_rub
    from {{ ref('stg_advertising') }}
    group by product_id
)
select
    p.product_id,
    p.sku,
    p.product_name,
    p.category,
    coalesce(s.orders_count, 0) as orders_count,
    coalesce(s.gross_revenue_rub, 0::numeric) as gross_revenue_rub,
    null::numeric as net_revenue_rub,
    s.gross_revenue_rub / nullif(s.orders_count, 0) as average_order_value_rub,
    coalesce(a.advertising_spend_rub, 0::numeric) as advertising_spend_rub,
    null::numeric as roas
from {{ ref('stg_products') }} p
left join sales s on p.product_id = s.product_id
left join ads a on p.product_id = a.product_id
