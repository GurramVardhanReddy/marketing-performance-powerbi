import importlib.util
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reconcile", ROOT / "scripts" / "reconcile.py")
rec = importlib.util.module_from_spec(spec)
sys.modules["reconcile"] = rec
spec.loader.exec_module(rec)


def make_gold(tmp: Path) -> Path:
    con = duckdb.connect()
    sql = {
        "fct_campaign_daily": """select * from (values (1, 0, 100, 30, 2.0::double, 3, 2), (1, 1, 50, 10, 1.0::double, 1, 1),
                                 (2, 0, 200, 20, 4.0::double, 2, 0)) t(campaign_id, day_index, impressions,
                                 clicks, cost, conversions, attributed_conversions)""",
        "fct_conversions": """select * from (values (10, 5, 1, 0, 2, 1, 3600, 7200, 1, 1.0, 2.0, false),
                              (11, 6, 2, 1, 1, 0, null, 100, 0, 0.5, 1.0, true))
                              t(conversion_id, user_id, campaign_id, conversion_day_index, n_impressions,
                              n_clicks, seconds_last_click_to_conversion,
                              seconds_first_touch_to_conversion, is_attributed, path_cost,
                              cost_per_order, spans_multiple_campaigns)""",
        "dim_campaign": "select * from (values (1), (2)) t(campaign_id)",
        "dim_date": "select * from (values (0, 0), (1, 0)) t(day_index, week_index)",
        "dim_campaign_tier_history": """select * from (values (1, 'low', true), (2, 'high', true))
                                         t(campaign_id, spend_tier, is_current)""",
    }
    for name, q in sql.items():
        con.execute(f"copy ({q}) to '{tmp / (name + '.parquet')}' (format parquet)")
    return tmp


def test_expected_values(tmp_path):
    exp = rec.expected(make_gold(tmp_path))
    t = exp["totals"]
    assert t["impressions"] == 350 and t["clicks"] == 60
    assert abs(t["ctr"] - 60 / 350) < 1e-12
    assert abs(t["cost_per_attributed_conversion"] - 7.0 / 3) < 1e-12
    assert t["median_hours_last_click_to_conversion"] == 1.0
    assert exp["by_campaign"][1]["cpa_rank"] == 1 and exp["by_campaign"][2]["cpa_rank"] is None
    assert abs(exp["by_day"][1]["rolling_7d_ctr"] - 60 / 350) < 1e-12


def test_compare_flags_mismatch(tmp_path):
    exp = rec.expected(make_gold(tmp_path))
    good = {"totals": {"value": [{f"[{k}]": v for k, v in exp["totals"].items()}]}}
    for section, key in (("by_campaign", "campaign_id"), ("by_day", "day_index"),
                         ("by_week", "week_index"), ("by_tier", "current_spend_tier")):
        good[section] = [{key: k, **{f"[{m}]": v for m, v in ms.items()}}
                         for k, ms in exp[section].items()]
    checks, problems = rec.compare(exp, good)
    assert checks > 0 and problems == []
    good["totals"]["value"][0]["[clicks]"] = 61
    assert any("clicks" in p for p in rec.compare(exp, good)[1])
