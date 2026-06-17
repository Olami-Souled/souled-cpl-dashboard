#!/usr/bin/env bash
#
# check-capi-validation-leak.sh
#
# Detects GENUINE signup-path CAPI leaks: a registration-conversion CAPI event
# (Lead / CompleteRegistration) that fired for a Contact which failed validation
# at signup. Those are the only events the ContactTriggerHandler suppression rule
# governs (fires on Source_FormTitan_ID__c='signup', suppressed when
# Failed_Validation__c=true). A real leak inflates Meta's reported conversions.
#
# Why this replaces the naive check
# ----------------------------------
# The original ad-hoc check was:
#
#   SELECT COUNT(Id) FROM Meta_Logs__c
#   WHERE CreatedDate >= <start> AND CreatedDate <= <end>
#     AND Contact__r.Failed_Validation__c = true
#
# It re-trips on false positives for two reasons:
#   1. No Event_Type__c filter, so it counts LIFECYCLE events
#      (FirstMeetingAttended, SecondMeetingAttended, CoachChosen) that fire later
#      against existing contacts and were never subject to signup suppression.
#   2. It joins on the Contact's CURRENT Failed_Validation__c, not the value at
#      fire time. A contact flagged failed days/years after its CAPI fired then
#      retroactively "implicates" a historical Meta_Logs row.
#
# This version fixes both:
#   - Restricts to Event_Type__c IN ('Lead','CompleteRegistration').
#   - Requires the Contact to have been CREATED inside the same window. Signup-path
#     CAPI fires on Contact creation, so a genuine leak's Contact CreatedDate ~=
#     the Meta_Logs CreatedDate. This excludes old contacts flagged retroactively.
#
# Usage:
#   ./check-capi-validation-leak.sh                 # last completed ISO week (Sun..Sat)
#   ./check-capi-validation-leak.sh 2026-06-07 2026-06-13
#   SF_ORG=yspolter-admin ./check-capi-validation-leak.sh
#
# Exit code: 0 = no genuine leak, 1 = leak(s) found (rows printed), 2 = query error.

set -euo pipefail

SF_ORG="${SF_ORG:-claude-sf}"

if [[ $# -eq 2 ]]; then
  START="$1"
  END="$2"
else
  # Default to the last completed ISO week: Sunday 00:00 .. Saturday 23:59.
  END="$(date -u -d 'last saturday' +%Y-%m-%d)"
  START="$(date -u -d "$END - 6 days" +%Y-%m-%d)"
fi

START_TS="${START}T00:00:00Z"
END_TS="${END}T23:59:59Z"

echo "CAPI signup-path leak check"
echo "  org:    ${SF_ORG}"
echo "  window: ${START} .. ${END}"
echo

QUERY="SELECT Id, Event_Type__c, Contact__c, CreatedDate, \
Contact__r.Source_FormTitan_ID__c, Contact__r.Failed_Validation__c, \
Contact__r.CreatedDate, Contact__r.LastModifiedDate \
FROM Meta_Logs__c \
WHERE CreatedDate >= ${START_TS} AND CreatedDate <= ${END_TS} \
AND Event_Type__c IN ('Lead','CompleteRegistration') \
AND Contact__r.Failed_Validation__c = true \
AND Contact__r.CreatedDate >= ${START_TS} AND Contact__r.CreatedDate <= ${END_TS}"

# NOTE: Body__c is intentionally NOT selected — it carries the production Meta
# access token in plaintext (see wiki concepts/meta-logs.md). Keep it out of logs.

if ! OUT="$(sf data query --target-org "${SF_ORG}" --query "${QUERY}" --result-format csv 2>/dev/null)"; then
  echo "ERROR: query failed (org access? ${SF_ORG} may lack Meta_Logs__c visibility)" >&2
  exit 2
fi

# First line is the CSV header; any further lines are leaked rows.
ROWS="$(printf '%s\n' "${OUT}" | tail -n +2 | grep -c . || true)"

if [[ "${ROWS}" -eq 0 ]]; then
  echo "OK — no genuine signup-path CAPI leak in window."
  exit 0
fi

echo "LEAK — ${ROWS} registration-conversion CAPI event(s) fired for failed-validation signups:"
echo
printf '%s\n' "${OUT}"
exit 1
