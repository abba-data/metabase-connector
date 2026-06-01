-- arr_at_risk
-- Licenses whose maintenance ends within horizon_days, broken down by
-- overall / partner / app. Reads dbt_marts.mart_license_renewal_risk.
-- {{group_by}} arrives as text matching the GroupBy enum.
--
-- Output cols match AtRiskBucket: key, arr, license_count.

with at_risk as (
    select *
    from dbt_marts.mart_license_renewal_risk
    where days_to_maintenance_end between 0 and cast({{horizon_days}} as int)
)
select
    case
        when {{group_by}} = 'overall' then 'overall'
        when {{group_by}} = 'partner' then coalesce(partner_uid_canonical, '(unknown partner)')
        when {{group_by}} = 'app'     then coalesce(addon_name, addon_key, '(unknown app)')
    end             as key,
    sum(arr_last_12m) as arr,
    count(*)          as license_count
from at_risk
group by key
order by arr desc nulls last
