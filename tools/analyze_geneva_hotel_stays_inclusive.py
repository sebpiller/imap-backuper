#!/usr/bin/env python3
import csv
import html
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


ROOT = Path.cwd()
INPUT_ROOTS = [ROOT / "Invoices_hotel", ROOT / "maybe"]
DETAIL_CSV = ROOT / "geneva_hotel_stays_inclusive_detail.csv"
MONTHLY_CSV = ROOT / "geneva_hotel_inclusive_monthly_subtotals.csv"
ANNUAL_CSV = ROOT / "geneva_hotel_inclusive_annual_subtotals.csv"
EMPTY_WEEKS_CSV = ROOT / "geneva_hotel_inclusive_weeks_without_reservation.csv"

GENEVA_TERMS = re.compile(r"\b(gen[eè]ve|geneva)\b", re.I)
GENEVA_30KM_TERMS = re.compile(
    r"(gen[eè]ve|geneva|petit[- ]lancy|grand[- ]lancy|\blancy\b|meyrin|cointrin|"
    r"nash airport hotel|ramada encore|vernier|carouge|onex|bernex|versoix|nyon|"
    r"ferney|pr[ée]vessin|annemasse|gaillard|saint[- ]julien|archamps|thoiry)",
    re.I,
)
LODGING_TERMS = re.compile(r"(hotel|hôtel|residence|résidence|aparthotel|airbnb|booking\.com|chambre|room|séjour|sejour|stay|arrivée|depart|départ|checkout|check-in|lodgingreservation)", re.I)
NON_OFFICIAL_TERMS = re.compile(
    r"(ceci n['’]est pas une facture|not an invoice|ne peut pas être utilisée pour demander le remboursement de la tva|"
    r"cannot be used.*vat|confirmation|réservation|reservation|vous avez payé|montant total)",
    re.I | re.S,
)
OFFICIAL_TERMS = re.compile(r"(\binvoice\b|\bfacture\b|\bfolio\b|votre reçu d['’]airbnb|numéro du reçu|receipt number)", re.I)

KNOWN_GENEVA_ESTABLISHMENTS = [
    ("primadom", "Primadom Aparthotel"),
    ("starling", "Starling Hotel Residence Geneve"),
    ("shresidence", "Starling Hotel Residence Geneve"),
    ("ramada encore", "Ramada Encore by Wyndham Geneva"),
    ("nash airport", "Nash Airport Hotel"),
    ("ibis budget geneve petit-lancy", "ibis budget Geneve Petit-Lancy"),
    ("ibis budget genève petit-lancy", "ibis budget Geneve Petit-Lancy"),
    ("green marmot", "Green Marmot Capsule Hotel Geneve"),
    ("green-marmot", "Green Marmot Capsule Hotel Geneve"),
    ("civitfun", "Green Marmot Capsule Hotel Geneve"),
    ("hotel des tourelles", "Hotel des Tourelles"),
    ("design hotel f6", "Design Hotel f6"),
    ("airbnb", "Airbnb"),
]
MONTHS = {
    "jan": 1, "janv": 1, "january": 1, "janvier": 1, "januar": 1,
    "feb": 2, "fev": 2, "fevr": 2, "févr": 2, "february": 2, "fevrier": 2, "février": 2, "februar": 2,
    "mar": 3, "march": 3, "mars": 3, "maerz": 3, "märz": 3,
    "apr": 4, "avr": 4, "april": 4, "avril": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6, "juni": 6,
    "jul": 7, "july": 7, "juillet": 7, "juli": 7,
    "aug": 8, "aou": 8, "aoû": 8, "august": 8, "aout": 8, "août": 8,
    "sep": 9, "sept": 9, "september": 9, "septembre": 9,
    "oct": 10, "october": 10, "octobre": 10, "okt": 10,
    "nov": 11, "november": 11, "novembre": 11,
    "dec": 12, "déc": 12, "december": 12, "decembre": 12, "décembre": 12,
}


def run_text_command(args):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False, timeout=20)
    except Exception:
        return ""
    return result.stdout.decode("utf-8", errors="ignore")


def is_pdf(path):
    try:
        return path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def text_for(path):
    if is_pdf(path):
        return run_text_command(["pdftotext", str(path), "-"])
    if path.suffix.lower() in {".html", ".htm", ".txt"}:
        try:
            raw = path.read_text(errors="ignore")
        except OSError:
            return ""
        json_bits = "\n".join(re.findall(r"(?is)<script[^>]*application/ld\+json[^>]*>(.*?)</script>", raw))
        cleaned = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
        cleaned = re.sub(r"(?s)<[^>]+>", "\n", cleaned)
        return html.unescape(cleaned + "\n" + json_bits)
    return ""


def flat(text):
    return re.sub(r"\s+", " ", text).strip()


def money_to_decimal(value):
    cleaned = value.replace("'", "").replace("\u00a0", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def q2(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_dmy(value):
    d, m, y = [int(x) for x in re.split(r"[./-]", value)]
    if y < 100:
        y = 2000 + y if y < 70 else 1900 + y
    return date(y, m, d)


def month_number(name):
    key = re.sub(r"[^A-Za-zÀ-ÿ]", "", name).lower()
    return MONTHS.get(key) or MONTHS.get(key[:4]) or MONTHS.get(key[:3])


def parse_human_date(day, month_name, year):
    mo = month_number(month_name)
    if not mo:
        return None
    return date(int(year), mo, int(day))


def lodging_json(text):
    m = re.search(r"\"@type\"\s*:\s*\"LodgingReservation\".*?\"reservationFor\"\s*:\s*\{.*?\"name\"\s*:\s*\"([^\"]+)\"", text, re.S)
    if not m:
        return ""
    return m.group(1)


def establishment_for(path, text):
    hay = f"{path.as_posix()} {text[:5000]}".lower()
    if "airbnb" in hay:
        return "Airbnb"
    for key, name in KNOWN_GENEVA_ESTABLISHMENTS:
        if key in hay:
            return name
    m = re.search(r"20\d{2}-\d{2}-\d{2}-(.+?)\.[^.]+$", path.name)
    return m.group(1) if m else path.stem


def date_range_from_text(text):
    hay = flat(text)

    m = re.search(r"\"checkinDate\"\s*:\s*\"(20\d{2}-\d{2}-\d{2})T[^\"]*\".*?\"checkoutDate\"\s*:\s*\"(20\d{2}-\d{2}-\d{2})T", text, re.S)
    if m:
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2)), "json checkin/checkout fields"

    m = re.search(r"S[ée]jour\s+du\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s+au\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", hay, re.I)
    if m:
        return parse_dmy(m.group(1)), parse_dmy(m.group(2)), "Séjour du/au"

    m = re.search(r"(\d{1,2}[.]\d{1,2}[.]\d{2})\s*-\s*(\d{1,2}[.]\d{1,2}[.]\d{2})", hay)
    if m:
        return parse_dmy(m.group(1)), parse_dmy(m.group(2)), "Dates of Stay"

    # Booking.com French arrival/departure blocks.
    m = re.search(
        r"Arriv[ée]e\s+(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\s*"
        r"(\d{1,2})\s+([A-Za-zÀ-ÿ.]+)\s+(20\d{2}).*?"
        r"D[ée]part\s+(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\s*"
        r"(\d{1,2})\s+([A-Za-zÀ-ÿ.]+)\s+(20\d{2})",
        hay,
        re.I | re.S,
    )
    if m:
        start = parse_human_date(m.group(1), m.group(2), m.group(3))
        end = parse_human_date(m.group(4), m.group(5), m.group(6))
        if start and end:
            return start, end, "Booking arrival/departure"

    m = re.search(
        r"(?:lun\.?|mar\.?|mer\.?|jeu\.?|ven\.?|sam\.?|dim\.?)?\s*"
        r"(\d{1,2})\s+([A-Za-zÀ-ÿ.]+)\s+(20\d{2})\s*(?:-|→|->|&gt;)\s*"
        r"(?:lun\.?|mar\.?|mer\.?|jeu\.?|ven\.?|sam\.?|dim\.?)?\s*"
        r"(\d{1,2})\s+([A-Za-zÀ-ÿ.]+)\s+(20\d{2})",
        hay,
        re.I,
    )
    if m:
        start = parse_human_date(m.group(1), m.group(2), m.group(3))
        end = parse_human_date(m.group(4), m.group(5), m.group(6))
        if start and end:
            return start, end, "visible human date range"

    return None, None, "no stay dates"


def invoice_date_from_filename(path):
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    return m.group(1) if m else ""


def amounts_on_labeled_lines(text, label_pattern):
    out = []
    for line in text.splitlines():
        if not re.search(label_pattern, line, re.I):
            continue
        for num in re.findall(r"(?<![\d.,])(\d{1,5}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))(?![\d.,])", line):
            val = money_to_decimal(num)
            if val is not None:
                out.append(val)
    return out


def amounts_after_label(text, label_pattern, window=220):
    out = []
    compact = flat(text)
    for m in re.finditer(label_pattern, compact, re.I):
        snippet = compact[m.end():m.end() + window]
        for num in re.findall(r"(?<!\d)(\d{1,5}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))(?:\s*)(?:CHF|EUR|€)?", snippet):
            val = money_to_decimal(num)
            if val is not None:
                out.append(val)
    return out


def extract_amount(path, text):
    lower = f"{path.name} {text[:5000]}".lower()
    if "primadom" in lower:
        vals = amounts_on_labeled_lines(text, r"montant total ttc") or amounts_after_label(text, r"montant total ttc", 80)
        if vals:
            return vals[0], "Montant total TTC"
    if "starling" in lower or "shresidence" in lower:
        vals = amounts_on_labeled_lines(text, r"total incl\.?\s*tva") or amounts_after_label(text, r"total incl\.?\s*tva", 160)
        if vals:
            return vals[-1], "Total incl. TVA"
    for label in [
        r"vous avez payé",
        r"montant payé",
        r"amount paid",
        r"total\s*\(chf\)",
        r"montant total",
        r"total paid",
        r"grand total",
        r"total ttc",
        r"\btotal\b",
    ]:
        vals = amounts_on_labeled_lines(text, label) or amounts_after_label(text, label, 180)
        vals = [v for v in vals if Decimal("10.00") <= v <= Decimal("10000.00")]
        if vals:
            return vals[-1] if "pay" in label or "payé" in label else max(vals), label
    prefixed = []
    for num in re.findall(r"(?:CHF|EUR|€)\s*(\d{1,5}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))", flat(text), re.I):
        val = money_to_decimal(num)
        if val is not None and Decimal("10.00") <= val <= Decimal("10000.00"):
            prefixed.append(val)
    if prefixed:
        return max(prefixed), "currency-prefixed amount"
    return None, "no amount"


def is_geneva_city_stay(path, text):
    hay = f"{path.as_posix()} {text[:18000]}"
    if not GENEVA_30KM_TERMS.search(hay):
        return False
    if re.search(r"FlightReservation|flightNumber|Easyjet|EuroAirport|Marrakech", hay, re.I) and not LODGING_TERMS.search(hay):
        return False
    return bool(LODGING_TERMS.search(hay))


def reservation_ref(text):
    for pat in [
        r"Code de confirmation\s*:?\s*([A-Z0-9]+)",
        r"reservationNumber\"\s*:\s*\"([A-Z0-9]+)\"",
        r"Conf\.\s*No\.\s*(\d+)",
        r"Num[ée]ro de r[ée]servation\s*:?\s*(\d+)",
        r"Invoice No\.\s*(\d+)",
        r"Facture no\s*:\s*(\d+)",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return ""


def source_type(path, text):
    hay = f"{path.as_posix()} {text[:15000]}"
    if "Invoices_hotel" in path.parts:
        return "official"
    if re.search(r"(ceci n['’]est pas une facture|not an invoice|ne peut pas être utilisée pour demander le remboursement de la tva|cannot be used.*vat)", hay, re.I | re.S):
        return "non_official"
    if OFFICIAL_TERMS.search(hay):
        return "official"
    if NON_OFFICIAL_TERMS.search(hay):
        return "non_official"
    return "non_official"


def monday_of_week(d):
    return d - timedelta(days=d.weekday())


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    candidates = []
    reservation_candidates = []
    for root in INPUT_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            text = text_for(path)
            if not text or not is_geneva_city_stay(path, text):
                continue
            start, end, date_source = date_range_from_text(text)
            if not start or not end or end <= start:
                continue
            est = establishment_for(path, text)
            ref = reservation_ref(text)
            stype = source_type(path, text)
            reservation_candidates.append({
                "establishment": est,
                "stay_start": start,
                "stay_end": end,
                "ref": ref,
                "source_type": stype,
                "file": str(path.relative_to(ROOT)),
            })
            amount, amount_source = extract_amount(path, text)
            if amount is None:
                continue
            candidates.append({
                "establishment": est,
                "amount_chf": q2(amount),
                "invoice_date": invoice_date_from_filename(path),
                "stay_start": start,
                "stay_end": end,
                "nights": (end - start).days,
                "ref": ref,
                "source_type": stype,
                "amount_source": amount_source,
                "date_source": date_source,
                "file": str(path.relative_to(ROOT)),
            })

    # Dedupe by stay. Prefer official documents over non-official ones, then
    # prefer rows with a reference and stable source paths.
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
        row["avg_chf_per_night"] = q2(row["amount_chf"] / Decimal(row["nights"]))

    monthly = defaultdict(lambda: {"total": Decimal("0.00"), "official": Decimal("0.00"), "non_official": Decimal("0.00"), "nights": 0, "count": 0})
    monthly_est = defaultdict(lambda: {"total": Decimal("0.00"), "official": Decimal("0.00"), "non_official": Decimal("0.00")})
    annual = defaultdict(lambda: {"total": Decimal("0.00"), "official": Decimal("0.00"), "non_official": Decimal("0.00"), "nights": 0, "count": 0})
    annual_est = defaultdict(lambda: {"total": Decimal("0.00"), "official": Decimal("0.00"), "non_official": Decimal("0.00")})
    for row in rows:
        month = row["month"]
        year = row["year"]
        source_bucket = row["source_type"]
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
        subtotal = q2(monthly[month]["total"])
        avg = q2(subtotal / Decimal(monthly[month]["nights"])) if monthly[month]["nights"] else Decimal("0.00")
        change = "" if prev_total is None else q2(subtotal - prev_total)
        change_pct = "" if prev_total in (None, Decimal("0.00")) else q2(((subtotal - prev_total) / prev_total) * Decimal("100"))
        for (m, est), data in sorted(monthly_est.items()):
            if m == month:
                monthly_rows.append({
                    "month": month,
                    "establishment": est,
                    "total_chf": f"{q2(data['total']):.2f}",
                    "official_chf": f"{q2(data['official']):.2f}",
                    "non_official_chf": f"{q2(data['non_official']):.2f}",
                    "month_subtotal_chf": f"{subtotal:.2f}",
                    "month_official_chf": f"{q2(monthly[month]['official']):.2f}",
                    "month_non_official_chf": f"{q2(monthly[month]['non_official']):.2f}",
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
        total = q2(annual[year]["total"])
        avg = q2(total / Decimal(annual[year]["nights"])) if annual[year]["nights"] else Decimal("0.00")
        for (y, est), data in sorted(annual_est.items()):
            if y == year:
                annual_rows.append({
                    "year": year,
                    "establishment": est,
                    "total_chf": f"{q2(data['total']):.2f}",
                    "official_chf": f"{q2(data['official']):.2f}",
                    "non_official_chf": f"{q2(data['non_official']):.2f}",
                    "year_subtotal_chf": f"{total:.2f}",
                    "year_official_chf": f"{q2(annual[year]['official']):.2f}",
                    "year_non_official_chf": f"{q2(annual[year]['non_official']):.2f}",
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
        cursor = monday_of_week(row["stay_start"])
        last = monday_of_week(row["stay_end"] - timedelta(days=1))
        while cursor <= last:
            covered_weeks.add(cursor)
            cursor += timedelta(days=7)
    empty_weeks = []
    if deduped_reservations:
        first_week = monday_of_week(min(r["stay_start"] for r in deduped_reservations.values()))
        last_week = monday_of_week(max(r["stay_end"] - timedelta(days=1) for r in deduped_reservations.values()))
        cursor = first_week
        while cursor <= last_week:
            if cursor not in covered_weeks:
                iso = cursor.isocalendar()
                empty_weeks.append({"iso_year": iso.year, "iso_week": iso.week, "week_start": cursor.isoformat(), "week_end": (cursor + timedelta(days=6)).isoformat()})
            cursor += timedelta(days=7)
    write_csv(EMPTY_WEEKS_CSV, empty_weeks, ["iso_year", "iso_week", "week_start", "week_end"])

    total = sum((row["amount_chf"] for row in rows), Decimal("0.00"))
    official = sum((row["amount_chf"] for row in rows if row["source_type"] == "official"), Decimal("0.00"))
    non_official = total - official
    nights = sum(row["nights"] for row in rows)
    print(f"TOTAL_CHF={q2(total):.2f}")
    print(f"OFFICIAL_CHF={q2(official):.2f}")
    print(f"NON_OFFICIAL_CHF={q2(non_official):.2f}")
    print(f"OFFICIAL_SHARE_PCT={q2((official / total) * Decimal('100')) if total else Decimal('0.00'):.2f}")
    print(f"NON_OFFICIAL_SHARE_PCT={q2((non_official / total) * Decimal('100')) if total else Decimal('0.00'):.2f}")
    print(f"DEDUPED_STAYS_WITH_AMOUNT={len(rows)}")
    print(f"DUPLICATE_AMOUNT_ROWS_REMOVED={len(duplicates)}")
    print(f"NIGHTS={nights}")
    print(f"AVG_CHF_PER_NIGHT={q2(total / Decimal(nights)) if nights else Decimal('0.00'):.2f}")
    print(f"DEDUPED_RESERVATIONS_WITH_DATES={len(deduped_reservations)}")
    print(f"EMPTY_WEEKS={len(empty_weeks)}")
    print(f"DETAIL_CSV={DETAIL_CSV.relative_to(ROOT)}")
    print(f"MONTHLY_CSV={MONTHLY_CSV.relative_to(ROOT)}")
    print(f"ANNUAL_CSV={ANNUAL_CSV.relative_to(ROOT)}")
    print(f"EMPTY_WEEKS_CSV={EMPTY_WEEKS_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
