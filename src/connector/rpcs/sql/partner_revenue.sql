-- partner_revenue
-- Net revenue per partner over the date window. Reads int_transactions_enriched
-- so consolidate=False can return raw partner_name and license_types can be a
-- proper subset filter. {{consolidate}} arrives as text 'true' / 'false';
-- {{license_types}} is a comma-joined string of allowed values.
--
-- Output cols match PartnerRevenueRow:
--   partner, canonical_parent, net_revenue, line_count, distinct_license_count.

select
    case when {{consolidate}} = 'true' then partner_uid_canonical else partner_name end as partner,
    partner_uid_canonical                                                               as canonical_parent,
    sum(vendor_amount)                                                                  as net_revenue,
    count(*) filter (where sale_type <> 'Refund')                                       as line_count,
    count(distinct license_uid)                                                         as distinct_license_count
from dbt_intermediate.int_transactions_enriched
where sale_date >= cast({{start_date}} as date)
  and sale_date <= cast({{end_date}} as date)
  and is_partner_attached
  and (license_type is null or license_type = any(string_to_array({{license_types}}, ',')))
group by 1, 2
order by net_revenue desc nulls last
