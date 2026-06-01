-- revenue_comparison
-- Period-over-period net-revenue compared along channel / sale_type / partner.
-- Reads int_transactions_enriched. License scope COMMERCIAL/ACADEMIC/NULL per
-- the channel-analysis methodology. {{dimension}} arrives as text matching the
-- Dimension enum.
--
-- Output cols match _reshape(): period (a/b), dimension_key, revenue.

with base as (
    select sale_date, vendor_amount, customer_type, sale_type, partner_uid_canonical
    from dbt_intermediate.int_transactions_enriched
    where (license_type is null or license_type in ('COMMERCIAL', 'ACADEMIC'))
),
combined as (
    select 'a' as period, sale_date, vendor_amount, customer_type, sale_type, partner_uid_canonical
    from base
    where sale_date >= cast({{period_a_start}} as date)
      and sale_date <= cast({{period_a_end}} as date)
    union all
    select 'b' as period, sale_date, vendor_amount, customer_type, sale_type, partner_uid_canonical
    from base
    where sale_date >= cast({{period_b_start}} as date)
      and sale_date <= cast({{period_b_end}} as date)
)
select
    period,
    case
        when {{dimension}} = 'channel'   then customer_type
        when {{dimension}} = 'sale_type' then sale_type
        when {{dimension}} = 'partner'   then partner_uid_canonical
    end                as dimension_key,
    sum(vendor_amount) as revenue
from combined
group by period, dimension_key
order by period, dimension_key
