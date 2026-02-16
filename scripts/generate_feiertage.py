#!/usr/bin/env python3
"""Generate Feiertage ICS files for all 16 German Bundesländer."""

import argparse
import hashlib
import os
from datetime import date, datetime, timedelta, timezone


PRODID = "ics.tools skjerns patch"
URL = "https://ics.tools"

STATES = [
    "baden-württemberg",
    "bayern",
    "berlin",
    "brandenburg",
    "bremen",
    "hamburg",
    "hessen",
    "mecklenburg-vorpommern",
    "niedersachsen",
    "nordrhein-westfalen",
    "rheinland-pfalz",
    "saarland",
    "sachsen-anhalt",
    "sachsen",
    "schleswig-holstein",
    "thüringen",
]


def easter_sunday(year: int) -> date:
    """Compute Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def buss_und_bettag(year: int) -> date:
    """Wednesday before Nov 23 (i.e. the Wed between Nov 16 and Nov 22)."""
    nov22 = date(year, 11, 22)
    days_back = (nov22.weekday() - 2) % 7  # weekday 2 = Wednesday
    return nov22 - timedelta(days=days_back)


def get_feiertage(state: str, year: int) -> list[tuple[date, str]]:
    """Return (date, name) pairs for the given state and year, sorted by date."""
    e = easter_sunday(year)

    holidays = [
        (date(year, 1, 1),   "Neujahr"),
        (e - timedelta(2),   "Karfreitag"),
        (e + timedelta(1),   "Ostermontag"),
        (date(year, 5, 1),   "Tag der Arbeit"),
        (e + timedelta(39),  "Christi Himmelfahrt"),
        (e + timedelta(50),  "Pfingstmontag"),
        (date(year, 10, 3),  "Tag der Deutschen Einheit"),
        (date(year, 12, 25), "1. Weihnachtsfeiertag"),
        (date(year, 12, 26), "2. Weihnachtsfeiertag"),
    ]

    # Heilige Drei Könige – BW, BY, ST
    if state in {"baden-württemberg", "bayern", "sachsen-anhalt"}:
        holidays.append((date(year, 1, 6), "Heilige Drei Könige"))

    # Internationaler Frauentag – BE from 2019, MV from 2023
    if state == "berlin" and year >= 2019:
        holidays.append((date(year, 3, 8), "Internationaler Frauentag"))
    if state == "mecklenburg-vorpommern" and year >= 2023:
        holidays.append((date(year, 3, 8), "Internationaler Frauentag"))

    # Fronleichnam (Easter+60) – BW, BY, HE, NW, RP, SL
    if state in {"baden-württemberg", "bayern", "hessen", "nordrhein-westfalen",
                 "rheinland-pfalz", "saarland"}:
        holidays.append((e + timedelta(60), "Fronleichnam"))

    # Mariä Himmelfahrt – BY, SL
    if state in {"bayern", "saarland"}:
        holidays.append((date(year, 8, 15), "Mariä Himmelfahrt"))

    # Ostersonntag + Pfingstsonntag – BB only
    if state == "brandenburg":
        holidays.append((e,               "Ostersonntag"))
        holidays.append((e + timedelta(49), "Pfingstsonntag"))

    # Weltkindertag – TH from 2019
    if state == "thüringen" and year >= 2019:
        holidays.append((date(year, 9, 20), "Weltkindertag"))

    # Reformationstag (Oct 31)
    # Always: BB, MV, SN, ST, TH
    # From 2018: HB, HH, NI, SH
    # 2017 only (500th anniversary): all states
    reformation_always = {"brandenburg", "mecklenburg-vorpommern", "sachsen",
                          "sachsen-anhalt", "thüringen"}
    reformation_from_2018 = {"bremen", "hamburg", "niedersachsen", "schleswig-holstein"}
    if year == 2017:
        holidays.append((date(year, 10, 31), "Reformationstag"))
    elif state in reformation_always:
        holidays.append((date(year, 10, 31), "Reformationstag"))
    elif state in reformation_from_2018 and year >= 2018:
        holidays.append((date(year, 10, 31), "Reformationstag"))

    # Allerheiligen – BW, BY, NW, RP, SL
    if state in {"baden-württemberg", "bayern", "nordrhein-westfalen",
                 "rheinland-pfalz", "saarland"}:
        holidays.append((date(year, 11, 1), "Allerheiligen"))

    # Buß- und Bettag – SN
    if state == "sachsen":
        holidays.append((buss_und_bettag(year), "Buß- und Bettag"))

    # Tag der Befreiung – BE, special years only
    if state == "berlin" and year in {2020, 2025}:
        holidays.append((date(year, 5, 8), "Tag der Befreiung"))

    return sorted(holidays)


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
    events = []
    for year in range(year_start, year_end + 1):
        for day, name in get_feiertage(state, year):
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
    print(f"  {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Feiertage ICS files for all German Bundesländer."
    )
    parser.add_argument("--year_start", type=int, required=True, help="First year (inclusive)")
    parser.add_argument("--year_end",   type=int, required=True, help="Last year (inclusive)")
    parser.add_argument("--output_dir", default="Feiertage",
                        help="Output directory (default: Feiertage/)")
    args = parser.parse_args()

    if args.year_start > args.year_end:
        parser.error("year_start must be <= year_end")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"Generating Feiertage for {args.year_start}–{args.year_end} → {args.output_dir}/")
    for state in STATES:
        write_feiertage(state, args.year_start, args.year_end, args.output_dir, timestamp)
    print("Done.")


if __name__ == "__main__":
    main()
