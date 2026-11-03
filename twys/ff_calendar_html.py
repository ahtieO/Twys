"""Forex Factory public webpage calendar reader.

The weekly JSON export does not expose released actuals. The public calendar page
contains the figures shown to readers. We only make ordinary public HTTPS
requests, respect access failures, and never infer missing results. The HTML is
subject to change; failures must not be mistaken for an empty calendar.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MONTHS = {n.lower(): i for i, n in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
CURRENCY = re.compile(r"\b(?:USD|EUR|GBP|JPY|AUD|CAD|CHF|NZD|CNY|ALL)\b", re.I)
DATE_TOKEN = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s*(\d{1,2})\b", re.I)
SOURCE_ZONE = re.compile(r"Calendar\s+Time\s+Zone\s*:\s*([\w/+-]+)\s*\(\s*GMT", re.I)
TIME_TOKEN = re.compile(r"^\s*(\d{1,2}):?(\d{2})?\s*(am|pm)?\s*$", re.I)


def page_url(week_start: date) -> str:
    return "https://www.forexfactory.com/calendar?" + urlencode({"week": week_start.strftime("%b").lower() + str(week_start.day) + "." + str(week_start.year)})


def download_week(week_start: date, timeout: int = 12) -> bytes:
    """Request the public HTML table with a UTC display time zone.

    No challenge-solving, account impersonation or anti-bot evasion is attempted.
    """
    req = Request(page_url(week_start), headers={
        "User-Agent": "TWYS Terminal/2.7 (personal economic-calendar reader)",
        "Accept": "text/html,application/xhtml+xml",
        "Cookie": "fftimezone=Etc/GMT; fftimeformat=1",
    })
    with urlopen(req, timeout=timeout) as response:
        data = response.read(2_500_001)
        if len(data) > 2_500_000:
            raise ValueError("Calendar page larger than the permitted response size")
        if "html" not in response.headers.get("Content-Type", "html").lower():
            raise ValueError("Calendar provider did not return HTML")
        return data


def source_timezone(html_text: str):
    from bs4 import BeautifulSoup
    # FF may split the label and time zone across separate elements.
    raw = BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)
    match = SOURCE_ZONE.search(raw)
    if not match:
        raise ValueError("Forex Factory calendar timezone could not be verified")
    label = match.group(1)
    try:
        return ZoneInfo(label)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unrecognized source timezone: " + label) from exc


def _event_day(raw: str, week_start: date):
    hit = DATE_TOKEN.search(raw)
    if not hit:
        return None
    mon, dd = MONTHS[hit.group(1).lower()], int(hit.group(2))
    # Nearest week date, including Dec/Jan rollover.
    candidates = []
    for year in (week_start.year - 1, week_start.year, week_start.year + 1):
        try:
            candidates.append(date(year, mon, dd))
        except ValueError:
            continue
    if not candidates:
        return None
    return min(candidates, key=lambda d: abs((d - (week_start + timedelta(days=3))).days))


def _clock(raw: str):
    value = raw.strip().lower().replace(" ", "")
    found = TIME_TOKEN.fullmatch(value)
    if not found:
        return None
    h, minute, meridiem = int(found.group(1)), int(found.group(2) or "0"), found.group(3)
    if minute > 59 or h > (12 if meridiem else 23) or (meridiem and h == 0):
        return None
    if meridiem:
        h = h % 12 + (12 if meridiem == "pm" else 0)
    return time(hour=h, minute=minute)


def _impact(cell):
    if cell is None:
        return "unrated"
    classes = " ".join(" ".join(tag.get("class", [])) for tag in [cell, *cell.select("[class]")]).lower()
    title = " ".join(str(tag.get("title") or "") for tag in [cell, *cell.select("[title]")]).lower()
    composite = classes + " " + title
    if any(s in composite for s in ("impact-red", "--high", "high impact")):
        return "high"
    if any(s in composite for s in ("impact-ora", "--medium", "med impact", "medium impact")):
        return "medium"
    if any(s in composite for s in ("impact-yel", "--low", "low impact")):
        return "low"
    return "unrated"


def parse_week(html: bytes | str, week_start: date):
    """Parse the webpage into TWYS events, with independently visible actuals.

    A calendar row may omit its date/time when these match the previous row.
    Non-timed items remain date-only rather than pretending to be midnight UTC.
    """
    from bs4 import BeautifulSoup
    source = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    soup = BeautifulSoup(source, "html.parser")
    table = soup.select_one("table.calendar__table")
    if table is None:
        raise ValueError("Forex Factory calendar table not available (page changed or blocked)")
    zone = source_timezone(source)
    events = []
    current_day = None
    current_time = ""
    for index, row in enumerate(table.select("tr.calendar__row")):
        event_cell = row.select_one("td.calendar__event")
        if event_cell is None:
            continue
        name_element = event_cell.select_one("span.calendar__event-title") or event_cell
        name = name_element.get_text(" ", strip=True)
        currency_cell = row.select_one("td.calendar__currency")
        currency_match = CURRENCY.search(currency_cell.get_text(" ", strip=True)) if currency_cell else None
        if not name or not currency_match:
            continue
        date_cell = row.select_one("td.calendar__date")
        date_label = date_cell.get_text(" ", strip=True) if date_cell else ""
        if date_label:
            parsed_day = _event_day(date_label, week_start)
            if parsed_day:
                if parsed_day != current_day:
                    current_time = ""
                current_day = parsed_day
        if not current_day:
            continue
        time_cell = row.select_one("td.calendar__time")
        clock = time_cell.get_text(" ", strip=True) if time_cell else ""
        if clock:
            current_time = clock
        exact_time = _clock(current_time)
        if exact_time:
            stamp = datetime.combine(current_day, exact_time, zone).astimezone(timezone.utc).isoformat()
            precision = "timestamp"
        else:
            stamp = current_day.isoformat()
            precision = "all_day" if "all day" in current_time.lower() else "date_only"
        def reading(css):
            node = row.select_one(css)
            if not node:
                return None
            # Prefer text over title/alt so revision arrows are not interpreted as results.
            result = node.get_text(" ", strip=True).strip()
            return result if result and result not in ("-", "—") else None
        actual = reading("td.calendar__actual")
        event_id = row.get("data-event-id") or f"{current_day}_{currency_match.group().upper()}_{name}_{index}"
        events.append({
            "id": str(event_id), "datetime": stamp,
            "country": currency_match.group().upper(), "currency": currency_match.group().upper(),
            "event": name, "impact": _impact(row.select_one("td.calendar__impact")),
            "impact_basis": "Forex Factory webpage classification", "actual": actual,
            "actual_status": "released" if actual is not None else "not_reported",
            "forecast": reading("td.calendar__forecast"), "previous": reading("td.calendar__previous"),
            "source": "Forex Factory calendar webpage", "source_url": page_url(week_start),
            "time_precision": precision,
        })
    if not events:
        raise ValueError("Calendar page returned no usable economic events")
    return events


def event_local_date(event) -> date:
    stamp = event.get("datetime", "")
    if event.get("time_precision") != "timestamp":
        return date.fromisoformat(stamp[:10])
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().date()
