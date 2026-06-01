-- mrr_trend
-- Monthly MRR series with channel + partner-subtype breakdown.
-- Reads dbt_marts.mart_mrr_monthly_by_channel (Q159 v2.2 methodology).
-- Output cols match _reshape(): mrr_month, customer_type, partner_type, mrr.

select
    mrr_month,
    customer_type,
    partner_subtype as partner_type,
    mrr_booked      as mrr
from dbt_marts.mart_mrr_monthly_by_channel
where mrr_month >= date_trunc('month', current_date) - (interval '1 month' * ({{months_back}} - 1))
  and mrr_month <= date_trunc('month', current_date)
  [[ and partner_subtype = {{partner_subtype}} ]]
order by mrr_month, customer_type, partner_subtype
