"""Generate the Power BI report definition (PBIR) for MarketingPerformance.pbip.

Pages and visuals are declared here and written as PBIR JSON, so the report is reviewable text
and rebuilds identically. Run after changing a visual:  python scripts/build_report.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "MarketingPerformance.Report"
S = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def measure(name: str) -> dict:
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "Key Measures"}},
                                  "Property": name}},
            "queryRef": f"Key Measures.{name}", "nativeQueryRef": name}


def column(table: str, name: str) -> dict:
    return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": table}},
                                 "Property": name}},
            "queryRef": f"{table}.{name}", "nativeQueryRef": name}


def visual(name, vtype, x, y, w, h, roles: dict, title: str | None = None) -> dict:
    v = {"visualType": vtype,
         "query": {"queryState": {r: {"projections": p} for r, p in roles.items()}},
         "drillFilterOtherVisuals": True}
    if title:
        v["visualContainerObjects"] = {"title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}]}
    return {"$schema": f"{S}/visualContainer/1.0.0/schema.json", "name": name,
            "position": {"x": x, "y": y, "z": 0, "width": w, "height": h}, "visual": v}


def card(name, x, y, m):
    return visual(name, "card", x, y, 200, 110, {"Values": [measure(m)]})


PAGES = {
    "overview": ("Overview", [
        card("kpi_impressions", 20, 20, "Impressions"),
        card("kpi_ctr", 235, 20, "CTR"),
        card("kpi_conversions", 450, 20, "Conversions"),
        card("kpi_attr_rate", 665, 20, "Attribution Rate"),
        card("kpi_cpa", 880, 20, "Cost per Attributed Conversion"),
        card("kpi_campaigns", 1095, 20, "Active Campaigns"),
        visual("trend_ctr", "lineChart", 20, 150, 620, 270,
               {"Category": [column("dim_date", "day_index")],
                "Y": [measure("CTR"), measure("Rolling 7-Day CTR")]}, "Daily CTR and rolling 7-day CTR"),
        visual("trend_cost", "lineChart", 660, 150, 600, 270,
               {"Category": [column("dim_date", "day_index")], "Y": [measure("Cumulative Cost")]},
               "Cumulative cost"),
        visual("conv_week", "clusteredColumnChart", 20, 440, 620, 260,
               {"Category": [column("dim_date", "week_index")], "Y": [measure("Conversions")]},
               "Conversions by week"),
        visual("tier_mix", "clusteredBarChart", 660, 440, 600, 260,
               {"Category": [column("dim_campaign", "current_spend_tier")],
                "Y": [measure("Cost"), measure("Attributed Conversions")]},
               "Cost and attributed conversions by current spend tier"),
    ]),
    "campaigns": ("Campaigns", [
        visual("tier_slicer", "slicer", 20, 20, 240, 200,
               {"Values": [column("dim_campaign", "current_spend_tier")]}, "Spend tier"),
        card("kpi_pareto", 20, 240, "Top 10% Campaigns Share of Attributed Conversions"),
        card("kpi_active", 20, 370, "Active Campaigns"),
        visual("leaderboard", "tableEx", 280, 20, 980, 680,
               {"Values": [column("dim_campaign", "campaign_label"),
                           column("dim_campaign", "current_spend_tier"),
                           measure("Impressions"), measure("CTR"), measure("Cost"),
                           measure("Share of Cost"), measure("Attributed Conversions"),
                           measure("Cost per Attributed Conversion"),
                           measure("Campaign CPA Rank")]},
               "Campaign leaderboard"),
    ]),
    "journeys": ("Conversion journeys", [
        card("kpi_journeys", 20, 20, "Conversion Journeys"),
        card("kpi_median_hours", 235, 20, "Median Hours Last Click to Conversion"),
        card("kpi_impr_per_journey", 450, 20, "Avg Impressions per Journey"),
        card("kpi_multi", 665, 20, "Multi-Campaign Journey Share"),
        visual("journeys_by_day", "lineChart", 20, 150, 1240, 270,
               {"Category": [column("dim_date", "day_index")],
                "Y": [measure("Conversion Journeys")]}, "Conversions by conversion day"),
        visual("journey_table", "tableEx", 20, 440, 1240, 260,
               {"Values": [column("dim_campaign", "campaign_label"),
                           measure("Conversion Journeys"),
                           measure("Avg Impressions per Journey"),
                           measure("Median Hours Last Click to Conversion"),
                           measure("Multi-Campaign Journey Share")]},
               "Journeys by campaign"),
    ]),
}


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def build() -> None:
    d = REPORT / "definition"
    if d.exists():
        shutil.rmtree(d)
    write(REPORT / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                   "definitionProperties/1.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": "../MarketingPerformance.SemanticModel"}}})
    write(d / "version.json", {"$schema": f"{S}/versionMetadata/1.0.0/schema.json",
                               "version": "2.0.0"})
    write(d / "report.json", {"$schema": f"{S}/report/1.0.0/schema.json",
                              "themeCollection": {}, "layoutOptimization": "None"})
    write(d / "pages" / "pages.json", {"$schema": f"{S}/pagesMetadata/1.0.0/schema.json",
                                       "pageOrder": list(PAGES), "activePageName": "overview"})
    for pid, (title, visuals) in PAGES.items():
        write(d / "pages" / pid / "page.json", {
            "$schema": f"{S}/page/1.0.0/schema.json", "name": pid, "displayName": title,
            "displayOption": "FitToPage", "height": 720, "width": 1280})
        for v in visuals:
            write(d / "pages" / pid / "visuals" / v["name"] / "visual.json", v)


if __name__ == "__main__":
    build()
    print("report written:", sum(1 for _ in (REPORT / "definition").rglob("visual.json")), "visuals")
