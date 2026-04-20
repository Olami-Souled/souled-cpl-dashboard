## Shared knowledge — Olami/Souled wiki

Before answering any domain question about marketing attribution, CPL,
UTM sources, Meta/CAPI events, or Registration volume, read
`~/knowledge/wiki/index.md` first. The most relevant pages for this repo
are the connection pages — they encode the hard-won filter logic:

- `~/knowledge/wiki/connections/utm-attribution-filter.md` — the UTM/Meta
  `IN ('facebook','ig','fb')` rule.
- `~/knowledge/wiki/connections/meta-capi-tracking.md` — how CAPI events
  link Contact → Registration → Meta_Log.
- `~/knowledge/wiki/concepts/registration.md` — the Souled "lead" row.
- `~/knowledge/wiki/concepts/meta-logs.md` — every CAPI event sent.
- `~/knowledge/wiki/concepts/api-name-typos.md`

Treat the wiki as authoritative. Hard rules:

- UTM/Meta filter: `utm_source__c IN ('facebook','ig','fb')`. Using just
  `'facebook'` misses ~30% of Meta traffic — this is the single most
  common attribution bug in the codebase.
- Test-record exclusion: `Test_Old__c = false AND NOT Name LIKE '%test%'`
  before computing any cost-per-X metric.
- `Manual_Referrrer__c` (triple `r`) on Registration is a real field.

If the wiki is missing a topic that comes up here, flag it.
Wiki repo: github.com/Olami-Souled/knowledge.