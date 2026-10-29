with orders as (
    select coalesce(sum(order_total_rub), 0) as amount, count(*) as quantity
    from {{ ref('stg_orders') }}
), sales as (
    select coalesce(sum(gross_revenue_rub), 0) as amount, coalesce(sum(orders_count), 0) as quantity
    from {{ ref('mart_daily_sales') }}
), product_sales as (
    select coalesce(sum(gross_revenue_rub), 0) as amount, coalesce(sum(orders_count), 0) as quantity
    from {{ ref('mart_product_performance') }}
), source_ads as (
    select coalesce(sum(spend_rub), 0) as amount from {{ ref('stg_advertising') }}
), mart_ads as (
    select coalesce(sum(advertising_spend_rub), 0) as amount from {{ ref('mart_ad_performance') }}
)
select 'sales_totals' as discrepancy from orders, sales, product_sales
where orders.amount != sales.amount or orders.quantity != sales.quantity
    or orders.amount != product_sales.amount or orders.quantity != product_sales.quantity
union all
select 'ad_spend' from source_ads, mart_ads where source_ads.amount != mart_ads.amount
