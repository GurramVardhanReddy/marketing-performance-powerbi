<#
Run the reconciliation DAX queries against the model open in Power BI Desktop and save the
results to reconciliation/dax_results.json. Then run scripts/reconcile.py to compare them with
the same numbers computed independently in SQL (DuckDB) from the gold Parquet files.
#>
$here = Split-Path $MyInvocation.MyCommand.Path
$q = Join-Path $here "query_model.ps1"
$queries = [ordered]@{
  totals = @'
EVALUATE ROW(
 "impressions", [Impressions], "clicks", [Clicks], "cost", [Cost], "conversions", [Conversions],
 "attributed_conversions", [Attributed Conversions], "ctr", [CTR], "attribution_rate", [Attribution Rate],
 "cost_per_attributed_conversion", [Cost per Attributed Conversion], "active_campaigns", [Active Campaigns],
 "top10_campaign_share_attributed", [Top 10% Campaigns Share of Attributed Conversions],
 "journeys", [Conversion Journeys], "median_hours_last_click_to_conversion", [Median Hours Last Click to Conversion],
 "avg_impressions_per_journey", [Avg Impressions per Journey], "multi_campaign_journey_share", [Multi-Campaign Journey Share])
'@
  by_campaign = @'
EVALUATE SUMMARIZECOLUMNS(dim_campaign[campaign_id], "cost", [Cost], "attributed_conversions", [Attributed Conversions],
 "cost_per_attributed_conversion", [Cost per Attributed Conversion], "share_of_cost", [Share of Cost], "cpa_rank", [Campaign CPA Rank])
'@
  by_day = @'
EVALUATE SUMMARIZECOLUMNS(dim_date[day_index], "ctr", [CTR], "rolling_7d_ctr", [Rolling 7-Day CTR], "cumulative_cost", [Cumulative Cost])
'@
  by_week = @'
EVALUATE SUMMARIZECOLUMNS(dim_date[week_index], "conversions", [Conversions], "conversions_wow", [Conversions WoW %])
'@
  by_tier = @'
EVALUATE SUMMARIZECOLUMNS(dim_campaign[current_spend_tier], "cost", [Cost], "attributed_conversions", [Attributed Conversions])
'@
}
$out = [ordered]@{}
foreach ($k in $queries.Keys) { $out[$k] = (& $q -Query $queries[$k]) | ConvertFrom-Json }
$dir = Join-Path (Split-Path $here) "reconciliation"; New-Item -ItemType Directory -Force $dir | Out-Null
$out | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $dir "dax_results.json")
"saved $((Join-Path $dir 'dax_results.json'))"
