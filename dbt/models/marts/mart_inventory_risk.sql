with ranked as (
    select *, row_number() over (
        partition by product_id, warehouse
        order by observed_at desc, stock_id desc
    ) as rn
    from {{ ref('stg_stocks') }}
), latest as (
    select product_id, sum(quantity) as stock_quantity,
        min(observed_date_utc) as coverage_anchor_date_utc,
        max(observed_date_utc) as latest_snapshot_date_utc
    from ranked
    where rn = 1
    group by product_id
), demand as (
    select l.product_id,
        coalesce(sum(o.quantity) filter (
            where o.status <> 'cancelled'
                and o.order_date_utc between l.coverage_anchor_date_utc - 29
                    and l.coverage_anchor_date_utc
        ), 0) as units_last_30_days
    from latest l
    left join {{ ref('stg_orders') }} o on o.product_id = l.product_id
    group by l.product_id
)
select
    p.product_id,
    p.sku,
    l.coverage_anchor_date_utc,
    l.latest_snapshot_date_utc,
    l.stock_quantity,
    d.units_last_30_days,
    d.units_last_30_days::numeric / 30 as average_daily_units,
    case when l.coverage_anchor_date_utc = l.latest_snapshot_date_utc
        then l.stock_quantity::numeric / nullif(d.units_last_30_days::numeric / 30, 0)
    end as stock_coverage_days
from {{ ref('stg_products') }} p
left join latest l on p.product_id = l.product_id
left join demand d on p.product_id = d.product_id
