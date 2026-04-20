"""
Souled Meta Ads CPL Dashboard Generator
Reads cached JSON data from Windsor.ai (Meta) and Salesforce,
merges them, computes CPL metrics, and generates a self-contained HTML dashboard.
"""
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
OUTPUT_FILE = os.path.join(BASE_DIR, "dashboard.html")


def load_meta_daily():
    with open(os.path.join(DATA_DIR, "meta_daily.json")) as f:
        data = json.load(f)
    rows = data["result"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    for col in ["spend", "clicks", "link_clicks", "impressions", "cpc", "ctr",
                 "actions_lead", "actions_complete_registration",
                 "cost_per_action_type_lead", "cost_per_action_type_complete_registration"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    # Combine both conversion events: older campaigns used complete_registration, newer use lead
    df["meta_conversions"] = df["actions_complete_registration"] + df["actions_lead"]
    return df


def load_meta_country():
    with open(os.path.join(DATA_DIR, "meta_country.json")) as f:
        data = json.load(f)
    rows = data["result"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    for col in ["spend", "clicks", "impressions", "actions_lead", "actions_complete_registration"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["meta_conversions"] = df["actions_complete_registration"] + df["actions_lead"]
    return df


def load_meta_creative():
    with open(os.path.join(DATA_DIR, "meta_creative.json")) as f:
        data = json.load(f)
    rows = data["result"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    for col in ["spend", "clicks", "link_clicks", "actions_lead", "actions_complete_registration"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["meta_conversions"] = df["actions_complete_registration"] + df["actions_lead"]
    return df


def load_sf_registrations():
    with open(os.path.join(DATA_DIR, "sf_registrations.json")) as f:
        data = json.load(f)
    records = data["result"]["records"]
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["CreatedDate"]).dt.tz_localize(None).dt.normalize()
    df["campaign"] = df["utm_campaign__c"].fillna("Unattributed")
    df["ad_content"] = df["utm_content__c"].fillna("Unknown")
    df["status"] = df["Status__c"]
    df["disqualified"] = df["Disqualified__c"].fillna(False)
    return df


def compute_iso_week(dt):
    return dt.isocalendar()[1]


def aggregate_by_period(meta_df, sf_df, period="W"):
    """Aggregate Meta + SF data by period and compute CPL."""
    if period == "D":
        meta_df["period"] = meta_df["date"].dt.strftime("%Y-%m-%d")
        sf_df["period"] = sf_df["date"].dt.strftime("%Y-%m-%d")
        sort_key = "period"
    elif period == "W":
        meta_df["period"] = meta_df["date"].dt.to_period("W").apply(lambda r: str(r.start_time.date()))
        sf_df["period"] = sf_df["date"].dt.to_period("W").apply(lambda r: str(r.start_time.date()))
        sort_key = "period"
    else:  # Monthly
        meta_df["period"] = meta_df["date"].dt.strftime("%Y-%m")
        sf_df["period"] = sf_df["date"].dt.strftime("%Y-%m")
        sort_key = "period"

    meta_agg = meta_df.groupby("period").agg(
        spend=("spend", "sum"),
        clicks=("clicks", "sum"),
        link_clicks=("link_clicks", "sum"),
        impressions=("impressions", "sum"),
        meta_leads=("meta_conversions", "sum"),
    ).reset_index()

    sf_agg = sf_df.groupby("period").agg(
        sf_leads=("Id", "count"),
        sf_disqualified=("disqualified", "sum"),
    ).reset_index()

    merged = meta_agg.merge(sf_agg, on="period", how="outer").fillna(0)
    merged = merged.sort_values(sort_key)

    merged["cpc"] = (merged["spend"] / merged["clicks"].replace(0, float("nan"))).round(2)
    merged["ctr"] = ((merged["clicks"] / merged["impressions"].replace(0, float("nan"))) * 100).round(2)
    merged["true_cpl"] = (merged["spend"] / merged["sf_leads"].replace(0, float("nan"))).round(2)
    merged["meta_cpl"] = (merged["spend"] / merged["meta_leads"].replace(0, float("nan"))).round(2)
    merged["lead_gap"] = merged["meta_leads"] - merged["sf_leads"]
    merged["lead_gap_pct"] = ((merged["lead_gap"] / merged["meta_leads"].replace(0, float("nan"))) * 100).round(1)
    merged["conv_rate"] = ((merged["sf_leads"] / merged["clicks"].replace(0, float("nan"))) * 100).round(2)

    merged = merged.fillna(0)
    for col in merged.select_dtypes(include=["float64"]).columns:
        merged[col] = merged[col].replace([float("inf"), float("-inf")], 0)

    return merged


def build_campaign_table(meta_df, sf_df):
    meta_camp = meta_df.groupby("campaign").agg(
        spend=("spend", "sum"),
        clicks=("clicks", "sum"),
        link_clicks=("link_clicks", "sum"),
        impressions=("impressions", "sum"),
        meta_leads=("meta_conversions", "sum"),
    ).reset_index()

    sf_camp = sf_df.groupby("campaign").agg(
        sf_leads=("Id", "count"),
    ).reset_index()

    merged = meta_camp.merge(sf_camp, on="campaign", how="outer").fillna(0)
    merged["cpc"] = (merged["spend"] / merged["clicks"].replace(0, float("nan"))).round(2)
    merged["ctr"] = ((merged["clicks"] / merged["impressions"].replace(0, float("nan"))) * 100).round(2)
    merged["true_cpl"] = (merged["spend"] / merged["sf_leads"].replace(0, float("nan"))).round(2)
    merged["conv_rate"] = ((merged["sf_leads"] / merged["clicks"].replace(0, float("nan"))) * 100).round(2)
    merged = merged.fillna(0).replace([float("inf"), float("-inf")], 0)
    merged = merged.sort_values("spend", ascending=False)
    return merged


def build_creative_table(creative_df, sf_df):
    creative_agg = creative_df.groupby(["ad_name", "campaign"]).agg(
        spend=("spend", "sum"),
        clicks=("clicks", "sum"),
        link_clicks=("link_clicks", "sum"),
        meta_leads=("meta_conversions", "sum"),
    ).reset_index()

    sf_content = sf_df.groupby("ad_content").agg(
        sf_leads=("Id", "count"),
    ).reset_index().rename(columns={"ad_content": "ad_name"})

    merged = creative_agg.merge(sf_content, on="ad_name", how="left").fillna(0)
    merged["true_cpl"] = (merged["spend"] / merged["sf_leads"].replace(0, float("nan"))).round(2)
    merged = merged.fillna(0).replace([float("inf"), float("-inf")], 0)
    merged = merged.sort_values("spend", ascending=False)
    return merged


def build_country_table(country_df):
    country_agg = country_df.groupby("country").agg(
        spend=("spend", "sum"),
        clicks=("clicks", "sum"),
        impressions=("impressions", "sum"),
        meta_leads=("meta_conversions", "sum"),
    ).reset_index()
    country_agg["cpc"] = (country_agg["spend"] / country_agg["clicks"].replace(0, float("nan"))).round(2)
    country_agg["meta_cpl"] = (country_agg["spend"] / country_agg["meta_leads"].replace(0, float("nan"))).round(2)
    country_agg = country_agg.fillna(0).replace([float("inf"), float("-inf")], 0)
    country_agg = country_agg.sort_values("spend", ascending=False)
    return country_agg


def build_campaign_daily(meta_df):
    df = meta_df.copy()
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    agg = df.groupby(["date_str", "campaign"]).agg(
        spend=("spend", "sum"),
        clicks=("clicks", "sum"),
        impressions=("impressions", "sum"),
        meta_leads=("meta_conversions", "sum"),
    ).reset_index().rename(columns={"date_str": "date"})
    return agg.sort_values(["date", "campaign"])


def build_country_daily(country_df):
    df = country_df.copy()
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    agg = df.groupby(["date_str", "country"]).agg(
        spend=("spend", "sum"),
        clicks=("clicks", "sum"),
        impressions=("impressions", "sum"),
        meta_leads=("meta_conversions", "sum"),
    ).reset_index().rename(columns={"date_str": "date"})
    return agg.sort_values(["date", "country"])


def build_creative_daily(creative_df):
    df = creative_df.copy()
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    agg = df.groupby(["date_str", "ad_name", "campaign"]).agg(
        spend=("spend", "sum"),
        clicks=("clicks", "sum"),
        meta_leads=("meta_conversions", "sum"),
    ).reset_index().rename(columns={"date_str": "date"})
    return agg.sort_values(["date", "ad_name"])


def build_sf_reg_daily(sf_df):
    result = sf_df[["date", "campaign", "ad_content", "status"]].copy()
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    return result.to_dict("records")


def build_status_funnel(sf_df):
    status_counts = sf_df["status"].value_counts().to_dict()
    total = len(sf_df)
    funnel = {
        "total_registered": total,
        "scheduled": status_counts.get("Scheduled", 0),
        "meeting_with_coach": status_counts.get("Meeting with a Coach", 0),
        "stopped_meeting": status_counts.get("Stopped Meeting with a Coach", 0),
        "never_matched": status_counts.get("Never Matched", 0),
        "matched_new_coach": status_counts.get("Matched with new coach", 0),
        "being_matched": status_counts.get("Being matched with another coach", 0),
    }
    funnel["ever_coached"] = funnel["meeting_with_coach"] + funnel["stopped_meeting"] + funnel["matched_new_coach"]
    funnel["coach_match_rate"] = round(funnel["ever_coached"] / total * 100, 1) if total > 0 else 0
    return funnel


def compute_kpis(meta_df, sf_df):
    total_spend = meta_df["spend"].sum()
    total_clicks = meta_df["clicks"].sum()
    total_impressions = meta_df["impressions"].sum()
    total_meta_leads = meta_df["meta_conversions"].sum()
    total_sf_leads = len(sf_df)
    true_cpl = round(total_spend / total_sf_leads, 2) if total_sf_leads > 0 else 0
    meta_cpl = round(total_spend / total_meta_leads, 2) if total_meta_leads > 0 else 0
    lead_gap_pct = round((total_meta_leads - total_sf_leads) / total_meta_leads * 100, 1) if total_meta_leads > 0 else 0
    cpc = round(total_spend / total_clicks, 2) if total_clicks > 0 else 0
    ctr = round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0

    funnel = build_status_funnel(sf_df)

    return {
        "total_spend": round(total_spend, 2),
        "total_clicks": int(total_clicks),
        "total_impressions": int(total_impressions),
        "total_meta_leads": int(total_meta_leads),
        "total_sf_leads": total_sf_leads,
        "true_cpl": true_cpl,
        "meta_cpl": meta_cpl,
        "lead_gap_pct": lead_gap_pct,
        "cpc": cpc,
        "ctr": ctr,
        "coach_match_rate": funnel["coach_match_rate"],
    }


def df_to_json_records(df):
    """Convert DataFrame to list of dicts, safe for JSON embedding."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def main():
    print("Loading data...")
    meta_daily = load_meta_daily()
    meta_country = load_meta_country()
    meta_creative = load_meta_creative()
    sf = load_sf_registrations()

    date_min = meta_daily["date"].min().strftime("%Y-%m-%d")
    date_max = meta_daily["date"].max().strftime("%Y-%m-%d")
    print(f"Meta data range: {date_min} to {date_max}")
    print(f"SF registrations: {len(sf)}")

    print("Computing aggregations...")
    weekly = aggregate_by_period(meta_daily.copy(), sf.copy(), "W")
    monthly = aggregate_by_period(meta_daily.copy(), sf.copy(), "M")
    daily = aggregate_by_period(meta_daily.copy(), sf.copy(), "D")

    campaign_table = build_campaign_table(meta_daily, sf)
    creative_table = build_creative_table(meta_creative, sf)
    country_table = build_country_table(meta_country)
    status_funnel = build_status_funnel(sf)
    kpis = compute_kpis(meta_daily, sf)
    campaign_daily = build_campaign_daily(meta_daily)
    country_daily = build_country_daily(meta_country)
    creative_daily = build_creative_daily(meta_creative)
    sf_reg_daily = build_sf_reg_daily(sf)

    print("Generating dashboard...")
    dashboard_data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date_min": date_min,
        "date_max": date_max,
        "kpis": kpis,
        "weekly": df_to_json_records(weekly),
        "monthly": df_to_json_records(monthly),
        "daily": df_to_json_records(daily),
        "campaigns": df_to_json_records(campaign_table),
        "creatives": df_to_json_records(creative_table),
        "countries": df_to_json_records(country_table),
        "funnel": status_funnel,
        "campaign_daily": df_to_json_records(campaign_daily),
        "country_daily": df_to_json_records(country_daily),
        "creative_daily": df_to_json_records(creative_daily),
        "sf_reg_daily": sf_reg_daily,
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("dashboard.html.j2")
    html = template.render(data=json.dumps(dashboard_data, default=str))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {OUTPUT_FILE}")
    print(f"KPIs: Spend=${kpis['total_spend']:,.2f} | SF Leads={kpis['total_sf_leads']} | True CPL=${kpis['true_cpl']:.2f} | Coach Match={kpis['coach_match_rate']}%")


if __name__ == "__main__":
    main()
