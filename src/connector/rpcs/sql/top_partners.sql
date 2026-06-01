-- top_partners
-- Ranked partner list by net revenue over the date window. Reads
-- int_transactions_enriched directly so consolidate=False can return raw
-- partner_name (the partner mart only carries the consolidated identity).
-- {{consolidate}} arrives as text 'true' / 'false'.
--
-- Output cols match TopPartnerRow: rank, partner, canonical_parent, net_revenue.

with grouped as (
    select
        case when {{consolidate}} = 'true' then partner_uid_canonical else partner_name end as partner,
        partner_uid_canonical                                                               as canonical_parent,
        sum(vendor_amount)                                                                  as net_revenue
    from dbt_intermediate.int_transactions_enriched
    where sale_date >= cast({{start_date}} as date)
      and sale_date <= cast({{end_date}} as date)
      and is_partner_attached
      and (license_type is null or license_type in ('COMMERCIAL', 'ACADEMIC'))
    group by 1, 2
)
select
    cast(row_number() over (order by net_revenue desc nulls last) as int) as rank,
    partner,
    canonical_parent,
    net_revenue
from grouped
order by net_revenue desc nulls last
limit cast({{limit}} as int)
