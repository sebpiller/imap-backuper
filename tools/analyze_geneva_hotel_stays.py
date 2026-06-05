#!/usr/bin/env python3
import csv
import html
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


ROOT = Path.cwd()
INPUT_ROOTS = [ROOT / "Invoices_hotel", ROOT / "maybe"]
DETAIL_CSV = ROOT / "geneva_hotel_stays_dedup_detail.csv"
MONTHLY_CSV = ROOT / "geneva_hotel_monthly_subtotals.csv"
EMPTY_WEEKS_CSV = ROOT / "geneva_hotel_weeks_without_reservation.csv"

GENEVA_TERMS = re.compile(r"\b(gen[eè]ve|geneva)\b", re.I)
NON_CITY_TERMS = re.compile(r"(petit[- ]lancy|grand[- ]lancy|\blancy\b|meyrin|cointrin|nash airport hotel|ramada encore)", re.I)
NON_INVOICE_TERMS = re.compile(
    r"(gratuit pour vous|transport card|nouveau message|assistant booking|"
    r"review your stay|donnez votre avis|ceci n['’]est pas une facture|not an invoice|"
    r"ne peut pas être utilisée pour demander le remboursement de la tva)",
    re.I,
)
KNOWN_GENEVA_ESTABLISHMENTS = [
    ("primadom", "Primadom Aparthotel"),
    ("starling", "Starling Hotel Residence Geneve"),
    ("shresidence", "Starling Hotel Residence Geneve"),
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


def establishment_for(path, text):
    hay = f"{path.as_posix()} {text[:4000]}".lower()
    for key, name in KNOWN_GENEVA_ESTABLISHMENTS:
        if key in hay:
            return name
    m = re.search(r"20\d{2}-\d{2}-\d{2}-(.+?)\.[^.]+$", path.name)
    return m.group(1) if m else path.stem


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


def date_range_from_text(text):
    hay = flat(text)

    # Structured Airbnb/Schema.org reservation metadata, including nested JSON
    # blocks that are awkward to parse with a simple regex.
    m = re.search(r"\"checkinDate\"\s*:\s*\"(20\d{2}-\d{2}-\d{2})T[^\"]*\".*?\"checkoutDate\"\s*:\s*\"(20\d{2}-\d{2}-\d{2})T", text, re.S)
    if m:
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2)), "json checkin/checkout fields"

    # Structured Airbnb reservation metadata.
    for m in re.finditer(r"\{[^{}]*\"@type\"\s*:\s*\"LodgingReservation\".*?\}", text, re.S):
        try:
            obj = json.loads(m.group(0))
        except Exception:
            continue
        if obj.get("checkinDate") and obj.get("checkoutDate"):
            return date.fromisoformat(obj["checkinDate"][:10]), date.fromisoformat(obj["checkoutDate"][:10]), "json checkin/checkout"

    # Primadom.
    m = re.search(r"S[ée]jour\s+du\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s+au\s*:?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", hay, re.I)
    if m:
        return parse_dmy(m.group(1)), parse_dmy(m.group(2)), "Séjour du/au"

    # Starling e-folio.
    m = re.search(r"(\d{1,2}[.]\d{1,2}[.]\d{2})\s*-\s*(\d{1,2}[.]\d{1,2}[.]\d{2})", hay)
    if m:
        return parse_dmy(m.group(1)), parse_dmy(m.group(2)), "Dates of Stay"

    # Airbnb visible receipt dates.
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


def has_invoice_signal(path, text):
    hay = f"{path.as_posix()} {text[:15000]}"
    if "Invoices_hotel" in path.parts:
        return True
    if NON_INVOICE_TERMS.search(hay):
        return False
    if "airbnb" in path.as_posix().lower():
        return bool(re.search(r"(votre reçu d['’]airbnb|numéro du reçu|receipt number|your receipt)", hay, re.I))
    return bool(re.search(r"(\bfacture\b|\binvoice\b|\bfolio\b|\btotal\s+ttc\b|receipt number|your receipt|votre reçu)", hay, re.I))


def amounts_on_labeled_lines(text, label_pattern):
    out = []
    for line in text.splitlines():
        if not re.search(label_pattern, line, re.I):
            continue
        for num in re.findall(r"(?<![\d.,])(\d{1,4}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))(?![\d.,])", line):
            val = money_to_decimal(num)
            if val is not None:
                out.append(val)
    return out


def amounts_after_label(text, label_pattern, window=220):
    out = []
    compact = flat(text)
    for m in re.finditer(label_pattern, compact, re.I):
        snippet = compact[m.end():m.end() + window]
        for num in re.findall(r"(?<!\d)(\d{1,4}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))(?:\s*)(?:CHF|EUR|€)?", snippet):
            val = money_to_decimal(num)
            if val is not None:
                out.append(val)
    return out


def extract_amount(path, text):
    lower = f"{path.name} {text[:4000]}".lower()
    if "primadom" in lower:
        vals = amounts_on_labeled_lines(text, r"montant total ttc") or amounts_after_label(text, r"montant total ttc", 80)
        if vals:
            return vals[0], "Montant total TTC"
    if "starling" in lower or "shresidence" in lower:
        vals = amounts_on_labeled_lines(text, r"total incl\.?\s*tva") or amounts_after_label(text, r"total incl\.?\s*tva", 160)
        if vals:
            return vals[-1], "Total incl. TVA"
    vals = amounts_on_labeled_lines(text, r"(montant payé|amount paid|total\s*\(chf\)|total paid)")
    vals = [v for v in vals if v != Decimal("0.00")]
    if vals:
        return vals[-1], "receipt total line"
    for label in [r"montant total ttc", r"total incl\.?\s*tva", r"grand total", r"total paid", r"amount paid", r"total ttc", r"\btotal\b"]:
        vals = amounts_on_labeled_lines(text, label) or amounts_after_label(text, label, 180)
        vals = [v for v in vals if v != Decimal("0.00")]
        if vals:
            return max(vals), label
    return None, "no amount"


def is_geneva_city_stay(path, text):
    hay = f"{path.as_posix()} {text[:12000]}"
    return bool(GENEVA_TERMS.search(hay)) and not bool(NON_CITY_TERMS.search(hay))


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


def monday_of_week(d):
    return d - timedelta(days=d.weekday())


def main():
    invoice_candidates = []
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
            est = establishment_for(path, text)
            start, end, date_source = date_range_from_text(text)
            ref = reservation_ref(text)
            if start and end and end > start:
                reservation_candidates.append({
                    "establishment": est,
                    "stay_start": start,
                    "stay_end": end,
                    "nights": (end - start).days,
                    "ref": ref,
                    "date_source": date_source,
                    "file": str(path.relative_to(ROOT)),
                })
            if not has_invoice_signal(path, text):
                continue
            amount, amount_source = extract_amount(path, text)
            if amount is None:
                continue
            invoice_candidates.append({
                "establishment": est,
                "amount_chf": q2(amount),
                "invoice_date": invoice_date_from_filename(path),
                "stay_start": start,
                "stay_end": end,
                "nights": (end - start).days if start and end and end > start else 0,
                "ref": ref,
                "amount_source": amount_source,
                "date_source": date_source,
                "file": str(path.relative_to(ROOT)),
            })

    deduped_invoices = {}
    duplicates = []
    for row in invoice_candidates:
        if row["stay_start"] and row["stay_end"]:
            key = (row["establishment"], row["stay_start"], row["stay_end"], row["amount_chf"])
        elif row["ref"]:
            key = (row["establishment"], row["ref"], row["amount_chf"])
        else:
            key = (row["establishment"], row["invoice_date"], row["amount_chf"], row["file"])
        if key in deduped_invoices:
            duplicates.append(row)
            continue
        deduped_invoices[key] = row
    invoice_rows = sorted(deduped_invoices.values(), key=lambda r: (r["stay_start"] or date.max, r["invoice_date"], r["establishment"], r["file"]))

    deduped_reservations = {}
    for row in reservation_candidates:
        key = (row["establishment"], row["stay_start"], row["stay_end"], row["ref"])
        if key not in deduped_reservations:
            deduped_reservations[key] = row
    reservation_rows = list(deduped_reservations.values())

    monthly = defaultdict(lambda: {"total": Decimal("0.00"), "nights": 0, "count": 0})
    monthly_est = defaultdict(Decimal)
    for row in invoice_rows:
        month = row["stay_start"].strftime("%Y-%m") if row["stay_start"] else (row["invoice_date"][:7] if row["invoice_date"] else "unknown")
        row["month"] = month
        monthly[month]["total"] += row["amount_chf"]
        monthly[month]["nights"] += row["nights"]
        monthly[month]["count"] += 1
        monthly_est[(month, row["establishment"])] += row["amount_chf"]

    prev_total = None
    with MONTHLY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["month", "establishment", "total_chf", "month_subtotal_chf", "invoice_count", "nights", "avg_chf_per_night", "change_vs_previous_month_chf", "change_vs_previous_month_pct"])
        writer.writeheader()
        for month in sorted(monthly):
            subtotal = q2(monthly[month]["total"])
            nights = monthly[month]["nights"]
            avg = q2(subtotal / Decimal(nights)) if nights else Decimal("0.00")
            change = "" if prev_total is None else q2(subtotal - prev_total)
            change_pct = "" if prev_total in (None, Decimal("0.00")) else q2(((subtotal - prev_total) / prev_total) * Decimal("100"))
            first = True
            for (m, est), total in sorted(monthly_est.items()):
                if m != month:
                    continue
                writer.writerow({
                    "month": month,
                    "establishment": est,
                    "total_chf": f"{q2(total):.2f}",
                    "month_subtotal_chf": f"{subtotal:.2f}" if first else "",
                    "invoice_count": monthly[month]["count"] if first else "",
                    "nights": nights if first else "",
                    "avg_chf_per_night": f"{avg:.2f}" if first else "",
                    "change_vs_previous_month_chf": f"{change:.2f}" if change != "" and first else "",
                    "change_vs_previous_month_pct": f"{change_pct:.2f}" if change_pct != "" and first else "",
                })
                first = False
            prev_total = subtotal

    with DETAIL_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["month", "establishment", "amount_chf", "stay_start", "stay_end", "nights", "avg_chf_per_night", "invoice_date", "ref", "file", "amount_source", "date_source"])
        writer.writeheader()
        for row in invoice_rows:
            nights = row["nights"]
            avg = q2(row["amount_chf"] / Decimal(nights)) if nights else Decimal("0.00")
            writer.writerow({
                "month": row["month"],
                "establishment": row["establishment"],
                "amount_chf": f"{row['amount_chf']:.2f}",
                "stay_start": row["stay_start"].isoformat() if row["stay_start"] else "",
                "stay_end": row["stay_end"].isoformat() if row["stay_end"] else "",
                "nights": nights,
                "avg_chf_per_night": f"{avg:.2f}" if nights else "",
                "invoice_date": row["invoice_date"],
                "ref": row["ref"],
                "file": row["file"],
                "amount_source": row["amount_source"],
                "date_source": row["date_source"],
            })

    covered_weeks = set()
    for row in reservation_rows:
        cursor = monday_of_week(row["stay_start"])
        last = monday_of_week(row["stay_end"] - timedelta(days=1))
        while cursor <= last:
            covered_weeks.add(cursor)
            cursor += timedelta(days=7)

    empty_weeks = []
    if reservation_rows:
        first_week = monday_of_week(min(r["stay_start"] for r in reservation_rows))
        last_week = monday_of_week(max(r["stay_end"] - timedelta(days=1) for r in reservation_rows))
        cursor = first_week
        while cursor <= last_week:
            if cursor not in covered_weeks:
                iso = cursor.isocalendar()
                empty_weeks.append((iso.year, iso.week, cursor, cursor + timedelta(days=6)))
            cursor += timedelta(days=7)

    with EMPTY_WEEKS_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["iso_year", "iso_week", "week_start", "week_end"])
        writer.writeheader()
        for iso_year, iso_week, start, end in empty_weeks:
            writer.writerow({"iso_year": iso_year, "iso_week": iso_week, "week_start": start.isoformat(), "week_end": end.isoformat()})

    total = sum((row["amount_chf"] for row in invoice_rows), Decimal("0.00"))
    nights = sum(row["nights"] for row in invoice_rows)
    avg = q2(total / Decimal(nights)) if nights else Decimal("0.00")
    print(f"TOTAL_CHF={q2(total):.2f}")
    print(f"DEDUPED_INVOICES={len(invoice_rows)}")
    print(f"DUPLICATE_INVOICE_ROWS_REMOVED={len(duplicates)}")
    print(f"INVOICE_NIGHTS={nights}")
    print(f"AVG_CHF_PER_NIGHT={avg:.2f}")
    print(f"DEDUPED_RESERVATIONS_WITH_DATES={len(reservation_rows)}")
    print(f"EMPTY_WEEKS={len(empty_weeks)}")
    print(f"DETAIL_CSV={DETAIL_CSV.relative_to(ROOT)}")
    print(f"MONTHLY_CSV={MONTHLY_CSV.relative_to(ROOT)}")
    print(f"EMPTY_WEEKS_CSV={EMPTY_WEEKS_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
