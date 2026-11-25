#!/usr/bin/env python3
"""
Pulls every DEP idling-charge row from NYC's OATH Hearings Division Case Status dataset
(jz4z-kudi on data.cityofnewyork.us) and writes a trimmed JSON snapshot, raw-deflate-compressed,
to idling_violations.json.deflate.

Raw deflate (zlib.compressobj with wbits=-15), not .gz: Apple's Compression framework decodes
raw deflate directly (`(data as NSData).decompressed(using: .zlib)`) with no header-stripping
code needed on the Swift side. A real gzip file has an extra 10-byte header + 8-byte trailer
that framework doesn't understand, so producing actual gzip here would just mean writing that
parsing by hand in Swift for no benefit.

Why this filter: a complaint only counts as a "prior" under 15 RCNY 43-01(5) if it's a DEP
§24-163 idling finding. Pulling just that subset (instead of the full ~2.9M-row OATH dataset)
keeps this small enough to host as a plain file, no Git LFS needed.

Why these fields: everything TruckNarcAI's PriorOffense/CompanyDirectory lookups actually use.
Notably respondent_address_house/borough/zip_code are the ONLY address fields NYC publishes for
the respondent — no street, city, or state. That's a known gap; the app fills it in with a
one-off Claude+web-search lookup only when a company isn't already in Alex's own curated lists
and FMCSA can't find it either (see CompanyDirectory.swift).
"""
import json
import zlib
import subprocess
import sys
import time

ENDPOINT = "https://data.cityofnewyork.us/resource/jz4z-kudi.json"
PAGE_SIZE = 50000

FIELDS = [
    "ticket_number", "violation_date", "issuing_agency",
    "respondent_last_name", "respondent_address_house",
    "respondent_address_borough", "respondent_address_zip_code",
    "hearing_status", "hearing_result", "violation_details",
    "charge_1_code_section", "charge_1_code_description",
    "charge_2_code_section", "charge_2_code_description",
    "charge_3_code_section", "charge_3_code_description",
    "charge_4_code_section", "charge_4_code_description",
]

# Idling can land on any of the 4 charge slots, not just the first — matches OATHClient.swift's
# own live-query WHERE clause so the snapshot and the (still-available) live fallback agree.
WHERE = "issuing_agency like 'DEP%' AND (" + " OR ".join(
    f"charge_{n}_code_section like '24-163%' OR upper(charge_{n}_code_description) like '%IDLING%'"
    for n in (1, 2, 3, 4)
) + ")"


def fetch_page(offset: int) -> list:
    params = {
        "$select": ",".join(FIELDS),
        "$where": WHERE,
        "$order": "ticket_number",
        "$limit": str(PAGE_SIZE),
        "$offset": str(offset),
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    # curl, not urllib — this project's own CLAUDE.md notes urllib's SSL verification fails
    # under isolated/sandboxed Python; curl sidesteps it cleanly.
    url = f"{ENDPOINT}?{query}"
    for attempt in range(3):
        out = subprocess.run(["curl", "-s", "-m", "60", "-G", ENDPOINT,
                               "--data-urlencode", f"$select={params['$select']}",
                               "--data-urlencode", f"$where={WHERE}",
                               "--data-urlencode", f"$order={params['$order']}",
                               "--data-urlencode", f"$limit={PAGE_SIZE}",
                               "--data-urlencode", f"$offset={offset}"],
                              capture_output=True, timeout=70)
        if out.returncode == 0 and out.stdout:
            try:
                return json.loads(out.stdout)
            except json.JSONDecodeError:
                pass
        print(f"  retry {attempt + 1} at offset {offset}", file=sys.stderr)
        time.sleep(2)
    raise RuntimeError(f"Failed to fetch page at offset {offset} after 3 attempts")


def main():
    rows = []
    offset = 0
    while True:
        page = fetch_page(offset)
        if not page:
            break
        rows.extend(page)
        print(f"  fetched {len(rows)} rows so far...", file=sys.stderr)
        offset += PAGE_SIZE
        if len(page) < PAGE_SIZE:
            break

    raw = json.dumps(rows, separators=(",", ":")).encode("utf-8")
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(raw) + compressor.flush()
    with open("idling_violations.json.deflate", "wb") as f:
        f.write(compressed)

    print(f"Wrote {len(rows)} rows ({len(raw)} bytes raw, {len(compressed)} bytes compressed) "
          f"to idling_violations.json.deflate")


if __name__ == "__main__":
    main()
