#!/usr/bin/env python3
import csv
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path


ROOT = Path.cwd()
CONFIRMED_ROOT = ROOT / "Invoices_hotel"
MAYBE_ROOT = ROOT / "maybe"
MANIFEST = ROOT / "Invoices_hotel_manifest.csv"

SCAN_ROOTS = [
    ROOT / "all-mails",
    ROOT / "1st shot" / "all-mails",
    ROOT / "1st shot" / "pdfs" / "all-mails",
    ROOT / "1st shot" / "hotels" / "pdfs" / "all-mails",
    ROOT / "1st shot" / "final",
]

ACCOMMODATION_PATH_TERMS = re.compile(
    r"(shresidence|primadom|grupohotusa|civitfun|freetobook|ajoiespa|"
    r"booking\.com|property\.booking\.com|airbnb\.com|hotelcard|"
    r"wyndhamhotels|ramada|starling|nash airport hotel|riad o ly|"
    r"ibis budget|design hotel f6|hotel des tourelles|green-marmot|"
    r"green marmot|aparthotel|hotel|hôtel)",
    re.I,
)

HOTEL_TERMS = re.compile(
    r"\b("
    r"hotel|hôtel|residence|résidence|aparthotel|suite|spa privatif|capsule hotel|"
    r"booking\.com|freetobook|airbnb|wyndham|ramada|riad|hostel|lodg|"
    r"accommodation|hébergement|hebergement|chambre|zimmer|gast|séjour|sejour|stay|"
    r"arrivée|arrivee|anreise|departure|départ|depart|abreise|check[- ]?in|nuitée|nuitee|reservierung"
    r")\b",
    re.I,
)

INVOICE_TERMS = re.compile(
    r"\b("
    r"invoice|facture|rechnung|receipt|reçu|recu|folio|e[- ]?folio|"
    r"pro[- ]?forma folio|tax invoice|booking invoice|"
    r"paid|payment|paiement|montant payé|montant paye|zahlungsübersicht|"
    r"city tax|taxe de séjour|taxe de sejour|vat|tva"
    r")\b",
    re.I,
)

STRONG_INVOICE_TERMS = re.compile(
    r"(booking invoice|pro[- ]?forma folio|e[- ]?folio|invoice no\.?|"
    r"facture no|facture n|rechnung:|tax invoice|folio)",
    re.I,
)

CONFIRMATION_TERMS = re.compile(
    r"(confirmation|reservation|réservation|details-de-la-reservation|"
    r"détails-de-la-réservation|conf letter|guest_confirmation)",
    re.I,
)

NEGATIVE_TERMS = re.compile(
    r"(ceci n['’]est pas une facture|not an invoice|cannot be used.*vat|"
    r"ne peut pas être utilisée pour demander le remboursement de la tva)",
    re.I | re.S,
)

MARKETING_OR_REVIEW = re.compile(
    r"(newsletter|offre spéciale|promo|se désinscrire|unsubscribe|"
    r"donnez votre avis|laisser un commentaire|review your stay|"
    r"évaluez votre séjour|happy new year|bonne année)",
    re.I,
)

MONTHS = {
    "jan": "01", "janv": "01", "january": "01", "janvier": "01", "januar": "01",
    "feb": "02", "févr": "02", "fevr": "02", "february": "02", "février": "02", "fevrier": "02", "februar": "02",
    "mar": "03", "march": "03", "mars": "03", "märz": "03", "maerz": "03",
    "apr": "04", "avr": "04", "april": "04", "avril": "04",
    "may": "05", "mai": "05",
    "jun": "06", "june": "06", "juin": "06", "juni": "06",
    "jul": "07", "july": "07", "juillet": "07", "juli": "07",
    "aug": "08", "aoû": "08", "aou": "08", "august": "08", "août": "08", "aout": "08",
    "sep": "09", "sept": "09", "september": "09", "septembre": "09",
    "oct": "10", "october": "10", "octobre": "10", "okt": "10", "oktober": "10",
    "nov": "11", "november": "11", "novembre": "11",
    "dec": "12", "déc": "12", "december": "12", "décembre": "12", "decembre": "12", "dez": "12", "dezember": "12",
}

KNOWN_FIRMS = [
    ("primadom", "Primadom Aparthotel"),
    ("starling", "Starling Hotel Residence Geneve"),
    ("shresidence", "Starling Hotel Residence Geneve"),
    ("grupohotusa", "Ikonik Lisboa"),
    ("ikonik", "Ikonik Lisboa"),
    ("green marmot", "Green Marmot Capsule Hotel Geneve"),
    ("green-marmot", "Green Marmot Capsule Hotel Geneve"),
    ("civitfun", "Green Marmot Capsule Hotel Geneve"),
    ("ajoiespa", "AjoieSpa"),
    ("freetobook", "AjoieSpa"),
    ("nash airport hotel", "Nash Airport Hotel"),
    ("riad o ly", "Riad O LY"),
    ("ibis budget", "ibis budget Geneve Petit-Lancy"),
    ("design hotel f6", "Design Hotel f6"),
    ("hotel des tourelles", "Hotel des Tourelles"),
    ("ramada encore", "Ramada Encore by Wyndham Geneva"),
    ("wyndham", "Ramada Encore by Wyndham Geneva"),
    ("airbnb", "Airbnb"),
    ("booking.com", "Booking.com"),
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
    name = path.name.lower()
    if is_pdf(path):
        return "pdf"
    if name.endswith(".html") or name.endswith(".htm"):
        return "html"
    if name.endswith(".txt"):
        return "txt"
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"pdf", "html", "htm", "txt"}:
        return "html" if suffix == "htm" else suffix
    return suffix or "dat"


def strip_html(raw):
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def text_for(path):
    ext = extension_for(path)
    if ext == "pdf":
        text = run_text_command(["pdftotext", str(path), "-"])
        return re.sub(r"\s+", " ", text).strip()
    if ext in {"html", "txt"}:
        try:
            raw = path.read_text(errors="ignore")
        except OSError:
            return ""
        return strip_html(raw) if ext == "html" else re.sub(r"\s+", " ", raw).strip()
    return ""


def normalized(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def sanitize(value):
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .-_")
    return value or "Unknown"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def year_from_two_digits(value):
    n = int(value)
    return 2000 + n if n < 70 else 1900 + n


def parse_date_from_text_or_path(text, path):
    patterns = [
        r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b",
        r"\b(0?[1-9]|[12]\d|3[01])[-/.](0?[1-9]|1[0-2])[-/.](20\d{2}|\d{2})\b",
        r"\b(0?[1-9]|[12]\d|3[01])\s+([A-Za-zÀ-ÿ]{3,10})\.?\s+(20\d{2}|\d{2})\b",
    ]

    for hay in [text[:5000], path.name, path.as_posix()]:
        for pat in patterns:
            m = re.search(pat, hay, re.I)
            if not m:
                continue
            parts = m.groups()
            if pat.startswith(r"\b(20"):
                y, mo, d = int(parts[0]), int(parts[1]), int(parts[2])
            elif parts[1].isdigit():
                d, mo, y = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts[2]) == 4 else year_from_two_digits(parts[2])
            else:
                d = int(parts[0])
                mo = MONTHS.get(normalized(parts[1])[:4]) or MONTHS.get(normalized(parts[1])[:3])
                if not mo:
                    continue
                mo = int(mo)
                y = int(parts[2]) if len(parts[2]) == 4 else year_from_two_digits(parts[2])
            if 2018 <= y <= 2035 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"

    parts = path.parts
    for i, part in enumerate(parts):
        if re.fullmatch(r"20\d{2}", part) and i + 1 < len(parts) and re.fullmatch(r"\d{1,2}", parts[i + 1]):
            return f"{int(part):04d}-{int(parts[i + 1]):02d}-01"
    return "unknown-date"


def firm_from_text_or_path(text, path):
    hay = normalized(f"{path.as_posix()} {text[:3000]}")
    for key, firm in KNOWN_FIRMS:
        if normalized(key) in hay:
            return firm

    m = re.search(r"\b(Starling Hotel Residence Genève|Primadom Aparthotel|Nash Airport Hotel|Riad O LY|Design Hotel f6|Hotel des Tourelles|Ramada Encore by Wyndham Geneva)\b", text, re.I)
    if m:
        return m.group(1).replace("Genève", "Geneve")

    return path.parts[-4] if len(path.parts) >= 4 else path.stem


def is_interesting_file(path):
    ext = extension_for(path)
    if ext in {"pdf", "html", "txt"}:
        return True
    return False


def classify(path, text):
    full = f"{path.as_posix()} {text}"
    full_norm = normalized(full)
    path_norm = normalized(path.as_posix())

    if not ACCOMMODATION_PATH_TERMS.search(path.as_posix()):
        return None, "source/path is not an accommodation provider"

    if not HOTEL_TERMS.search(full):
        return None, "no hotel/stay signal in path or text"

    if MARKETING_OR_REVIEW.search(full) and not INVOICE_TERMS.search(full):
        return None, "marketing/review without invoice signal"

    has_invoice = bool(INVOICE_TERMS.search(full))
    has_strong_invoice = bool(STRONG_INVOICE_TERMS.search(full))
    has_negative = bool(NEGATIVE_TERMS.search(full))
    has_confirmation = bool(CONFIRMATION_TERMS.search(full))
    ext = extension_for(path)

    if "1st shot/final" in path.as_posix():
        return "confirmed", "prior curated hotel invoice"

    if ext == "pdf" and has_confirmation and not has_strong_invoice:
        return "maybe", "stay-related confirmation/reservation"

    if ext == "pdf" and has_strong_invoice and not has_negative:
        return "confirmed", "PDF has hotel/stay and strong invoice/folio terms"

    if "booking invoice" in full_norm and not has_negative:
        return "confirmed", "document says Booking Invoice"

    if has_negative:
        return "maybe", "stay-related receipt explicitly says it is not an invoice"

    if has_invoice:
        return "maybe", "stay-related payment/receipt signal but not a clear invoice"

    if has_confirmation:
        return "maybe", "stay-related confirmation/reservation"

    return None, "not invoice-like enough"


def unique_destination(base_dir, date, firm, ext):
    year = date[:4] if re.match(r"20\d{2}-\d{2}-\d{2}", date) else "unknown-year"
    month = date[5:7] if re.match(r"20\d{2}-\d{2}-\d{2}", date) else "unknown-month"
    folder = base_dir / year / month
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{date}-{sanitize(firm)}"
    candidate = folder / f"{stem}.{ext}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem}-{n}.{ext}"
        n += 1
    return candidate


def iter_files():
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if CONFIRMED_ROOT in path.parents or MAYBE_ROOT in path.parents:
                continue
            if is_interesting_file(path):
                yield path


def main():
    CONFIRMED_ROOT.mkdir(exist_ok=True)
    MAYBE_ROOT.mkdir(exist_ok=True)

    rows = []
    seen = {}
    copied = {"confirmed": 0, "maybe": 0}
    considered = 0

    for path in iter_files():
        considered += 1
        text = text_for(path)
        bucket, reason = classify(path, text)
        if not bucket:
            continue

        digest = sha256(path)
        if digest in seen:
            rows.append({
                "bucket": "duplicate",
                "destination": seen[digest],
                "source": str(path),
                "date": "",
                "firm": "",
                "reason": f"duplicate of {seen[digest]}",
                "sha256": digest,
            })
            continue

        date = parse_date_from_text_or_path(text, path)
        firm = firm_from_text_or_path(text, path)
        ext = extension_for(path)
        base = CONFIRMED_ROOT if bucket == "confirmed" else MAYBE_ROOT
        dest = unique_destination(base, date, firm, ext)
        shutil.copy2(path, dest)
        seen[digest] = str(dest.relative_to(ROOT))
        copied[bucket] += 1
        rows.append({
            "bucket": bucket,
            "destination": str(dest.relative_to(ROOT)),
            "source": str(path),
            "date": date,
            "firm": firm,
            "reason": reason,
            "sha256": digest,
        })

    with MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["bucket", "destination", "source", "date", "firm", "reason", "sha256"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"considered={considered}")
    print(f"confirmed={copied['confirmed']}")
    print(f"maybe={copied['maybe']}")
    print(f"manifest={MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
