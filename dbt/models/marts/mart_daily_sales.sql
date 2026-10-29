select
    order_date_utc as sales_date_utc,
    count(*) as orders_count,
    count(*) filter (where status = 'cancelled') as cancelled_orders_count,
    sum(order_total_rub) as gross_revenue_rub,
    null::numeric as net_revenue_rub,
    sum(order_total_rub) / nullif(count(*), 0) as average_order_value_rub
from {{ ref('stg_orders') }}
group by order_date_utc
