# trucknarc-oath-data

A daily-refreshed snapshot of NYC's OATH Hearings Division Case Status dataset (`jz4z-kudi`
on data.cityofnewyork.us), filtered to DEP §24-163 idling-charge rows only — the subset that
can count as a "prior offense" under 15 RCNY 43-01(5).

`idling_violations.json.deflate` (raw-deflate compressed, not gzip — see `scripts/fetch.py` for
why) is fetched and committed by `.github/workflows/refresh.yml` once a
day (matching NYC's own bulk-sync cadence for this dataset, so there's no real freshness loss
vs. querying the live API). TruckNarcAI downloads this file instead of making live, per-draft
Socrata queries for its plate prior-offense check and as one input to its company-address
lookup.

Known gap: NYC's public dataset gives the respondent's house number, borough, and zip — never
a street, city, or state. TruckNarcAI fills that in with a one-off Claude+web-search lookup,
only for a company that isn't already in Alex's own curated lists and that FMCSA can't find
either; the result is cached so it only ever happens once per company.

To force a refresh outside the daily schedule: Actions tab → "Refresh idling violations
snapshot" → Run workflow.
