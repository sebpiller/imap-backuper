#!/usr/bin/env python3
import csv
import html
import re
import subprocess
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path.cwd()
INPUT_ROOTS = [ROOT / "Invoices_hotel", ROOT / "maybe"]
DETAIL_CSV = ROOT / "geneva_hotel_amounts_detail.csv"
SUMMARY_CSV = ROOT / "geneva_hotel_amounts_by_month_establishment.csv"

GENEVA_TERMS = re.compile(r"\b(gen[eè]ve|geneva)\b", re.I)
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


def run_text_command(args):
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=20,
        )
    except Exception:
        return ""
    return result.stdout.decode("utf-8", errors="ignore")


def is_pdf(path):
    try:
        return path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def extension_for(path):
    if is_pdf(path):
        return "pdf"
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"html", "htm"}:
        return "html"
    if suffix == "txt":
        return "txt"
    return suffix


def strip_html(raw):
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def text_for(path):
    ext = extension_for(path)
    if ext == "pdf":
        return run_text_command(["pdftotext", str(path), "-"])
    if ext in {"html", "txt"}:
        try:
            raw = path.read_text(errors="ignore")
        except OSError:
            return ""
        return strip_html(raw) if ext == "html" else raw
    return ""


def normalize_space(text):
    return re.sub(r"\s+", " ", text).strip()


def money_to_decimal(value):
    cleaned = value.replace("'", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_filename_date(path):
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    return m.group(1) if m else ""


def establishment_for(path, text):
    hay = f"{path.as_posix()} {text[:3000]}".lower()
    for key, name in KNOWN_GENEVA_ESTABLISHMENTS:
        if key in hay:
            return name
    m = re.search(r"20\d{2}-\d{2}-\d{2}-(.+?)\.[^.]+$", path.name)
    return m.group(1) if m else path.stem


def is_geneva_stay(path, text):
    hay = f"{path.as_posix()} {text[:8000]}"
    if not GENEVA_TERMS.search(hay):
        return False
    lower_path = path.as_posix().lower()
    # These are Geneva-area names, but outside the city of Geneva.
    if "ramada encore" in lower_path or "nash airport hotel" in lower_path or "petit-lancy" in lower_path or " lancy" in lower_path:
        return False
    if "hotel residence geneve" in lower_path:
        return True
    if any(key in lower_path for key, _ in KNOWN_GENEVA_ESTABLISHMENTS):
        return True
    return bool(re.search(r"\b(chambre|room|stay|séjour|sejour|nuit|reservation|réservation|invoice|facture|receipt)\b", hay, re.I))


def has_invoice_signal(path, text):
    hay = f"{path.as_posix()} {text[:12000]}"
    if path.parts and "Invoices_hotel" in path.parts:
        return True
    if NON_INVOICE_TERMS.search(hay):
        return False
    if "airbnb" in path.as_posix().lower():
        return bool(re.search(
            r"(votre reçu d['’]airbnb|numéro du reçu|receipt number|your receipt)",
            hay,
            re.I,
        ))
    return bool(re.search(
        r"(\bfacture\b|\binvoice\b|\bfolio\b|\btotal\s+ttc\b|"
        r"receipt number|your receipt|votre reçu)",
        hay,
        re.I,
    ))


def amounts_after_label(text, label_pattern, window=220):
    out = []
    for m in re.finditer(label_pattern, text, re.I):
        snippet = text[m.end():m.end() + window]
        for num in re.findall(r"(?<!\d)(\d{1,4}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))(?:\s*)(?:CHF|€|EUR)?", snippet):
            val = money_to_decimal(num)
            if val is not None:
                out.append(val)
    return out


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


def extract_amount(path, text):
    flat = normalize_space(text)
    name = path.name.lower()

    # Precise invoice totals seen in confirmed hotel invoices.
    label_patterns = [
        r"montant total ttc",
        r"\btotal incl\.?\s*tva\b",
        r"\bgrand total\b",
        r"\btotal\s+paid\b",
        r"\bamount paid\b",
        r"\btotal\s+ttc\b",
        r"\btotal\b",
    ]

    if "primadom" in name or "primadom" in flat.lower():
        vals = amounts_on_labeled_lines(text, r"montant total ttc")
        if not vals:
            vals = amounts_after_label(flat, r"montant total ttc", 80)
        if vals:
            return vals[0], "Montant total TTC"

    if "starling" in name or "shresidence" in flat.lower():
        vals = amounts_on_labeled_lines(text, r"total incl\.?\s*tva")
        if not vals:
            vals = amounts_after_label(flat, r"total incl\.?\s*tva", 160)
        if vals:
            return vals[-1], "Total incl. TVA"
        vals = amounts_on_labeled_lines(text, r"\btotal\b")
        if not vals:
            vals = amounts_after_label(flat, r"\btotal\b", 180)
        vals = [v for v in vals if v != Decimal("0.00")]
        if vals:
            return max(vals), "Total"

    vals = amounts_on_labeled_lines(text, r"(montant payé|amount paid|total\s*\(chf\)|total paid)")
    vals = [v for v in vals if v != Decimal("0.00")]
    if vals:
        return vals[-1], "receipt total line"

    for label in label_patterns:
        vals = amounts_on_labeled_lines(text, label)
        if not vals:
            vals = amounts_after_label(flat, label, 180)
        vals = [v for v in vals if v != Decimal("0.00")]
        if vals:
            return max(vals), label

    # Airbnb/Booking receipts sometimes only expose a currency-prefixed total.
    prefixed = []
    for num in re.findall(r"(?:CHF|€|EUR)\s*(\d{1,4}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))", flat, re.I):
        val = money_to_decimal(num)
        if val is not None:
            prefixed.append(val)
    if prefixed:
        return max(prefixed), "currency-prefixed amount"

    suffixed = []
    for num in re.findall(r"(?<!\d)(\d{1,4}(?:[ '\u00a0]\d{3})*(?:[.,]\d{2}))\s*(?:CHF|€|EUR)", flat, re.I):
        val = money_to_decimal(num)
        if val is not None:
            suffixed.append(val)
    if suffixed:
        return max(suffixed), "currency-suffixed amount"

    return None, "no amount found"


def main():
    rows = []
    skipped = []
    for root in INPUT_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            text = text_for(path)
            if not text:
                skipped.append((path, "no text"))
                continue
            if not is_geneva_stay(path, text):
                continue
            if not has_invoice_signal(path, text):
                skipped.append((path, "geneva stay but no invoice signal"))
                continue
            amount, amount_source = extract_amount(path, text)
            if amount is None:
                skipped.append((path, "geneva invoice-like but no amount"))
                continue
            date = parse_filename_date(path)
            month = date[:7] if date else "unknown"
            rows.append({
                "month": month,
                "establishment": establishment_for(path, text),
                "amount_chf": f"{amount:.2f}",
                "date": date,
                "file": str(path.relative_to(ROOT)),
                "amount_source": amount_source,
            })

    totals = defaultdict(Decimal)
    for row in rows:
        totals[(row["month"], row["establishment"])] += Decimal(row["amount_chf"])

    with DETAIL_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["month", "establishment", "amount_chf", "date", "file", "amount_source"])
        writer.writeheader()
        writer.writerows(rows)

    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["month", "establishment", "total_chf"])
        writer.writeheader()
        for (month, establishment), total in sorted(totals.items()):
            writer.writerow({"month": month, "establishment": establishment, "total_chf": f"{total:.2f}"})

    print("SUMMARY")
    for (month, establishment), total in sorted(totals.items()):
        print(f"{month}\t{establishment}\t{total:.2f}")
    print(f"DETAIL_ROWS={len(rows)}")
    print(f"DETAIL_CSV={DETAIL_CSV.relative_to(ROOT)}")
    print(f"SUMMARY_CSV={SUMMARY_CSV.relative_to(ROOT)}")
    print("SKIPPED_GENEVA_RELEVANT")
    for path, reason in skipped[:200]:
        print(f"{reason}\t{path.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
