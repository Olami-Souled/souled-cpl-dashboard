# A/B Test Registration Query

SOQL for the daily A/B test refresh. Run via `salesforce_query` MCP and save to `data/sf_ab_test.json`.

```sql
SELECT Id, CreatedDate, Form_Arm__c
FROM Registration__c
WHERE Program__c = 'a2F5f000000yRpfEAE'
  AND Student__r.Test_Old__c = false
  AND (NOT Student__r.Name LIKE '%test%')
  AND Student__r.Failed_Validation__c = false
  AND Referral_Type__c = 'Paid'
  AND CreatedDate >= 2026-04-30T00:00:00Z
ORDER BY CreatedDate ASC
```

## Key filters

- `Program__c = 'a2F5f000000yRpfEAE'` — Souled program only
- `Test_Old__c = false AND NOT Name LIKE '%test%'` — standard test-record exclusion
- `Referral_Type__c = 'Paid'` — paid acquisition only (no UTM filter here; the Paid flag is the gate)
- `Student__r.Failed_Validation__c = false` — exclude contacts who failed form validation (matches the canonical SF report filter)
- `CreatedDate >= 2026-04-30T00:00:00Z` — tracking start date (Form_Arm__c field was deployed Apr 30; Apr 29 nulls are pre-tracking and ambiguous)

## Arm mapping

| `Form_Arm__c` value | Meaning |
|---|---|
| `'new'` | New WordPress form at `souled.olami.org/join-test/` |
| `null` | Legacy Visualforce form at `online.olami.org/joinsouled` — India team hasn't added `'old'` yet; treat null as "old" in the rendering layer |

The rendering layer (`load_ab_test_data()` in `refresh_dashboard.py`) handles the null→"old" mapping. Do **not** write `'old'` to Salesforce yourself.

## Reference IDs

| Thing | Value |
|---|---|
| Souled Program ID | `a2F5f000000yRpfEAE` |
| A/B test start | `2026-04-29` |
| Canonical SF report | `00ORi00000MFahdMAD` ("Paid signups by form a/b test") |
| Splitter URL | `https://souled.olami.org/join-now/` |
| New form URL | `https://souled.olami.org/join-test/` |
| Legacy form URL | `https://online.olami.org/joinsouled` |
