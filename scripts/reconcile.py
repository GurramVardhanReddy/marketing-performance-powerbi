"""Reconcile the Power BI model against SQL.

Every DAX measure in the report is recomputed independently with DuckDB SQL over the same gold
Parquet files, and compared with the values the Power BI engine returned
(reconciliation/dax_results.json, written by scripts/reconcile.ps1). Exit code 1 on a mismatch.

    python scripts/reconcile.py --gold data/gold
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import duckdb

REL_TOL = 1e-9


def expected(gold: Path) -> dict:
    con = duckdb.connect()
    for t in ("fct_campaign_daily", "fct_conversions", "dim_campaign", "dim_date",
              "dim_campaign_tier_history"):
        con.execute(f"create view {t} as select * from read_parquet('{gold / (t + '.parquet')}')")
    one = lambda sql: con.execute(sql).fetchone()
    imp, clk, cost, conv, attr = one("""select sum(impressions), sum(clicks), sum(cost),
        sum(conversions), sum(attributed_conversions) from fct_campaign_daily""")
    per_c = con.execute("""select campaign_id, sum(cost), sum(attributed_conversions)
        from fct_campaign_daily group by 1""").fetchall()
    attr_sorted = sorted((a for _, _, a in per_c if a > 0), reverse=True)
    n_top = math.ceil(len(attr_sorted) * 0.1)
    j = one("""select count(*), median(seconds_last_click_to_conversion) / 3600.0,
        avg(n_impressions), avg(case when spans_multiple_campaigns then 1.0 else 0.0 end)
        from fct_conversions""")
    totals = {"impressions": imp, "clicks": clk, "cost": cost, "conversions": conv,
              "attributed_conversions": attr, "ctr": clk / imp, "attribution_rate": attr / conv,
              "cost_per_attributed_conversion": cost / attr,
              "active_campaigns": one("select count(distinct campaign_id) from fct_campaign_daily "
                                      "where impressions > 0")[0],
              "top10_campaign_share_attributed": sum(attr_sorted[:n_top]) / sum(attr_sorted),
              "journeys": j[0], "median_hours_last_click_to_conversion": j[1],
              "avg_impressions_per_journey": j[2], "multi_campaign_journey_share": j[3]}
    cpa = {c: co / a for c, co, a in per_c if a}
    ranks = {c: r for r, c in enumerate(sorted(cpa, key=cpa.get), start=1)}  # ties unlikely
    by_campaign = {c: {"cost": co, "attributed_conversions": a, "cost_per_attributed_conversion":
                       cpa.get(c), "share_of_cost": co / cost, "cpa_rank": ranks.get(c)}
                   for c, co, a in per_c}
    days = con.execute("""select d.day_index, sum(f.clicks), sum(f.impressions), sum(f.cost)
        from dim_date d left join fct_campaign_daily f using (day_index)
        group by 1 order by 1""").fetchall()
    by_day = {}
    for d, c_, i_, co in days:
        win = [r for r in days if d - 7 < r[0] <= d and r[2]]
        by_day[d] = {"ctr": (c_ / i_) if i_ else None,
                     "rolling_7d_ctr": (sum(r[1] for r in win) / sum(r[2] for r in win))
                     if win else None,
                     "cumulative_cost": sum(r[3] or 0 for r in days if r[0] <= d) or None}
    weeks = dict(con.execute("""select d.week_index, sum(f.conversions) from dim_date d
        left join fct_campaign_daily f using (day_index) group by 1""").fetchall())
    by_week = {w: {"conversions": v, "conversions_wow": ((v - weeks[w - 1]) / weeks[w - 1])
                   if weeks.get(w - 1) and v is not None else None} for w, v in weeks.items()}
    tiers = con.execute("""select h.spend_tier, sum(f.cost), sum(f.attributed_conversions)
        from fct_campaign_daily f join dim_campaign_tier_history h
          on h.campaign_id = f.campaign_id and h.is_current group by 1""").fetchall()
    by_tier = {t: {"cost": c, "attributed_conversions": a} for t, c, a in tiers}
    return {"totals": totals, "by_campaign": by_campaign, "by_day": by_day,
            "by_week": by_week, "by_tier": by_tier}


def close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=1e-9)


def strip(k: str) -> str:
    return k.split("[")[-1].rstrip("]")


def as_rows(x) -> list:
    """Rows from PowerShell JSON: a list, a {"value": [...]} wrapper, or one object."""
    if isinstance(x, dict) and isinstance(x.get("value"), list):  # PowerShell array wrapper
        return x["value"]
    return x if isinstance(x, list) else [x]


def compare(exp: dict, dax: dict) -> tuple[int, list[str]]:
    checks, problems = 0, []
    for k, v in exp["totals"].items():
        got = {strip(kk): vv for kk, vv in as_rows(dax["totals"])[0].items()}[k]
        checks += 1
        if not close(v, got):
            problems.append(f"totals.{k}: sql={v} dax={got}")
    keyed = {"by_campaign": "campaign_id", "by_day": "day_index", "by_week": "week_index",
             "by_tier": "current_spend_tier"}
    for section, key in keyed.items():
        rows = {}
        for r in as_rows(dax[section]):
            r = {strip(k): v for k, v in r.items()}
            rows[r[key]] = r
        if len(rows) != len(exp[section]):
            problems.append(f"{section}: {len(rows)} rows in DAX, {len(exp[section])} in SQL")
        for kval, metrics in exp[section].items():
            r = rows.get(kval, {})
            for m, v in metrics.items():
                checks += 1
                if not close(v, r.get(m)):
                    problems.append(f"{section}[{kval}].{m}: sql={v} dax={r.get(m)}")
    return checks, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, default=Path("data/gold"))
    ap.add_argument("--dax", type=Path, default=Path("reconciliation/dax_results.json"))
    a = ap.parse_args()
    dax = json.loads(a.dax.read_text(encoding="utf-8-sig"))
    checks, problems = compare(expected(a.gold), dax)
    summary = {"checks": checks, "mismatches": len(problems), "examples": problems[:20]}
    Path("reconciliation/summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
