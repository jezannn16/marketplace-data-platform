with expected as (
    select i.product_id, i.stock_quantity, i.units_last_30_days,
        coalesce(sum(o.quantity) filter (
            where o.status <> 'cancelled'
                and o.order_date_utc between i.coverage_anchor_date_utc - 29
                    and i.coverage_anchor_date_utc
        ), 0) as expected_units
    from {{ ref('mart_inventory_risk') }} i
    left join {{ ref('stg_orders') }} o on o.product_id = i.product_id
    where i.coverage_anchor_date_utc is not null
    group by i.product_id, i.stock_quantity, i.units_last_30_days, i.coverage_anchor_date_utc
)
select e.product_id
from expected e
join {{ ref('mart_inventory_risk') }} i using (product_id)
where e.units_last_30_days != e.expected_units
    or i.average_daily_units != e.expected_units::numeric / 30
    or (e.expected_units > 0 and abs(i.stock_coverage_days * i.average_daily_units - e.stock_quantity) > 0.01)
