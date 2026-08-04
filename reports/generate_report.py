"""
Генерирует самостоятельный HTML-отчёт по данным curated-витрин:
top IP по трафику, p95/p99 латентность, error rate по эндпоинтам,
тренд трафика по 5-минутным окнам.

Запуск:
    python reports/generate_report.py
    python reports/generate_report.py --out reports/output/my_report.html
"""

import argparse
import base64
import io
import os
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # без GUI-бэкенда, только рендер в файл/буфер
import matplotlib.pyplot as plt
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "telemetry"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

REPORT_DIR = Path(__file__).parent / "output"

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#333333",
    "axes.grid": True,
    "grid.color": "#e5e5e5",
    "grid.linewidth": 0.6,
    "font.size": 10,
})

ACCENT = "#2563eb"
ACCENT_WARN = "#dc2626"


def fetch_df(conn, query: str) -> pd.DataFrame:
    return pd.read_sql(query, conn)


def fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def chart_top_ip(df: pd.DataFrame) -> str:
    top = df.sort_values("total_bytes", ascending=False).head(10)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(top["client_ip"].astype(str)[::-1], (top["total_bytes"] / 1_000_000)[::-1], color=ACCENT)
    ax.set_xlabel("Total traffic (MB)")
    ax.set_title("Top 10 IPs by traffic")
    return fig_to_base64(fig)


def chart_latency(df: pd.DataFrame) -> str:
    d = df.sort_values("p99_ms", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 4))
    x = range(len(d))
    ax.bar(x, d["p50_ms"], width=0.25, label="p50", color="#93c5fd")
    ax.bar([i + 0.25 for i in x], d["p95_ms"], width=0.25, label="p95", color=ACCENT)
    ax.bar([i + 0.5 for i in x], d["p99_ms"], width=0.25, label="p99", color=ACCENT_WARN)
    ax.set_xticks([i + 0.25 for i in x])
    ax.set_xticklabels(d["path"], rotation=30, ha="right")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Latency percentiles by endpoint")
    ax.legend()
    return fig_to_base64(fig)


def chart_error_rate(df: pd.DataFrame) -> str:
    d = df.sort_values("error_rate_pct", ascending=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    colors = [ACCENT_WARN if v >= 15 else ACCENT for v in d["error_rate_pct"]]
    ax.barh(d["path"], d["error_rate_pct"], color=colors)
    ax.set_xlabel("Error rate (%)")
    ax.set_title("Error rate by endpoint")
    return fig_to_base64(fig)


def chart_traffic_windows(df: pd.DataFrame) -> str:
    d = df.sort_values("window_start")
    fig, ax1 = plt.subplots(figsize=(9, 4))
    ax1.plot(d["window_start"], d["request_count"], color=ACCENT, marker="o", label="Requests")
    ax1.set_ylabel("Requests / 5min", color=ACCENT)
    ax1.tick_params(axis="x", rotation=30)

    ax2 = ax1.twinx()
    ax2.plot(d["window_start"], d["p95_ms"], color=ACCENT_WARN, marker="s", linestyle="--", label="p95 latency (ms)")
    ax2.set_ylabel("p95 latency (ms)", color=ACCENT_WARN)

    fig.suptitle("Traffic & latency over time (5-minute windows)")
    fig.tight_layout()
    return fig_to_base64(fig)


def build_html(charts: dict, tables: dict, generated_at: str) -> str:
    def table_html(df: pd.DataFrame) -> str:
        return df.to_html(index=False, classes="data-table", border=0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Telemetry Analytics Report</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f8fafc;
    color: #1e293b;
    margin: 0;
    padding: 40px;
  }}
  .container {{ max-width: 1000px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .subtitle {{ color: #64748b; font-size: 13px; margin-bottom: 32px; }}
  .section {{
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 24px;
    margin-bottom: 24px;
  }}
  .section h2 {{ font-size: 16px; margin-top: 0; margin-bottom: 16px; }}
  img {{ max-width: 100%; display: block; margin: 0 auto 16px; }}
  table.data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  table.data-table th {{
    text-align: left;
    background: #f1f5f9;
    padding: 8px 10px;
    border-bottom: 1px solid #e2e8f0;
  }}
  table.data-table td {{
    padding: 6px 10px;
    border-bottom: 1px solid #f1f5f9;
  }}
  footer {{ color: #94a3b8; font-size: 12px; margin-top: 32px; text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <h1>Telemetry Analytics Report</h1>
  <div class="subtitle">Generated {generated_at} · source: KuFlow (synthetic data)</div>

  <div class="section">
    <h2>Top IPs by traffic</h2>
    <img src="data:image/png;base64,{charts['top_ip']}">
    {table_html(tables['top_ip'].head(10))}
  </div>

  <div class="section">
    <h2>Latency percentiles by endpoint</h2>
    <img src="data:image/png;base64,{charts['latency']}">
    {table_html(tables['latency'])}
  </div>

  <div class="section">
    <h2>Error rate by endpoint</h2>
    <img src="data:image/png;base64,{charts['error_rate']}">
    {table_html(tables['error_rate'])}
  </div>

  <div class="section">
    <h2>Traffic & latency trend (5-minute windows)</h2>
    <img src="data:image/png;base64,{charts['traffic_windows']}">
  </div>

  <footer>Telemetry Analytics Pipeline · Raw → Processed → Curated</footer>
</div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output HTML path (default: reports/output/report_<timestamp>.html)",
    )
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else REPORT_DIR / f"report_{datetime.now():%Y%m%d_%H%M%S}.html"

    conn = psycopg2.connect(**DB_CONFIG)

    top_ip_df = fetch_df(conn, "SELECT * FROM curated.top_ip_by_traffic;")
    latency_df = fetch_df(conn, "SELECT * FROM curated.latency_percentiles;")
    error_rate_df = fetch_df(conn, "SELECT * FROM curated.error_rate_by_endpoint;")
    traffic_windows_df = fetch_df(conn, "SELECT * FROM curated.traffic_windows_5m;")

    conn.close()

    charts = {
        "top_ip": chart_top_ip(top_ip_df),
        "latency": chart_latency(latency_df),
        "error_rate": chart_error_rate(error_rate_df),
        "traffic_windows": chart_traffic_windows(traffic_windows_df),
    }
    tables = {
        "top_ip": top_ip_df,
        "latency": latency_df,
        "error_rate": error_rate_df,
    }

    html = build_html(charts, tables, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    out_path.write_text(html, encoding="utf-8")

    print(f"✅ Report generated: {out_path}")


if __name__ == "__main__":
    main()