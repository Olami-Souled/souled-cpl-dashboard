"""
meta_direct.py — Direct Meta Marketing API (Graph API) client for the CPL dashboard.

Drop-in replacement for the Windsor.ai Facebook connector. `fetch()` mirrors the
old `_windsor_fetch(fields, date_from, date_to)` signature and returns records using
the SAME field names Windsor produced (date, campaign, spend, clicks, link_clicks,
impressions, cpc, ctr, actions_lead, actions_complete_registration,
cost_per_action_type_lead, cost_per_action_type_complete_registration, country,
ad_name, adset_name) — so the rest of refresh_dashboard.py needs no changes.

Auth: FACEBOOK_ADS_TOKEN (long-lived System User token, ads_read).
Account: FACEBOOK_AD_ACCOUNT_ID (defaults to act_548376353109705).

Meta shape notes:
  - Per-day rows come from time_increment=1; the day is `date_start`.
  - Lead / registration COUNTS live in the `actions` array; their COSTS live in
    `cost_per_action_type`. Each is a list of {"action_type": ..., "value": ...}.
  - `country` is a breakdown, not a field.
  - Level is inferred from the requested fields (ad > adset > campaign).
"""
import json
import os
import time

import requests

GRAPH_VERSION = "v25.0"
META_TIMEOUT = 120
META_RETRIES = 5
PAGE_LIMIT = 500
ASYNC_POLL_SECS = 6
ASYNC_MAX_POLLS = 100  # ~10 min ceiling
_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Windsor field -> the action array + action_type to read it from.
_ACTION_MAP = {
    "actions_lead": ("actions", "lead"),
    "actions_complete_registration": ("actions", "complete_registration"),
    "cost_per_action_type_lead": ("cost_per_action_type", "lead"),
    "cost_per_action_type_complete_registration": ("cost_per_action_type", "complete_registration"),
}
# Windsor field -> Meta top-level insights field (only where names differ / need requesting).
_SCALAR_MAP = {
    "campaign": "campaign_name",
    "adset_name": "adset_name",
    "ad_name": "ad_name",
    "spend": "spend",
    "clicks": "clicks",
    "link_clicks": "inline_link_clicks",
    "impressions": "impressions",
    "cpc": "cpc",
    "ctr": "ctr",
}


def _infer_level(fields):
    if "ad_name" in fields:
        return "ad"
    if "adset_name" in fields:
        return "adset"
    return "campaign"


def _meta_fields_for(fields):
    """Translate requested Windsor fields into the Meta `fields=` list."""
    meta = set()
    for f in fields:
        if f in _SCALAR_MAP:
            meta.add(_SCALAR_MAP[f])
        elif f in _ACTION_MAP:
            meta.add(_ACTION_MAP[f][0])  # "actions" or "cost_per_action_type"
        # "date" is free via time_increment=1; "country" is a breakdown
    return sorted(meta)


def _extract_action(row, arr_field, action_type):
    """Pull a single action_type value out of a Meta actions/cost array; 0 if absent."""
    for entry in row.get(arr_field, []) or []:
        if entry.get("action_type") == action_type:
            return entry.get("value", 0)
    return 0


def _to_windsor_row(row, fields):
    """Reshape one Meta insights row into Windsor's flat field names."""
    out = {}
    for f in fields:
        if f == "date":
            out["date"] = row.get("date_start")
        elif f == "country":
            out["country"] = row.get("country")
        elif f in _ACTION_MAP:
            arr_field, action_type = _ACTION_MAP[f]
            out[f] = _extract_action(row, arr_field, action_type)
        elif f in _SCALAR_MAP:
            out[f] = row.get(_SCALAR_MAP[f])
    return out


def _request_with_retry(url, params):
    """GET with backoff on Meta throttling / transient 5xx. Returns parsed JSON."""
    last_err = None
    for attempt in range(1, META_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=(30, META_TIMEOUT))
            if resp.status_code == 200:
                return resp.json()
            # Meta throttle (code 4 / subcode 1504022) and rate/server errors -> retry.
            retriable = resp.status_code in (429, 500, 502, 503)
            try:
                err = resp.json().get("error", {})
                # Retry Meta throttling (code 4/17/32/613, subcode 1504022) and the
                # transient "service temporarily unavailable" family (code 1/2,
                # subcode 1504044), plus anything Meta flags is_transient.
                if (err.get("code") in (1, 2, 4, 17, 32, 613)
                        or err.get("error_subcode") in (1504022, 1504044)
                        or err.get("is_transient")):
                    retriable = True
            except ValueError:
                err = {"message": resp.text[:200]}
            if not retriable:
                raise RuntimeError(f"Meta API {resp.status_code}: {err}")
            last_err = RuntimeError(f"Meta API {resp.status_code}: {err}")
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
        if attempt < META_RETRIES:
            backoff = 10 * (2 ** (attempt - 1))  # 10, 20, 40, 80s
            print(f"  Meta fetch attempt {attempt} throttled/failed ({last_err}); retry in {backoff}s...")
            time.sleep(backoff)
    raise last_err


def _collect(url, params, fields):
    """Page through an insights result (sync GET or async report edge)."""
    records = []
    payload = _request_with_retry(url, params)
    while True:
        for row in payload.get("data", []):
            records.append(_to_windsor_row(row, fields))
        next_url = (payload.get("paging") or {}).get("next")
        if not next_url:
            break
        # paging.next is a fully-formed URL (token embedded); call it directly.
        payload = _request_with_retry(next_url, None)
    return records


def _fetch_async(account, params, fields, token):
    """Heavy breakdowns (ad-level, wide ranges) exceed the sync endpoint's limits;
    Meta's async report jobs are the supported path. POST to create the run, poll
    until complete, then page the report_run_id/insights edge."""
    run = None
    for attempt in range(1, META_RETRIES + 1):
        r = requests.post(f"{_BASE}/{account}/insights", data=params, timeout=(30, META_TIMEOUT))
        if r.status_code == 200:
            run = r.json()
            break
        if attempt < META_RETRIES:
            time.sleep(10 * (2 ** (attempt - 1)))
    if not run or "report_run_id" not in run:
        raise RuntimeError(f"async job creation failed: {run}")
    run_id = run["report_run_id"]

    for _ in range(ASYNC_MAX_POLLS):
        time.sleep(ASYNC_POLL_SECS)
        st = requests.get(f"{_BASE}/{run_id}", params={"access_token": token},
                          timeout=(30, META_TIMEOUT)).json()
        status = st.get("async_status")
        if status == "Job Completed":
            break
        if status in ("Job Failed", "Job Skipped"):
            raise RuntimeError(f"async job {status} ({st.get('async_percent_completion')}%)")
    else:
        raise RuntimeError("async job did not complete within poll ceiling")

    return _collect(f"{_BASE}/{run_id}/insights", {"limit": PAGE_LIMIT, "access_token": token}, fields)


def fetch(fields, date_from, date_to, account_id=None):
    """Windsor-compatible fetch: return list of records with Windsor field names.

    Tries the fast sync endpoint first; on failure (heavy ad-level / wide-range
    pulls that Meta refuses synchronously) falls back to an async report job."""
    token = os.environ["FACEBOOK_ADS_TOKEN"]
    account = account_id or os.environ.get("FACEBOOK_AD_ACCOUNT_ID", "act_548376353109705")
    if not account.startswith("act_"):
        account = f"act_{account}"

    params = {
        "level": _infer_level(fields),
        "fields": ",".join(_meta_fields_for(fields)),
        "time_range": json.dumps({"since": date_from, "until": date_to}),
        "time_increment": 1,
        "limit": PAGE_LIMIT,
        "access_token": token,
    }
    if "country" in fields:
        params["breakdowns"] = "country"

    url = f"{_BASE}/{account}/insights"
    try:
        return _collect(url, params, fields)
    except Exception as e:
        print(f"  sync fetch failed ({e}); falling back to async report job...")
        return _fetch_async(account, params, fields, token)
