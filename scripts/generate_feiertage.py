#!/usr/bin/env python3
"""Generate Feiertage and Ferien ICS files for all 16 German Bundesländer."""

import argparse
import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone


PRODID = "ics.tools skjerns patch"
URL = "https://ics.tools"
FEIERTAGE_API = "https://feiertage-api.de/api/"
FERIEN_API = "https://openholidaysapi.org/SchoolHolidays"
MAX_BATCH_DAYS = 1000

# feiertage-api.de land codes
FEIERTAGE_CODES = {
    "baden-württemberg":      "BW",
    "bayern":                 "BY",
    "berlin":                 "BE",
    "brandenburg":            "BB",
    "bremen":                 "HB",
    "hamburg":                "HH",
    "hessen":                 "HE",
    "mecklenburg-vorpommern": "MV",
    "niedersachsen":          "NI",
    "nordrhein-westfalen":    "NW",
    "rheinland-pfalz":        "RP",
    "saarland":               "SL",
    "sachsen-anhalt":         "ST",
    "sachsen":                "SN",
    "schleswig-holstein":     "SH",
    "thüringen":              "TH",
}

# openholidaysapi.org subdivision codes
SUBDIVISION_CODES = {
    "baden-württemberg":      "DE-BW",
    "bayern":                 "DE-BY",
    "berlin":                 "DE-BE",
    "brandenburg":            "DE-BB",
    "bremen":                 "DE-HB",
    "hamburg":                "DE-HH",
    "hessen":                 "DE-HE",
    "mecklenburg-vorpommern": "DE-MV",
    "niedersachsen":          "DE-NI",
    "nordrhein-westfalen":    "DE-NW",
    "rheinland-pfalz":        "DE-RP",
    "saarland":               "DE-SL",
    "sachsen-anhalt":         "DE-ST",
    "sachsen":                "DE-SN",
    "schleswig-holstein":     "DE-SH",
    "thüringen":              "DE-TH",
}

STATES = list(FEIERTAGE_CODES.keys())


def fetch_feiertage_api(land_code: str, year: int) -> list[tuple[date, str]]:
    """Fetch public holidays from feiertage-api.de for a given state and year."""
    params = urllib.parse.urlencode({"jahr": year, "nur_land": land_code})
    req = urllib.request.Request(
        f"{FEIERTAGE_API}?{params}",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return sorted(
        (date.fromisoformat(v["datum"]), name)
        for name, v in data.items()
    )


def make_uid(summary: str, dtstart: date) -> str:
    raw = f"{summary}{dtstart.strftime('%Y%m%d')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def ics_fold(line: str) -> str:
    """RFC 5545 line folding: max 75 octets per line, continuation with CRLF + space."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks = []
    pos = 0
    limit = 75
    while pos < len(encoded):
        chunks.append(encoded[pos:pos + limit].decode("utf-8", errors="ignore"))
        pos += limit
        limit = 74  # continuation lines have 1 char less (the leading space)
    return "\r\n ".join(chunks)


def vevent(summary: str, dtstart: date, dtend: date, timestamp: str) -> str:
    uid = make_uid(summary, dtstart)
    lines = [
        "BEGIN:VEVENT",
        f"DTSTART;VALUE=DATE:{dtstart.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{dtend.strftime('%Y%m%d')}",
        f"SUMMARY:{summary}",
        ics_fold(f"UID:{uid}"),
        f"URL:{URL}",
        f"CREATED:{timestamp}",
        f"LAST-MODIFIED:{timestamp}",
        f"DTSTAMP:{timestamp}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]
    return "\r\n".join(lines)


def write_feiertage(state: str, year_start: int, year_end: int,
                    output_dir: str, timestamp: str) -> None:
    cal_name = f"{state.title()} Feiertage"
    code = FEIERTAGE_CODES[state]
    events = []
    for year in range(year_start, year_end + 1):
        for day, name in fetch_feiertage_api(code, year):
            dtend = day + timedelta(days=1)
            events.append(vevent(name, day, dtend, timestamp))

    parts = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        *events,
        f"NAME:{cal_name}",
        f"X-WR-CALNAME:{cal_name}",
        "METHOD:PUBLISH",
        "END:VCALENDAR",
    ]
    content = "\r\n".join(parts) + "\r\n"

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{state}.ics")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  → {out_path}")


def fetch_ferien_api(subdivision_code: str, from_date: date, to_date: date) -> list[dict]:
    """Fetch school holidays from OpenHolidays API in batches of at most MAX_BATCH_DAYS days."""
    results = []
    current = from_date
    while current <= to_date:
        batch_end = min(current + timedelta(days=MAX_BATCH_DAYS - 1), to_date)
        params = urllib.parse.urlencode({
            "countryIsoCode": "DE",
            "subdivisionCode": subdivision_code,
            "validFrom": current.strftime("%Y-%m-%d"),
            "validTo":   batch_end.strftime("%Y-%m-%d"),
        })
        req = urllib.request.Request(
            f"{FERIEN_API}?{params}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            results.extend(json.loads(resp.read()))
        current = batch_end + timedelta(days=1)

    # Deduplicate entries that appear in overlapping batch windows
    seen: set[tuple] = set()
    unique = []
    for item in results:
        key = (item["startDate"], item["endDate"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def german_name(name_list: list[dict]) -> str:
    for entry in name_list:
        if entry.get("language") == "DE":
            return entry["text"]
    return name_list[0]["text"] if name_list else "Ferien"


def write_ferien(state: str, year_start: int, year_end: int,
                 output_dir: str, timestamp: str) -> None:
    code = SUBDIVISION_CODES[state]
    state_title = state.title()
    cal_name = f"{state_title} Ferien"

    print(f"  {state} ({code}) ...", end="", flush=True)
    holidays = fetch_ferien_api(code, date(year_start, 1, 1), date(year_end, 12, 31))
    print(f" {len(holidays)} entries")

    events = []
    for h in sorted(holidays, key=lambda x: x["startDate"]):
        name = german_name(h["name"])
        start = date.fromisoformat(h["startDate"])
        # API endDate is the last inclusive day; ICS DTEND is exclusive
        end = date.fromisoformat(h["endDate"]) + timedelta(days=1)
        summary = f"{name} {start.year} {state_title}"
        events.append(vevent(summary, start, end, timestamp))

    parts = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        *events,
        f"NAME:{cal_name}",
        f"X-WR-CALNAME:{cal_name}",
        "METHOD:PUBLISH",
        "END:VCALENDAR",
    ]
    content = "\r\n".join(parts) + "\r\n"

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{state}.ics")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  → {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Feiertage and Ferien ICS files for all German Bundesländer."
    )
    parser.add_argument("--year_start", type=int, required=True, help="First year (inclusive)")
    parser.add_argument("--year_end",   type=int, required=True, help="Last year (inclusive)")
    parser.add_argument("--feiertage_dir", default="Feiertage",
                        help="Output directory for Feiertage (default: Feiertage/)")
    parser.add_argument("--ferien_dir", default="Ferien",
                        help="Output directory for Ferien (default: Ferien/)")
    args = parser.parse_args()

    if args.year_start > args.year_end:
        parser.error("year_start must be <= year_end")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"Generating Feiertage {args.year_start}–{args.year_end} → {args.feiertage_dir}/")
    for state in STATES:
        write_feiertage(state, args.year_start, args.year_end, args.feiertage_dir, timestamp)

    print(f"\nFetching Ferien {args.year_start}–{args.year_end} → {args.ferien_dir}/")
    for state in STATES:
        write_ferien(state, args.year_start, args.year_end, args.ferien_dir, timestamp)

    print("Done.")


if __name__ == "__main__":
    main()
