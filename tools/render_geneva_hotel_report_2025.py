#!/usr/bin/env python3
from decimal import Decimal
from pathlib import Path

import render_geneva_hotel_report as report


ROOT = Path.cwd()
YEAR = 2025
DETAIL_CSV = ROOT / "geneva_hotel_2025_stays_inclusive_detail.csv"
MONTHLY_CSV = ROOT / "geneva_hotel_2025_inclusive_monthly_subtotals.csv"
ANNUAL_CSV = ROOT / "geneva_hotel_2025_inclusive_annual_subtotals.csv"
EMPTY_WEEKS_CSV = ROOT / "geneva_hotel_2025_inclusive_weeks_without_reservation.csv"
OUTPUT = ROOT / "geneva_hotel_report_2025.html"


def main():
    detail = report.read_csv(DETAIL_CSV)
    monthly = report.read_csv(MONTHLY_CSV)
    annual = report.read_csv(ANNUAL_CSV)
    empty_weeks = report.read_csv(EMPTY_WEEKS_CSV)

    total = sum(report.dec(r["amount_chf"]) for r in detail)
    official = sum(report.dec(r["official_chf"]) for r in detail)
    non_official = sum(report.dec(r["non_official_chf"]) for r in detail)
    nights = sum(int(r["nights"]) for r in detail)
    avg = report.q2(total / Decimal(nights)) if nights else Decimal("0")
    official_share = report.q2((official / total) * Decimal("100")) if total else Decimal("0")
    non_official_share = report.q2((non_official / total) * Decimal("100")) if total else Decimal("0")
    official_count = sum(1 for r in detail if r["source_type"] == "official")
    non_official_count = len(detail) - official_count

    unique_months = []
    seen = set()
    for row in monthly:
        if row["month"] not in seen:
            seen.add(row["month"])
            unique_months.append(row)
    peak_month = max(unique_months, key=lambda r: report.dec(r["month_subtotal_chf"]))
    biggest_up = max((r for r in unique_months if r["change_vs_previous_month_chf"]), key=lambda r: report.dec(r["change_vs_previous_month_chf"]), default=None)
    biggest_down = min((r for r in unique_months if r["change_vs_previous_month_chf"]), key=lambda r: report.dec(r["change_vs_previous_month_chf"]), default=None)
    lowest_avg = min(unique_months, key=lambda r: report.dec(r["avg_chf_per_night"]))
    highest_avg = max(unique_months, key=lambda r: report.dec(r["avg_chf_per_night"]))

    html_doc = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rapport 2025 des séjours hôteliers autour de Genève</title>
  <style>
    :root {{
      --ink: #172026; --muted: #66727c; --line: #d9e1e7; --panel: #fff; --page: #f5f7f9;
      --green: #11735f; --blue: #235c93; --red: #a13f34; --amber: #9a651c;
      --green-soft: #e5f2ef; --blue-soft: #e8f0f8; --red-soft: #f7e9e6; --amber-soft: #f6eee1;
      --shadow: 0 12px 32px rgba(23, 32, 38, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--page); line-height: 1.45; }}
    header {{ background: #fff; border-bottom: 1px solid var(--line); }}
    .wrap {{ width: min(1220px, calc(100% - 32px)); margin: 0 auto; }}
    .hero {{ padding: 42px 0 30px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(30px, 4vw, 52px); line-height: 1.02; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 22px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; letter-spacing: 0; }}
    p {{ margin: 0; color: var(--muted); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    main {{ padding: 26px 0 54px; }}
    section {{ margin-top: 22px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); overflow: hidden; }}
    .section-head {{ padding: 20px 22px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 20px; align-items: start; }}
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
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .split {{ grid-template-columns: 1fr; }} .week-list {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .section-head {{ display: block; }} .section-head .chip {{ margin-top: 12px; }} }}
    @media (max-width: 640px) {{ .wrap {{ width: min(100% - 20px, 1220px); }} .hero {{ padding: 30px 0 22px; }} .grid {{ grid-template-columns: 1fr; }} .week-list {{ grid-template-columns: 1fr; }} .bar-row {{ grid-template-columns: 70px 1fr; }} .bar-row .num {{ grid-column: 2; text-align: left; }} th, td {{ padding: 10px 9px; }} }}
  </style>
</head>
<body>
  <header>
    <div class="wrap hero">
      <p>Rapport inclusif 2025 des séjours dans un rayon de 30 km autour de Genève</p>
      <h1>Séjours hôteliers autour de Genève 2025</h1>
      <p>Données issues de <code>Invoices_hotel</code> et <code>maybe</code>, limitées aux séjours qui chevauchent l'année 2025, avec documents non officiels exploitables inclus.</p>
      <div class="grid">
        <div class="metric"><span>Total retenu 2025</span><strong>{report.money(total)}</strong><span>{len(detail)} séjours avec montant après dédoublonnage</span></div>
        <div class="metric"><span>Part officielle</span><strong>{report.money(official)}</strong><span>{official_share}% du total, {official_count} documents</span></div>
        <div class="metric"><span>Part non officielle</span><strong>{report.money(non_official)}</strong><span>{non_official_share}% du total, {non_official_count} documents</span></div>
        <div class="metric"><span>Prix moyen</span><strong>{report.money(avg)}</strong><span>{nights} nuitées retenues</span></div>
      </div>
    </div>
  </header>
  <main class="wrap">
    <section>
      <div class="section-head"><div><h2>Origine des montants</h2><p>Les documents non officiels sont inclus seulement lorsqu'ils apportent dates et montants exploitables.</p></div><span class="chip warn">Non officiel inclus</span></div>
      <div class="section-body split">
        <div class="note"><h3>Factures et reçus officiels</h3><p>{report.money(official)} sur {report.money(total)}, soit {official_share}% du total 2025.</p></div>
        <div class="note"><h3>Documents non officiels</h3><p>{report.money(non_official)} sur {report.money(total)}, soit {non_official_share}% du total 2025. Ces lignes sont marquées dans le détail.</p></div>
      </div>
    </section>
    <section><div class="section-head"><div><h2>Synthèse mensuelle</h2><p>Sous-totaux 2025 par mois du séjour, ventilés par établissement et source.</p></div><span class="chip ok">Total {report.money(total)}</span></div><div class="section-body table-scroll">{report.monthly_table(monthly)}</div></section>
    <section><div class="section-head"><div><h2>Sous-total annuel</h2><p>Somme annuelle 2025 avec ventilation officielle/non officielle.</p></div><span class="chip ok">2025 = {report.money(total)}</span></div><div class="section-body table-scroll">{report.annual_table(annual)}</div></section>
    <section><div class="section-head"><div><h2>Sous-totaux par mois</h2><p>Barres empilées : vert pour les documents officiels, orange pour les documents non officiels.</p></div><span class="chip info">Mois sans séjour omis</span></div><div class="section-body"><div class="bars">{report.bars(monthly)}</div><div class="legend"><span class="chip ok">Officiel</span><span class="chip warn">Non officiel</span></div></div></section>
    <section>
      <div class="section-head"><div><h2>Observations</h2><p>Fluctuations observées sur les sous-totaux mensuels et le prix moyen de la nuitée en 2025.</p></div><span class="chip info">{len(unique_months)} mois avec données</span></div>
      <div class="section-body"><div class="grid">
        <div class="note"><h3>Pic mensuel</h3><p>{report.e(peak_month["month"])} atteint {report.money(peak_month["month_subtotal_chf"])}.</p></div>
        <div class="note"><h3>Plus forte hausse</h3><p>{report.e(biggest_up["month"])} progresse de {report.money(biggest_up["change_vs_previous_month_chf"])} ({report.pct(biggest_up["change_vs_previous_month_pct"])}).</p></div>
        <div class="note"><h3>Plus forte baisse</h3><p>{report.e(biggest_down["month"])} recule de {report.money(biggest_down["change_vs_previous_month_chf"])} ({report.pct(biggest_down["change_vs_previous_month_pct"])}).</p></div>
        <div class="note"><h3>Prix par nuit</h3><p>La moyenne mensuelle va de {report.money(lowest_avg["avg_chf_per_night"])} en {report.e(lowest_avg["month"])} à {report.money(highest_avg["avg_chf_per_night"])} en {report.e(highest_avg["month"])}.</p></div>
      </div></div>
    </section>
    <section><div class="section-head"><div><h2>Semaines 2025 sans réservation trouvée</h2><p>Basé sur les réservations datées dans le périmètre de 30 km autour de Genève qui chevauchent 2025.</p></div><span class="chip info">{len(empty_weeks)} semaines</span></div><div class="section-body"><div class="week-list">{report.weeks(empty_weeks)}</div></div></section>
    <section>
      <div class="section-head"><div><h2>Détail des séjours retenus</h2><p>Chaque ligne correspond à un séjour 2025 avec montant après dédoublonnage.</p></div><span class="chip ok">{len(detail)} lignes</span></div>
      <div class="section-body table-scroll"><table><thead><tr><th>Mois</th><th>Établissement</th><th>Source</th><th class="num">Montant</th><th>Séjour</th><th class="num">Nuits</th><th class="num">Moy. / nuit</th><th>Fichier</th></tr></thead><tbody>{report.detail_table(detail)}</tbody></table></div>
    </section>
    <section>
      <div class="section-head"><div><h2>Fichiers de référence</h2><p>CSV, scripts et archive générés pour le périmètre 2025.</p></div></div>
      <div class="section-body">
        <p><a href="geneva_hotel_2025_inclusive_monthly_subtotals.csv">geneva_hotel_2025_inclusive_monthly_subtotals.csv</a></p>
        <p><a href="geneva_hotel_2025_inclusive_annual_subtotals.csv">geneva_hotel_2025_inclusive_annual_subtotals.csv</a></p>
        <p><a href="geneva_hotel_2025_stays_inclusive_detail.csv">geneva_hotel_2025_stays_inclusive_detail.csv</a></p>
        <p><a href="geneva_hotel_2025_inclusive_weeks_without_reservation.csv">geneva_hotel_2025_inclusive_weeks_without_reservation.csv</a></p>
        <p><a href="geneva_hotel_2025_concerned_files.csv">geneva_hotel_2025_concerned_files.csv</a></p>
        <p><a href="tools/analyze_geneva_hotel_stays_inclusive_2025.py">tools/analyze_geneva_hotel_stays_inclusive_2025.py</a></p>
        <p><a href="tools/render_geneva_hotel_report_2025.py">tools/render_geneva_hotel_report_2025.py</a></p>
      </div>
    </section>
    <section>
      <div class="section-head"><div><h2>Discussion</h2><p>Section fermée par défaut, contenant la conversation disponible dans ce fil.</p></div><span class="chip info">Masquée par défaut</span></div>
      <details><summary>Afficher la discussion complète</summary><div class="transcript">{report.transcript_html()}</div></details>
    </section>
  </main>
</body>
</html>
"""
    OUTPUT.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
