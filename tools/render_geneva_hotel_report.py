#!/usr/bin/env python3
import csv
import html
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


ROOT = Path.cwd()
DETAIL_CSV = ROOT / "geneva_hotel_stays_inclusive_detail.csv"
MONTHLY_CSV = ROOT / "geneva_hotel_inclusive_monthly_subtotals.csv"
ANNUAL_CSV = ROOT / "geneva_hotel_inclusive_annual_subtotals.csv"
EMPTY_WEEKS_CSV = ROOT / "geneva_hotel_inclusive_weeks_without_reservation.csv"
REPORT = ROOT / "geneva_hotel_report.html"


TRANSCRIPT = [
    ("Utilisateur", "explain me these logs [application.log]"),
    ("Utilisateur", 'Now, search in the folder in every file and fetch all the invoices for hotel room reservations or other kind of stays. Export all these invoices to a new folder named "Invoices_hotel". Create folder hierarchy with "year/month" and rename the files with a pattern like "<invoice_date>-<firm>.<extension>". If you have any strong doubt about a file, move it in anothoer root folder named "maybe". Beware of file name collisions.'),
    ("Assistant", 'Done.\n\nI created the final export folders:\n\n- Invoices_hotel: 36 confirmed hotel/stay invoices\n- maybe: 348 doubtful stay-related files\n- Invoices_hotel_manifest.csv: audit trail with source path, destination, reason, date, firm, and hash\n\nThe files are organized as year/month and renamed like:\n\n2025-10-29-Ikonik Lisboa.pdf\n2026-06-04-Starling Hotel Residence Geneve.pdf\n\nFilename collisions were handled with suffixes like -2, -3, etc.\n\nI left the original mail/export files untouched and copied the matching files into the new folders. The maybe folder mostly contains Booking.com/Airbnb receipts, confirmations, or payment documents where the file is stay-related but not clearly an invoice. Some Booking.com receipts explicitly say they are not invoices, so I kept those out of the confirmed folder.'),
    ("Utilisateur", "Fais moi la somme de toutes factures que tu trouves dans hotel_invoices et dans maybe pour des séjours qui se seraient passé dans la ville de Genève."),
    ("Utilisateur", "Fais moi la somme de toutes factures que tu trouves dans hotel_invoices et dans maybe pour des séjours qui se seraient passé dans la ville de Genève. Groupe par mois et par établissement."),
    ("Assistant", "J’ai calculé le total strict des factures/reçus explicites pour des séjours à Genève depuis Invoices_hotel + maybe.\n\nTotal général: CHF 7’397.15\n\nJ’ai exclu les simples confirmations Booking.com/Airbnb, les e-mails transport card, les documents indiquant explicitement qu’ils ne sont pas une facture, et les séjours hors ville de Genève type Petit-Lancy/Ramada/Nash Airport."),
    ("Utilisateur", "Ajoute un sous-total pour chaque mois (somme de toutes les factures d'hôtelerie dans des établissements genevois pour un mois donné). Je veux également que tu t'assures que les séjours n'ont été comptabilisé qu'une seule mêne si certaines emails étaient à double. Je veux aussi que tu me listes toutes les semaines où aucune réservation n'a été trouvée à Genève. Calcule moi aussi le prix moyen de la nuitée, et les fluctuation que tu pourrais constater d'un mois à l'autre."),
    ("Assistant", "J’ai refait le calcul en dédupliquant par séjour, pas par e-mail: clé principale établissement + dates de séjour + montant, avec référence de réservation/facture quand disponible.\n\nRésultat strict: 35 factures/reçus comptabilisés, 66 nuitées, total CHF 7’397.15. Prix moyen global: CHF 112.08 / nuit.\n\nLes semaines sans réservation trouvée à Genève ont aussi été listées à partir des réservations datées trouvées, y compris des confirmations non facturées quand leurs dates étaient exploitables."),
    ("Utilisateur", "Prépare un fichier html qui affiche toutes ces données d'une façon agréable, et ajoute également une section cachée par défaut qui contient l'entiereté de notre discussion."),
    ("Assistant", "J’ai préparé geneva_hotel_report.html avec les tableaux, les sous-totaux mensuels, les semaines sans réservation, le détail des factures retenues et une section Discussion masquée par défaut."),
    ("Utilisateur", "Refais ce rapport en ajoutant des sous-totaux annuels."),
    ("Assistant", "J’ai mis à jour geneva_hotel_report.html avec une section de sous-totaux annuels."),
    ("Utilisateur", "Recalcule tous les chiffres en prenant en compte les documents qui stipulent qu'ils ne sont pas des factures, s'ils te permettent de déterminer plus de données. Même si ce ne sont pas des factures officielles, utilise les pour déterminer plus de séjours,puis recréé le rapport html en intégrant ces données tout en permettant de voir la part qui provient de documents non officiels."),
]


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def dec(value):
    return Decimal(value or "0")


def money(value):
    value = dec(value) if not isinstance(value, Decimal) else value
    return f"CHF {value:,.2f}".replace(",", "'")


def number(value):
    value = dec(value) if not isinstance(value, Decimal) else value
    return f"{value:,.2f}".replace(",", "'")


def pct(value):
    return f"{dec(value):+.2f}%"


def q2(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def e(value):
    return html.escape(str(value), quote=True)


def source_label(source_type):
    return "Officiel" if source_type == "official" else "Non officiel"


def source_chip(source_type):
    klass = "ok" if source_type == "official" else "warn"
    return f'<span class="chip {klass}">{source_label(source_type)}</span>'


def change_chip(row):
    value = row.get("change_vs_previous_month_pct", "")
    if not value:
        return ""
    klass = "ok" if dec(value) >= 0 else "down"
    return f'<span class="chip {klass}">{pct(value)}</span>'


def rowspanned_table(rows, key, columns):
    grouped = defaultdict(list)
    order = []
    for row in rows:
        if row[key] not in grouped:
            order.append(row[key])
        grouped[row[key]].append(row)

    out = []
    for group_key in order:
        group = grouped[group_key]
        span = len(group)
        for index, row in enumerate(group):
            cells = []
            for name, renderer, span_group in columns:
                if span_group and index:
                    continue
                attrs = f' rowspan="{span}"' if span_group and span > 1 else ""
                cells.append(f"<td{attrs}>{renderer(row)}</td>")
            out.append("<tr>" + "".join(cells) + "</tr>")
    return "\n".join(out)


def monthly_table(rows):
    columns = [
        ("month", lambda r: e(r["month"]), True),
        ("establishment", lambda r: e(r["establishment"]), False),
        ("total", lambda r: f'<span class="numwrap">{number(r["total_chf"])}</span>', False),
        ("official", lambda r: f'<span class="numwrap">{number(r["official_chf"])}</span>', False),
        ("non_official", lambda r: f'<span class="numwrap">{number(r["non_official_chf"])}</span>', False),
        ("subtotal", lambda r: f'<strong>{number(r["month_subtotal_chf"])}</strong>', True),
        ("count", lambda r: e(r["invoice_count"]), True),
        ("nights", lambda r: e(r["nights"]), True),
        ("avg", lambda r: number(r["avg_chf_per_night"]), True),
        ("change", change_chip, True),
    ]
    html_rows = rowspanned_table(rows, "month", columns)
    return f"""
        <table>
          <thead>
            <tr>
              <th>Mois</th>
              <th>Établissement</th>
              <th class="num">Total</th>
              <th class="num">Officiel</th>
              <th class="num">Non officiel</th>
              <th class="num">Sous-total mois</th>
              <th class="num">Séjours</th>
              <th class="num">Nuits</th>
              <th class="num">Moy. / nuit</th>
              <th class="num">Variation</th>
            </tr>
          </thead>
          <tbody>{html_rows}</tbody>
        </table>
    """


def annual_table(rows):
    columns = [
        ("year", lambda r: e(r["year"]), True),
        ("establishment", lambda r: e(r["establishment"]), False),
        ("total", lambda r: f'<span class="numwrap">{number(r["total_chf"])}</span>', False),
        ("official", lambda r: f'<span class="numwrap">{number(r["official_chf"])}</span>', False),
        ("non_official", lambda r: f'<span class="numwrap">{number(r["non_official_chf"])}</span>', False),
        ("subtotal", lambda r: f'<strong>{number(r["year_subtotal_chf"])}</strong>', True),
        ("count", lambda r: e(r["count"]), True),
        ("nights", lambda r: e(r["nights"]), True),
        ("avg", lambda r: number(r["avg_chf_per_night"]), True),
    ]
    html_rows = rowspanned_table(rows, "year", columns)
    return f"""
        <table>
          <thead>
            <tr>
              <th>Année</th>
              <th>Établissement</th>
              <th class="num">Total</th>
              <th class="num">Officiel</th>
              <th class="num">Non officiel</th>
              <th class="num">Sous-total annuel</th>
              <th class="num">Séjours</th>
              <th class="num">Nuits</th>
              <th class="num">Moy. / nuit</th>
            </tr>
          </thead>
          <tbody>{html_rows}</tbody>
        </table>
    """


def bars(rows):
    month_rows = []
    seen = set()
    for row in rows:
        month = row["month"]
        if month in seen:
            continue
        seen.add(month)
        total = dec(row["month_subtotal_chf"])
        official = dec(row["month_official_chf"])
        non_official = dec(row["month_non_official_chf"])
        month_rows.append((month, total, official, non_official))
    max_total = max((item[1] for item in month_rows), default=Decimal("1"))
    out = []
    for month, total, official, non_official in month_rows:
        width = q2((total / max_total) * Decimal("100")) if max_total else Decimal("0")
        official_share = q2((official / total) * Decimal("100")) if total else Decimal("0")
        non_official_share = Decimal("100") - official_share if total else Decimal("0")
        out.append(
            f'<div class="bar-row"><span>{e(month)}</span>'
            f'<div class="bar-track" style="--w:{width}%">'
            f'<div class="bar official" style="--segment:{official_share}%"></div>'
            f'<div class="bar unofficial" style="--segment:{non_official_share}%"></div>'
            f'</div><span class="num">{number(total)}</span></div>'
        )
    return "\n".join(out)


def weeks(rows):
    return "\n".join(
        f'<div class="week"><strong>{int(r["iso_year"])}-W{int(r["iso_week"]):02d}</strong><span>{e(r["week_start"])} au {e(r["week_end"])}</span></div>'
        for r in rows
    )


def detail_table(rows):
    out = []
    for r in rows:
        file_link = f'<a href="{e(r["file"])}">{e(Path(r["file"]).name)}</a>'
        out.append(
            "<tr>"
            f"<td>{e(r['month'])}</td>"
            f"<td>{e(r['establishment'])}</td>"
            f"<td>{source_chip(r['source_type'])}</td>"
            f"<td class=\"num\">{number(r['amount_chf'])}</td>"
            f"<td>{e(r['stay_start'])} au {e(r['stay_end'])}</td>"
            f"<td class=\"num\">{e(r['nights'])}</td>"
            f"<td class=\"num\">{number(r['avg_chf_per_night'])}</td>"
            f"<td>{file_link}</td>"
            "</tr>"
        )
    return "\n".join(out)


def transcript_html():
    return "\n".join(
        f'<div class="message"><div class="role">{e(role)}</div><pre>{e(text)}</pre></div>'
        for role, text in TRANSCRIPT
    )


def main():
    detail = read_csv(DETAIL_CSV)
    monthly = read_csv(MONTHLY_CSV)
    annual = read_csv(ANNUAL_CSV)
    empty_weeks = read_csv(EMPTY_WEEKS_CSV)

    total = sum(dec(r["amount_chf"]) for r in detail)
    official = sum(dec(r["official_chf"]) for r in detail)
    non_official = sum(dec(r["non_official_chf"]) for r in detail)
    nights = sum(int(r["nights"]) for r in detail)
    avg = q2(total / Decimal(nights)) if nights else Decimal("0")
    official_share = q2((official / total) * Decimal("100")) if total else Decimal("0")
    non_official_share = q2((non_official / total) * Decimal("100")) if total else Decimal("0")
    official_count = sum(1 for r in detail if r["source_type"] == "official")
    non_official_count = len(detail) - official_count

    unique_months = []
    seen = set()
    for row in monthly:
        if row["month"] not in seen:
            seen.add(row["month"])
            unique_months.append(row)
    biggest_up = max((r for r in unique_months if r["change_vs_previous_month_chf"]), key=lambda r: dec(r["change_vs_previous_month_chf"]), default=None)
    biggest_down = min((r for r in unique_months if r["change_vs_previous_month_chf"]), key=lambda r: dec(r["change_vs_previous_month_chf"]), default=None)
    peak_month = max(unique_months, key=lambda r: dec(r["month_subtotal_chf"]))
    lowest_avg = min(unique_months, key=lambda r: dec(r["avg_chf_per_night"]))
    highest_avg = max(unique_months, key=lambda r: dec(r["avg_chf_per_night"]))

    html_doc = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rapport des séjours hôteliers autour de Genève</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172026;
      --muted: #66727c;
      --line: #d9e1e7;
      --panel: #ffffff;
      --page: #f5f7f9;
      --green: #11735f;
      --blue: #235c93;
      --red: #a13f34;
      --amber: #9a651c;
      --green-soft: #e5f2ef;
      --blue-soft: #e8f0f8;
      --red-soft: #f7e9e6;
      --amber-soft: #f6eee1;
      --shadow: 0 12px 32px rgba(23, 32, 38, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--page);
      line-height: 1.45;
    }}
    header {{ background: #ffffff; border-bottom: 1px solid var(--line); }}
    .wrap {{ width: min(1220px, calc(100% - 32px)); margin: 0 auto; }}
    .hero {{ padding: 42px 0 30px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(30px, 4vw, 52px); line-height: 1.02; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 22px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; letter-spacing: 0; }}
    p {{ margin: 0; color: var(--muted); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    main {{ padding: 26px 0 54px; }}
    section {{
      margin-top: 22px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .section-head {{
      padding: 20px 22px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: start;
    }}
    .section-body {{ padding: 22px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }}
    .metric {{ background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-height: 118px; }}
    .metric strong {{ display: block; font-size: 26px; line-height: 1.12; margin: 8px 0 6px; letter-spacing: 0; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .note {{ padding: 14px 16px; border-radius: 8px; background: #fbfcfd; border: 1px solid var(--line); color: #42515c; font-size: 14px; }}
    .chip {{ display: inline-flex; align-items: center; min-height: 28px; border-radius: 999px; padding: 4px 10px; font-size: 13px; font-weight: 650; border: 1px solid transparent; white-space: nowrap; }}
    .ok {{ background: var(--green-soft); color: var(--green); border-color: #b9ddd4; }}
    .info {{ background: var(--blue-soft); color: var(--blue); border-color: #c4d8ea; }}
    .warn {{ background: var(--amber-soft); color: var(--amber); border-color: #e2cda9; }}
    .down {{ background: var(--red-soft); color: var(--red); border-color: #e8c4bd; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 11px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: #41505b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; background: #f8fafb; }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .numwrap {{ display: inline-block; min-width: 74px; text-align: right; font-variant-numeric: tabular-nums; }}
    tr:last-child td {{ border-bottom: 0; }}
    .table-scroll {{ overflow-x: auto; }}
    .bars {{ display: grid; gap: 11px; }}
    .bar-row {{ display: grid; grid-template-columns: 82px 1fr 104px; gap: 12px; align-items: center; font-size: 14px; }}
    .bar-track {{ width: var(--w); min-width: 4px; max-width: 100%; height: 14px; border-radius: 999px; background: #e6ebef; overflow: hidden; display: flex; }}
    .bar {{ height: 100%; width: var(--segment); }}
    .bar.official {{ background: var(--green); }}
    .bar.unofficial {{ background: var(--amber); }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
    .week-list {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .week {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: #fbfcfd; }}
    .week strong {{ display: block; font-size: 14px; margin-bottom: 3px; }}
    .week span {{ color: var(--muted); font-size: 13px; }}
    details {{ border-top: 1px solid var(--line); }}
    details summary {{ cursor: pointer; padding: 18px 22px; font-weight: 700; background: #fbfcfd; }}
    .transcript {{ padding: 0 22px 22px; display: grid; gap: 12px; }}
    .message {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; }}
    .message .role {{ color: var(--blue); font-weight: 750; margin-bottom: 6px; }}
    .message pre {{ margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; color: #33414b; }}
    a {{ color: var(--blue); text-decoration: none; font-weight: 650; }}
    a:hover {{ text-decoration: underline; }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .split {{ grid-template-columns: 1fr; }}
      .week-list {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .section-head {{ display: block; }}
      .section-head .chip {{ margin-top: 12px; }}
    }}
    @media (max-width: 640px) {{
      .wrap {{ width: min(100% - 20px, 1220px); }}
      .hero {{ padding: 30px 0 22px; }}
      .grid {{ grid-template-columns: 1fr; }}
      .week-list {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: 70px 1fr; }}
      .bar-row .num {{ grid-column: 2; text-align: left; }}
      th, td {{ padding: 10px 9px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap hero">
      <p>Rapport inclusif des séjours dans un rayon de 30 km autour de Genève</p>
      <h1>Séjours hôteliers autour de Genève</h1>
      <p>Données issues de <code>Invoices_hotel</code> et <code>maybe</code>, avec intégration des documents non officiels exploitables et dédoublonnage par établissement + dates de séjour.</p>
      <div class="grid">
        <div class="metric"><span>Total retenu</span><strong>{money(total)}</strong><span>{len(detail)} séjours avec montant après dédoublonnage</span></div>
        <div class="metric"><span>Part officielle</span><strong>{money(official)}</strong><span>{official_share}% du total, {official_count} documents</span></div>
        <div class="metric"><span>Part non officielle</span><strong>{money(non_official)}</strong><span>{non_official_share}% du total, {non_official_count} documents</span></div>
        <div class="metric"><span>Prix moyen</span><strong>{money(avg)}</strong><span>{nights} nuitées retenues</span></div>
      </div>
    </div>
  </header>
  <main class="wrap">
    <section>
      <div class="section-head">
        <div><h2>Origine des montants</h2><p>Les documents non officiels sont des confirmations ou reçus de paiement qui indiquent ne pas constituer une facture, mais contiennent dates et montants exploitables.</p></div>
        <span class="chip warn">Non officiel inclus</span>
      </div>
      <div class="section-body split">
        <div class="note"><h3>Factures et reçus officiels</h3><p>{money(official)} sur {money(total)}, soit {official_share}% du total.</p></div>
        <div class="note"><h3>Documents non officiels</h3><p>{money(non_official)} sur {money(total)}, soit {non_official_share}% du total. Ces lignes sont marquées dans le détail.</p></div>
      </div>
    </section>

    <section>
      <div class="section-head">
        <div><h2>Synthèse mensuelle</h2><p>Sous-totaux par mois du séjour, ventilés par établissement et par source officielle/non officielle.</p></div>
        <span class="chip ok">Total {money(total)}</span>
      </div>
      <div class="section-body table-scroll">{monthly_table(monthly)}</div>
    </section>

    <section>
      <div class="section-head">
        <div><h2>Sous-totaux annuels</h2><p>Sommes annuelles retenues, avec ventilation officielle/non officielle.</p></div>
        <span class="chip ok">2025 + 2026 = {money(total)}</span>
      </div>
      <div class="section-body table-scroll">{annual_table(annual)}</div>
    </section>

    <section>
      <div class="section-head">
        <div><h2>Sous-totaux par mois</h2><p>Barres empilées : vert pour les documents officiels, orange pour les documents non officiels.</p></div>
        <span class="chip info">Mois sans séjour omis</span>
      </div>
      <div class="section-body">
        <div class="bars">{bars(monthly)}</div>
        <div class="legend"><span class="chip ok">Officiel</span><span class="chip warn">Non officiel</span></div>
      </div>
    </section>

    <section>
      <div class="section-head">
        <div><h2>Observations</h2><p>Fluctuations observées sur les sous-totaux mensuels et le prix moyen de la nuitée.</p></div>
        <span class="chip info">{len(unique_months)} mois avec données</span>
      </div>
      <div class="section-body">
        <div class="grid">
          <div class="note"><h3>Pic mensuel</h3><p>{e(peak_month["month"])} atteint {money(peak_month["month_subtotal_chf"])}.</p></div>
          <div class="note"><h3>Plus forte hausse</h3><p>{e(biggest_up["month"])} progresse de {money(biggest_up["change_vs_previous_month_chf"])} ({pct(biggest_up["change_vs_previous_month_pct"])}).</p></div>
          <div class="note"><h3>Plus forte baisse</h3><p>{e(biggest_down["month"])} recule de {money(biggest_down["change_vs_previous_month_chf"])} ({pct(biggest_down["change_vs_previous_month_pct"])}).</p></div>
          <div class="note"><h3>Prix par nuit</h3><p>La moyenne mensuelle va de {money(lowest_avg["avg_chf_per_night"])} en {e(lowest_avg["month"])} à {money(highest_avg["avg_chf_per_night"])} en {e(highest_avg["month"])}.</p></div>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head">
        <div><h2>Semaines sans réservation trouvée</h2><p>Basé sur toutes les réservations datées trouvées dans le périmètre de 30 km autour de Genève, factures et documents non officiels inclus.</p></div>
        <span class="chip info">{len(empty_weeks)} semaines</span>
      </div>
      <div class="section-body"><div class="week-list">{weeks(empty_weeks)}</div></div>
    </section>

    <section>
      <div class="section-head">
        <div><h2>Détail des séjours retenus</h2><p>Chaque ligne correspond à un séjour avec montant après dédoublonnage; la source indique si le document est officiel ou non.</p></div>
        <span class="chip ok">{len(detail)} lignes</span>
      </div>
      <div class="section-body table-scroll">
        <table>
          <thead>
            <tr><th>Mois</th><th>Établissement</th><th>Source</th><th class="num">Montant</th><th>Séjour</th><th class="num">Nuits</th><th class="num">Moy. / nuit</th><th>Fichier</th></tr>
          </thead>
          <tbody>{detail_table(detail)}</tbody>
        </table>
      </div>
    </section>

    <section>
      <div class="section-head">
        <div><h2>Fichiers de référence</h2><p>CSV et scripts générés pendant l’analyse inclusive.</p></div>
      </div>
      <div class="section-body">
        <p><a href="geneva_hotel_inclusive_monthly_subtotals.csv">geneva_hotel_inclusive_monthly_subtotals.csv</a></p>
        <p><a href="geneva_hotel_inclusive_annual_subtotals.csv">geneva_hotel_inclusive_annual_subtotals.csv</a></p>
        <p><a href="geneva_hotel_stays_inclusive_detail.csv">geneva_hotel_stays_inclusive_detail.csv</a></p>
        <p><a href="geneva_hotel_inclusive_weeks_without_reservation.csv">geneva_hotel_inclusive_weeks_without_reservation.csv</a></p>
        <p><a href="tools/analyze_geneva_hotel_stays_inclusive.py">tools/analyze_geneva_hotel_stays_inclusive.py</a></p>
        <p><a href="tools/render_geneva_hotel_report.py">tools/render_geneva_hotel_report.py</a></p>
      </div>
    </section>

    <section>
      <div class="section-head">
        <div><h2>Discussion</h2><p>Section fermée par défaut, contenant la conversation disponible dans ce fil.</p></div>
        <span class="chip info">Masquée par défaut</span>
      </div>
      <details>
        <summary>Afficher la discussion complète</summary>
        <div class="transcript">{transcript_html()}</div>
      </details>
    </section>
  </main>
</body>
</html>
"""
    REPORT.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
