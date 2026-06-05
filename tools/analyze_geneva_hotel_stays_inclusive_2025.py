#!/usr/bin/env python3
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import analyze_geneva_hotel_stays_inclusive as base


ROOT = Path.cwd()
YEAR = 2025
DETAIL_CSV = ROOT / "geneva_hotel_2025_stays_inclusive_detail.csv"
MONTHLY_CSV = ROOT / "geneva_hotel_2025_inclusive_monthly_subtotals.csv"
ANNUAL_CSV = ROOT / "geneva_hotel_2025_inclusive_annual_subtotals.csv"
EMPTY_WEEKS_CSV = ROOT / "geneva_hotel_2025_inclusive_weeks_without_reservation.csv"
CONCERNED_FILES_CSV = ROOT / "geneva_hotel_2025_concerned_files.csv"


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def overlaps_year(start, end):
    year_start = date(YEAR, 1, 1)
    year_end = date(YEAR + 1, 1, 1)
    return start < year_end and end > year_start


def main():
    candidates = []
    reservation_candidates = []
    for root in base.INPUT_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            text = base.text_for(path)
            if not text or not base.is_geneva_city_stay(path, text):
                continue
            start, end, date_source = base.date_range_from_text(text)
            if not start or not end or end <= start or not overlaps_year(start, end):
                continue
            est = base.establishment_for(path, text)
            ref = base.reservation_ref(text)
            stype = base.source_type(path, text)
            reservation_candidates.append({
                "establishment": est,
                "stay_start": start,
                "stay_end": end,
                "ref": ref,
                "source_type": stype,
                "file": str(path.relative_to(ROOT)),
            })
            amount, amount_source = base.extract_amount(path, text)
            if amount is None:
                continue
            candidates.append({
                "establishment": est,
                "amount_chf": base.q2(amount),
                "invoice_date": base.invoice_date_from_filename(path),
                "stay_start": start,
                "stay_end": end,
                "nights": (end - start).days,
                "ref": ref,
                "source_type": stype,
                "amount_source": amount_source,
                "date_source": date_source,
                "file": str(path.relative_to(ROOT)),
            })

    selected = {}
    duplicates = []
    for row in candidates:
        key = (row["establishment"], row["stay_start"], row["stay_end"])
        prev = selected.get(key)
        if prev is None:
            selected[key] = row
            continue
        prev_score = (1 if prev["source_type"] == "official" else 0, 1 if prev["ref"] else 0)
        row_score = (1 if row["source_type"] == "official" else 0, 1 if row["ref"] else 0)
        if row_score > prev_score:
            duplicates.append(prev)
            selected[key] = row
        else:
            duplicates.append(row)

    rows = sorted(selected.values(), key=lambda r: (r["stay_start"], r["establishment"], r["source_type"], r["file"]))
    for row in rows:
        row["month"] = row["stay_start"].strftime("%Y-%m")
        row["year"] = row["stay_start"].strftime("%Y")
        row["avg_chf_per_night"] = base.q2(row["amount_chf"] / Decimal(row["nights"]))

    monthly = defaultdict(lambda: {"total": Decimal("0.00"), "official": Decimal("0.00"), "non_official": Decimal("0.00"), "nights": 0, "count": 0})
    monthly_est = defaultdict(lambda: {"total": Decimal("0.00"), "official": Decimal("0.00"), "non_official": Decimal("0.00")})
    annual = defaultdict(lambda: {"total": Decimal("0.00"), "official": Decimal("0.00"), "non_official": Decimal("0.00"), "nights": 0, "count": 0})
    annual_est = defaultdict(lambda: {"total": Decimal("0.00"), "official": Decimal("0.00"), "non_official": Decimal("0.00")})
    for row in rows:
        source_bucket = row["source_type"]
        month = row["month"]
        year = row["year"]
        monthly[month]["total"] += row["amount_chf"]
        monthly[month][source_bucket] += row["amount_chf"]
        monthly[month]["nights"] += row["nights"]
        monthly[month]["count"] += 1
        monthly_est[(month, row["establishment"])]["total"] += row["amount_chf"]
        monthly_est[(month, row["establishment"])][source_bucket] += row["amount_chf"]
        annual[year]["total"] += row["amount_chf"]
        annual[year][source_bucket] += row["amount_chf"]
        annual[year]["nights"] += row["nights"]
        annual[year]["count"] += 1
        annual_est[(year, row["establishment"])]["total"] += row["amount_chf"]
        annual_est[(year, row["establishment"])][source_bucket] += row["amount_chf"]

    detail_rows = []
    for row in rows:
        detail_rows.append({
            "month": row["month"],
            "year": row["year"],
            "establishment": row["establishment"],
            "amount_chf": f"{row['amount_chf']:.2f}",
            "official_chf": f"{row['amount_chf']:.2f}" if row["source_type"] == "official" else "0.00",
            "non_official_chf": f"{row['amount_chf']:.2f}" if row["source_type"] == "non_official" else "0.00",
            "source_type": row["source_type"],
            "stay_start": row["stay_start"].isoformat(),
            "stay_end": row["stay_end"].isoformat(),
            "nights": row["nights"],
            "avg_chf_per_night": f"{row['avg_chf_per_night']:.2f}",
            "invoice_date": row["invoice_date"],
            "ref": row["ref"],
            "file": row["file"],
            "amount_source": row["amount_source"],
            "date_source": row["date_source"],
        })
    write_csv(DETAIL_CSV, detail_rows, ["month", "year", "establishment", "amount_chf", "official_chf", "non_official_chf", "source_type", "stay_start", "stay_end", "nights", "avg_chf_per_night", "invoice_date", "ref", "file", "amount_source", "date_source"])

    monthly_rows = []
    prev_total = None
    for month in sorted(monthly):
        subtotal = base.q2(monthly[month]["total"])
        avg = base.q2(subtotal / Decimal(monthly[month]["nights"])) if monthly[month]["nights"] else Decimal("0.00")
        change = "" if prev_total is None else base.q2(subtotal - prev_total)
        change_pct = "" if prev_total in (None, Decimal("0.00")) else base.q2(((subtotal - prev_total) / prev_total) * Decimal("100"))
        for (m, est), data in sorted(monthly_est.items()):
            if m == month:
                monthly_rows.append({
                    "month": month,
                    "establishment": est,
                    "total_chf": f"{base.q2(data['total']):.2f}",
                    "official_chf": f"{base.q2(data['official']):.2f}",
                    "non_official_chf": f"{base.q2(data['non_official']):.2f}",
                    "month_subtotal_chf": f"{subtotal:.2f}",
                    "month_official_chf": f"{base.q2(monthly[month]['official']):.2f}",
                    "month_non_official_chf": f"{base.q2(monthly[month]['non_official']):.2f}",
                    "invoice_count": monthly[month]["count"],
                    "nights": monthly[month]["nights"],
                    "avg_chf_per_night": f"{avg:.2f}",
                    "change_vs_previous_month_chf": f"{change:.2f}" if change != "" else "",
                    "change_vs_previous_month_pct": f"{change_pct:.2f}" if change_pct != "" else "",
                })
        prev_total = subtotal
    write_csv(MONTHLY_CSV, monthly_rows, ["month", "establishment", "total_chf", "official_chf", "non_official_chf", "month_subtotal_chf", "month_official_chf", "month_non_official_chf", "invoice_count", "nights", "avg_chf_per_night", "change_vs_previous_month_chf", "change_vs_previous_month_pct"])

    annual_rows = []
    for year in sorted(annual):
        total = base.q2(annual[year]["total"])
        avg = base.q2(total / Decimal(annual[year]["nights"])) if annual[year]["nights"] else Decimal("0.00")
        for (y, est), data in sorted(annual_est.items()):
            if y == year:
                annual_rows.append({
                    "year": year,
                    "establishment": est,
                    "total_chf": f"{base.q2(data['total']):.2f}",
                    "official_chf": f"{base.q2(data['official']):.2f}",
                    "non_official_chf": f"{base.q2(data['non_official']):.2f}",
                    "year_subtotal_chf": f"{total:.2f}",
                    "year_official_chf": f"{base.q2(annual[year]['official']):.2f}",
                    "year_non_official_chf": f"{base.q2(annual[year]['non_official']):.2f}",
                    "count": annual[year]["count"],
                    "nights": annual[year]["nights"],
                    "avg_chf_per_night": f"{avg:.2f}",
                })
    write_csv(ANNUAL_CSV, annual_rows, ["year", "establishment", "total_chf", "official_chf", "non_official_chf", "year_subtotal_chf", "year_official_chf", "year_non_official_chf", "count", "nights", "avg_chf_per_night"])

    deduped_reservations = {}
    for row in reservation_candidates:
        key = (row["establishment"], row["stay_start"], row["stay_end"], row["ref"])
        deduped_reservations.setdefault(key, row)
    covered_weeks = set()
    for row in deduped_reservations.values():
        cursor = base.monday_of_week(row["stay_start"])
        last = base.monday_of_week(row["stay_end"] - timedelta(days=1))
        while cursor <= last:
            if cursor.year == YEAR:
                covered_weeks.add(cursor)
            cursor += timedelta(days=7)
    empty_weeks = []
    cursor = base.monday_of_week(date(YEAR, 1, 1))
    last_week = base.monday_of_week(date(YEAR, 12, 31))
    while cursor <= last_week:
        if cursor.year == YEAR and cursor not in covered_weeks:
            iso = cursor.isocalendar()
            empty_weeks.append({"iso_year": iso.year, "iso_week": iso.week, "week_start": cursor.isoformat(), "week_end": (cursor + timedelta(days=6)).isoformat()})
        cursor += timedelta(days=7)
    write_csv(EMPTY_WEEKS_CSV, empty_weeks, ["iso_year", "iso_week", "week_start", "week_end"])

    concerned_rows = []
    for row in detail_rows:
        concerned_rows.append({
            "file": row["file"],
            "source_type": row["source_type"],
            "establishment": row["establishment"],
            "stay_start": row["stay_start"],
            "stay_end": row["stay_end"],
            "nights": row["nights"],
            "amount_chf": row["amount_chf"],
            "official_chf": row["official_chf"],
            "non_official_chf": row["non_official_chf"],
            "invoice_date": row["invoice_date"],
            "ref": row["ref"],
        })
    write_csv(CONCERNED_FILES_CSV, concerned_rows, ["file", "source_type", "establishment", "stay_start", "stay_end", "nights", "amount_chf", "official_chf", "non_official_chf", "invoice_date", "ref"])

    total = sum((row["amount_chf"] for row in rows), Decimal("0.00"))
    official = sum((row["amount_chf"] for row in rows if row["source_type"] == "official"), Decimal("0.00"))
    non_official = total - official
    nights = sum(row["nights"] for row in rows)
    print(f"YEAR={YEAR}")
    print(f"TOTAL_CHF={base.q2(total):.2f}")
    print(f"OFFICIAL_CHF={base.q2(official):.2f}")
    print(f"NON_OFFICIAL_CHF={base.q2(non_official):.2f}")
    print(f"OFFICIAL_SHARE_PCT={base.q2((official / total) * Decimal('100')) if total else Decimal('0.00'):.2f}")
    print(f"NON_OFFICIAL_SHARE_PCT={base.q2((non_official / total) * Decimal('100')) if total else Decimal('0.00'):.2f}")
    print(f"DEDUPED_STAYS_WITH_AMOUNT={len(rows)}")
    print(f"DUPLICATE_AMOUNT_ROWS_REMOVED={len(duplicates)}")
    print(f"NIGHTS={nights}")
    print(f"AVG_CHF_PER_NIGHT={base.q2(total / Decimal(nights)) if nights else Decimal('0.00'):.2f}")
    print(f"DEDUPED_RESERVATIONS_WITH_DATES={len(deduped_reservations)}")
    print(f"EMPTY_WEEKS={len(empty_weeks)}")


if __name__ == "__main__":
    sys.exit(main())
