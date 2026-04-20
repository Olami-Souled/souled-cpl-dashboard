# Daily Dashboard Refresh — Souled CPL

You are a scheduled agent. Your job is to refresh the Souled Meta Ads CPL Dashboard with today's latest data and push the result to GitHub (Railway auto-deploys).

## Context

- **Repo:** `Olami-Souled/souled-cpl-dashboard` (you are already cloned into it)
- **Dashboard:** https://souled-cpl-dashboard-production.up.railway.app
- **Data sources:**
  - Meta ad performance — via the **Windsor.ai** MCP connector (Facebook connector, account `548376353109705`)
  - Salesforce registrations — via the **Souled-Salesforce** MCP connector (tool: `salesforce_query`)

Do not stop to ask questions. Execute end-to-end.

## Steps

### 1. Fetch Meta daily campaign data
Call the Windsor.ai MCP `get_data` tool:
- `connector`: `"facebook"`
- `accounts`: `["548376353109705"]`
- `fields`: `["date","campaign","spend","clicks","link_clicks","impressions","cpc","ctr","actions_lead","actions_complete_registration","cost_per_action_type_lead","cost_per_action_type_complete_registration"]`
- `date_from`: 180 days before today
- `date_to`: yesterday (YYYY-MM-DD — do NOT include today, partial data skews trends)

Wrap the returned array as `{"result": [...]}` and save to `data/meta_daily.json`.

If the tool response is too large and gets spilled to a temp file, read it back and save into `data/meta_daily.json` in the same `{"result": [...]}` shape.

### 2. Fetch Meta country data
Same connector/account. Fields: `["date","campaign","country","spend","clicks","impressions","actions_lead","actions_complete_registration"]`. Save to `data/meta_country.json` as `{"result": [...]}`.

### 3. Fetch Meta creative data
Same connector/account. Fields: `["date","campaign","ad_name","spend","clicks","link_clicks","actions_lead","actions_complete_registration"]`. Save to `data/meta_creative.json` as `{"result": [...]}`.

### 4. Fetch Salesforce registrations
Call the Souled-Salesforce MCP `salesforce_query` tool with this SOQL:

```sql
SELECT Id, CreatedDate, Status__c, utm_source__c, utm_campaign__c, utm_content__c, utm_medium__c, Referral_Type__c, Referral_Category__c, Disqualified__c, Disqualified_Reason__c
FROM Registration__c
WHERE Program__c = 'a2F5f000000yRpfEAE'
  AND Student__r.Test_Old__c = false
  AND (NOT Student__r.Name LIKE '%test%')
  AND Referral_Type__c = 'Paid'
  AND CreatedDate >= 2025-10-01T00:00:00Z
ORDER BY CreatedDate DESC
```

Save the response to `data/sf_registrations.json`. The loader accepts either `{"records": [...]}` or a raw list or the CLI wrapper `{"result": {"records": [...]}}` — whichever the MCP returns is fine.

### 5. Regenerate the dashboard
```bash
pip install -q pandas jinja2
python refresh_dashboard.py
```

Expected output: confirms "Dashboard generated" and prints KPIs line.

### 6. Commit and push
```bash
git add -A
git commit -m "Daily data refresh [auto]"
git push
```

Railway will auto-deploy from the push in ~1–2 min.

### 7. Summary block
At the end, output exactly this block so the run log is easy to scan:

```
DASHBOARD REFRESH SUMMARY
Meta spend (last 6mo): $XX,XXX.XX
SF registrations: X,XXX
True CPL: $XX.XX
Coach match rate: XX.X%
Pushed: <commit sha>
```

## Hard rules

- **Never include today's date** in the Meta data fetch — partial-day numbers skew trends and CPL. `date_to` should be yesterday.
- **SF Leads count = paid-acquisition Souled registrations only.** Filter: `Program__c = 'a2F5f000000yRpfEAE' AND Referral_Type__c = 'Paid' AND Student__r.Test_Old__c = false AND Student__r.Name NOT LIKE '%test%'`. `Referral_Type__c` is manually maintained by the Souled team — trust it over `utm_source__c` (which can be missing or wrong). Organic/referral/word-of-mouth registrations are explicitly excluded from this dashboard.
- **Never use the `sf` CLI.** You are running on Anthropic infrastructure, not Yair's laptop. SF access is only via the Souled-Salesforce MCP.
- If any step fails, commit what you have with a message explaining the failure, then exit.
