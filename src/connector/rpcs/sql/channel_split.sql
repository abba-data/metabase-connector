-- channel_split
-- Single-row partner vs direct net-revenue split with line counts and distinct
-- license counts. Reads dbt_intermediate.int_transactions_enriched (row-level
-- access needed for distinct-license counts; the bookings mart pre-aggregates
-- them out). license_types accepts a comma-joined string of allowed values;
-- NULL license_type is preserved per channel-analysis methodology.
--
-- Output cols match channel_split._row_to_groups():
--   partner_revenue, partner_lines, partner_distinct_licenses,
--   direct_revenue, direct_lines, direct_distinct_licenses.

select
    sum(vendor_amount) filter (where is_partner_attached)                            as partner_revenue,
    count(*)           filter (where is_partner_attached and sale_type <> 'Refund')  as partner_lines,
    count(distinct license_uid) filter (where is_partner_attached)                   as partner_distinct_licenses,
    sum(vendor_amount) filter (where not is_partner_attached)                        as direct_revenue,
    count(*)           filter (where not is_partner_attached and sale_type <> 'Refund') as direct_lines,
    count(distinct license_uid) filter (where not is_partner_attached)               as direct_distinct_licenses
from dbt_intermediate.int_transactions_enriched
where sale_date >= cast({{start_date}} as date)
  and sale_date <= cast({{end_date}} as date)
  and (license_type is null or license_type = any(string_to_array({{license_types}}, ',')))
