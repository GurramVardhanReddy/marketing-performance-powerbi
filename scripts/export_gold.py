"""Export the gold (marts) layer of the marketing data platform's DuckDB warehouse to Parquet.

The warehouse is built by github.com/GurramVardhanReddy/marketing-data-platform: raw (bronze) ->
staging (silver) -> marts (gold). Power BI reads these Parquet files.

    python scripts/export_gold.py --warehouse ~/mdp_data/warehouse.duckdb --out data/gold
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

TABLES = {
    "fct_campaign_daily": "select * from marts.fct_campaign_daily",
    "fct_conversions": "select * from marts.fct_conversions",
    "dim_campaign": "select * from marts.dim_campaign",
    "dim_date": "select * from marts.dim_date",
    "dim_campaign_tier_history": """
        select campaign_id, spend_tier, as_of_day_index, cost_to_date, impressions_to_date,
               dbt_valid_from as valid_from, dbt_valid_to as valid_to,
               dbt_valid_to is null as is_current
        from snapshots.snap_campaign_tier""",
}


def export(warehouse: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse), read_only=True)
    counts = {}
    for name, sql in TABLES.items():
        # HUGEINT sums from dbt are cast to BIGINT so Power BI reads them as whole numbers
        cols = con.execute(f"describe {sql}").fetchall()
        select = ", ".join(f'cast("{c[0]}" as bigint) as "{c[0]}"' if c[1] == "HUGEINT"
                           else f'"{c[0]}"' for c in cols)
        con.execute(f"copy (select {select} from ({sql})) to '{out / (name + '.parquet')}' "
                    "(format parquet)")
        counts[name] = con.execute(f"select count(*) from ({sql})").fetchone()[0]
    (out / "manifest.json").write_text(json.dumps(counts, indent=2))
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/gold"))
    a = ap.parse_args()
    print(export(a.warehouse, a.out))
