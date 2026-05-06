# Handoff — Add A/B Test Section to Souled CPL Dashboard

**For:** Claude Code, opened in this repo (`souled-cpl-dashboard`)
**Owner:** Yair Spolter (`yspolter@olami.org`)
**Date written:** 2026-05-05
**Goal:** Add a self-contained section to the existing CPL dashboard that shows the registration-form A/B test results so Yair can monitor it alongside CPL on a single screen.

---

## Read these first (3 minutes)

In this order:

1. `instructions/DAILY_REFRESH.md` in this repo — current daily-refresh prompt; you'll likely add a step to it.
2. `refresh_dashboard.py` and `templates/dashboard.html.j2` in this repo — current architecture (Python + pandas + Jinja2 + Chart.js + Bootstrap).
3. `Olami-Souled/knowledge` wiki, specifically:
   - `wiki/concepts/cpl-dashboard.md` — architecture and layout conventions for this dashboard
   - `wiki/concepts/souled-ab-daily-report.md` — sibling daily-email A/B report; gives you the data-segmentation pattern
   - `wiki/sources/form-arm-ab-tracking-2026-04-30.md` — the `Form_Arm__c` field implementation
   - `wiki/concepts/registration.md` — `Form_Arm__c` and `Referral_Type__c` field semantics
   - `wiki/connections/paid-acquisition-filter.md` — canonical paid filter

You don't need to read everything in detail; skim until you feel oriented, then come back for specifics.

---

## What to build

Add a new section to `dashboard.html` between the existing KPI strip and the existing CPL/Spend charts, titled **"Form A/B Test"**. The section should contain:

1. **A small KPI strip with three cards** — three numbers, side-by-side:
   - **New form** — paid registrations to date since A/B start (Apr 29, 2026)
   - **Old form** — paid registrations to date since A/B start
   - **Lift** — `(new / old) × 100%` formatted as a multiplier (e.g., "9× new / old"). If old is zero, show "n/a (old = 0)".

2. **A daily stacked-bar chart**, one bar per day from 2026-04-29 forward, with two stacked segments per bar (`new` in green, `old` in gray). X-axis is the date; Y-axis is the count of paid registrations created that day. Use Chart.js (already in the dashboard).

3. **A small reference line and label** marking the A/B start date (Apr 29, 2026) so the chart's left edge is anchored.

4. **A two-line caption below the chart**:
   - Line 1: "A/B test: legacy Visualforce form vs new WordPress form. Splitter at souled.olami.org/join-now/ routes 50/50."
   - Line 2: A dynamic last-updated timestamp matching the dashboard's existing footer convention.

That's the whole spec for v1. Don't over-build; this is a tracking widget, not a full report. The full daily email already exists (see `souled-ab-daily-report` wiki concept) so anything elaborate goes there, not here.

---

## Data source

Add a new SOQL query to `instructions/DAILY_REFRESH.md` (or extend the existing Souled-registrations query) that pulls the fields needed to segment by arm. The minimal field set:

```sql
SELECT
  Id,
  CreatedDate,
  Form_Arm__c
FROM Registration__c
WHERE Program__c = 'a2F5f000000yRpfEAE'
  AND Student__r.Test_Old__c = false
  AND (NOT Student__r.Name LIKE '%test%')
  AND Referral_Type__c = 'Paid'
  AND CreatedDate >= 2026-04-29T00:00:00Z
ORDER BY CreatedDate ASC
```

**Critical filters:**

- `Program__c = 'a2F5f000000yRpfEAE'` — Souled program only
- `Student__r.Test_Old__c = false AND NOT Student__r.Name LIKE '%test%'` — exclude test contacts (this is non-negotiable; Yair has been bitten by test-data contamination repeatedly)
- `Referral_Type__c = 'Paid'` — paid acquisition only (per `paid-acquisition-filter` wiki page)
- `CreatedDate >= 2026-04-29T00:00:00Z` — A/B test start date

**Arm mapping** (per `form-arm-ab-tracking-2026-04-30` source):

- `Form_Arm__c = 'new'` → New WP form (Claude-built, at `souled.olami.org/join-test/`)
- `Form_Arm__c IS NULL` → Legacy Visualforce form (`online.olami.org/joinsouled`). The India team owns the legacy form's Apex code and has not yet added `Form_Arm__c = 'old'`. Treat null as "old" until they ship it.

**Save the query result** as `data/sf_ab_test.json` to match the existing convention (`data/sf_registrations.json`, `data/meta_daily.json`).

---

## Implementation steps

### 1. Update the daily-refresh prompt

In `instructions/DAILY_REFRESH.md`, add a step after the existing Souled-registrations SOQL pull:

> Pull A/B test segmentation: run the SOQL above (Form_Arm__c view) and save the result to `data/sf_ab_test.json`. Use the same `souled-sf-mcp` client. The daily refresh runs at 05:27 UTC; this query is small (~few hundred rows max), no rate-limiting concern.

Don't replicate the entire SOQL in DAILY_REFRESH.md — reference this handoff or a new dedicated file in `instructions/` like `AB_TEST_QUERY.md` if you want it self-contained.

### 2. Update `refresh_dashboard.py`

Add a function `load_ab_test_data()` that:

- Reads `data/sf_ab_test.json`
- Parses CreatedDate to dates (timezone-aware, then convert to America/New_York to match dashboard convention)
- Buckets by date and `Form_Arm__c`, treating null as "old"
- Returns a pandas DataFrame ready for the Jinja2 template:
  - One row per `(date, arm)` pair
  - Columns: `date`, `arm` (`'new'` | `'old'`), `count`
- Also returns the totals as a dict: `{'new': N, 'old': M, 'lift_multiplier': N/M or None}`

Pass both the daily DataFrame and the totals dict into the Jinja2 context as `ab_daily` and `ab_totals`.

Match the existing pattern: see how `sf_registrations.json` is consumed; this is structurally identical.

### 3. Update `templates/dashboard.html.j2`

Insert the new section between the existing KPI strip and the first chart row. Use the dashboard's existing Bootstrap grid (`row` / `col-md-*`). Match the visual style (card classes, font sizes, color scheme).

For the chart, use a Chart.js stacked bar chart. Reference an existing chart in the file for the script-block pattern (look for `new Chart(...)`); add a new `<canvas id="ab-test-chart">` and a script block at the bottom of the body that builds the chart from the Jinja2-injected data.

Color convention (match `cpl-dashboard.md` color thresholds where possible):

- New arm bars: green (`#10b981` or the green already used for healthy CPL)
- Old arm bars: gray (`#6b7280` or a neutral gray)
- Reference line / label for Apr 29 start: light blue dashed line

### 4. Test locally

Run `python refresh_dashboard.py` after dropping a hand-edited `data/sf_ab_test.json` with realistic test data into `data/`. Verify:

- KPI cards render
- Chart renders with the correct date range
- Chart is responsive on mobile (Bootstrap container)
- The page still loads without JS errors
- Existing dashboard sections still work

### 5. Deploy

Standard Railway deploy via push to main. The next 05:27 UTC refresh will pull live data and the A/B section will populate.

---

## Edge cases to handle

- **Zero data on a given day** — chart should show that day with zero-height bars, not skip the date.
- **Test-data contamination** — already handled by the SOQL filter, but defensively: if you see a record with `Student__r.Name` containing "Test" or "Canary" or "Smoke" that somehow slipped through, log a warning. The wiki's `paid-acquisition-filter` filter is the line of defense.
- **Future cutover scenario** — if Yair switches the splitter to 100% new form (a likely near-term decision based on early A/B results), the chart should keep working — old-arm bars just go to zero. Don't hardcode the splitter ratio anywhere.
- **null vs 'old' for the legacy form arm** — keep the convention `null === 'old'` in the rendering layer; do not write `'old'` to Salesforce yourself. Just display "Old form" / "Legacy form" in the chart legend regardless of how the data is stored.

---

## Acceptance criteria

- The new section appears between KPI strip and first chart row on `https://souled-cpl-dashboard-production.up.railway.app` after deploy
- Three KPI cards show correct totals from `data/sf_ab_test.json`
- Stacked-bar daily chart renders cleanly from Apr 29 forward
- Daily refresh at 05:27 UTC populates fresh data without errors (check Railway trigger logs the next morning)
- Mobile-friendly (test in DevTools mobile viewport)
- No regressions in existing CPL / spend / leads sections

---

## Reference IDs (copy-paste for convenience)

| Thing | ID |
|---|---|
| Souled program (Salesforce) | `a2F5f000000yRpfEAE` |
| A/B test start date | `2026-04-29` |
| Canonical SF report (for reference) | `00ORi00000MFahdMAD` ("Paid signnups by form a/b test") |
| Splitter URL | `https://souled.olami.org/join-now/` |
| New form URL | `https://souled.olami.org/join-test/` |
| Legacy form URL | `https://online.olami.org/joinsouled` |
| Souled SF MCP | `https://souled-sf-mcp-production.up.railway.app/mcp?k=...` |
| Dashboard repo | `Olami-Souled/souled-cpl-dashboard` |
| Dashboard live URL | `https://souled-cpl-dashboard-production.up.railway.app` |
| Daily refresh trigger | `trig_01TrCMckUou6jhS31Lyf4w9A` (5:27 AM UTC) |

---

## What's NOT in scope

- Conversion rate per arm. The denominator (sessions per arm) requires GA4 + Clarity correlation that's noisy and not yet reliable. Leave this for a later iteration.
- Statistical significance testing. The sample is too small currently (single-digit conversions per arm) for any defensible test; adding a p-value would imply more rigor than the data supports.
- A/B-test cutover automation. Yair will decide when to cut over manually; the dashboard's job is to show the data, not act on it.
- Backfilling pre-Apr-29 data. The Form_Arm field didn't exist before then; pretending otherwise creates noise.

---

## Open questions you may need to resolve

1. **Layout placement.** Above I said "between KPI strip and first chart row." If the dashboard is already crowded, an alternative is to add a tab or accordion. Yair's preference is probably visible-by-default since A/B is the most actionable thing on the dashboard right now — but ask if you're unsure.
2. **Color scheme.** Match the existing dashboard rather than inventing new colors; if the dashboard uses Bootstrap 5's standard palette (e.g., `bg-success`, `bg-secondary`), use those.
3. **Daily-email duplication.** The `souled-ab-daily-report` Railway service already emails Yair daily. This dashboard section is a different surface for the same data — that's fine and intentional. Don't try to replace the email; complement it.

If anything blocks you, page Yair before guessing. He's been clear that he'd rather rewrite a spec than have you ship the wrong thing.

— end of handoff —
