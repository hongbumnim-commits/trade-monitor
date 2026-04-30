"""
한국 주요 종목 수익률 테이블 생성기
매일 GitHub Actions에서 실행되어 index.html을 업데이트합니다.

컬럼 정의:
  - 거래대금 증가: 최근 20일 평균 거래대금 / 시작일 이후 초기 20일 평균 거래대금
  - 수익률: 기준일 종가 대비 현재 종가 상승률 (%)
  - 수익률 - 시총증가: 수익률(%) - 시가총액 증가율(%)  →  자사주 매입 효과 등 측정
"""

import time
from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock

# ── 설정 ──────────────────────────────────────────────────────────────────────
START_DATE = "20200102"   # 기준일

# 추적할 종목 (티커, 표시명)
TICKERS = [
    ("005930", "삼성전자"),
    ("000660", "SK하이닉스"),
    ("035420", "NAVER"),
    ("035720", "카카오"),
    ("005380", "현대차"),
    ("000270", "기아"),
    ("051910", "LG화학"),
    ("006400", "삼성SDI"),
    ("373220", "LG에너지솔루션"),
    ("207940", "삼성바이오로직스"),
    ("068270", "셀트리온"),
    ("005490", "POSCO홀딩스"),
    ("105560", "KB금융"),
    ("055550", "신한지주"),
    ("086790", "하나금융지주"),
    ("033780", "KT&G"),
    ("012330", "현대모비스"),
    ("000810", "삼성화재"),
    ("017670", "SK텔레콤"),
    ("028260", "삼성물산"),
]

OUTPUT_FILE = "index.html"

# ── 데이터 수집 ────────────────────────────────────────────────────────────────

def last_trading_day() -> str:
    """pykrx로 실제 마지막 거래일 조회 (공휴일·주말 자동 처리)"""
    today = datetime.today().strftime("%Y%m%d")
    ohlcv = stock.get_market_ohlcv_by_date("20260101", today, "005930")
    if ohlcv is not None and not ohlcv.empty:
        return ohlcv.index[-1].strftime("%Y%m%d")
    # fallback: 3일 전
    d = datetime.today() - timedelta(days=3)
    return d.strftime("%Y%m%d")


def fetch_metrics(ticker: str, name: str, start: str, end: str) -> dict | None:
    try:
        # OHLCV + 거래대금
        ohlcv = stock.get_market_ohlcv_by_date(start, end, ticker)
        if ohlcv is None or ohlcv.empty or len(ohlcv) < 25:
            print(f"  [{name}] OHLCV 데이터 부족 — 스킵")
            return None

        # 시가총액
        cap_df = stock.get_market_cap_by_date(start, end, ticker)
        if cap_df is None or cap_df.empty:
            print(f"  [{name}] 시총 데이터 없음 — 스킵")
            return None

        # ① 거래대금 증가 배수
        first20_avg = ohlcv["거래대금"].iloc[:20].mean()
        last20_avg  = ohlcv["거래대금"].iloc[-20:].mean()
        tv_ratio = round(last20_avg / first20_avg, 2) if first20_avg > 0 else None

        # ② 수익률 (%)
        start_price = ohlcv["종가"].iloc[0]
        end_price   = ohlcv["종가"].iloc[-1]
        ret = round((end_price - start_price) / start_price * 100) if start_price > 0 else None

        # ③ 시총 증가율 (%)
        start_cap = cap_df["시가총액"].iloc[0]
        end_cap   = cap_df["시가총액"].iloc[-1]
        cap_growth = round((end_cap - start_cap) / start_cap * 100) if start_cap > 0 else None

        # ④ 수익률 - 시총증가
        ret_minus_cap = (round(ret - cap_growth)) if (ret is not None and cap_growth is not None) else None

        return {
            "ticker": ticker,
            "name": name,
            "tv_ratio": tv_ratio,
            "ret": ret,
            "ret_minus_cap": ret_minus_cap,
        }

    except Exception as e:
        print(f"  [{name}] 오류: {e}")
        return None


# ── HTML 생성 ──────────────────────────────────────────────────────────────────

def row_bg(ret: int | None) -> str:
    if ret is None:
        return ""
    if ret >= 300:
        return "row-yellow"
    if ret >= 120:
        return "row-green"
    if ret < 40:
        return "row-pink"
    return ""


def cell_class(val: int | None) -> str:
    if val is None:
        return ""
    if val >= 100:
        return "cell-yellow"
    if val >= 30:
        return "cell-green"
    if val < 0:
        return "cell-pink"
    return ""


def fmt_pct(v) -> str:
    return f"{v:+d}%" if v is not None else "—"


def fmt_ratio(v) -> str:
    return f"{v:.2f}" if v is not None else "—"


def build_html(rows: list, generated_at: str, end_date: str) -> str:
    end_fmt = f"{end_date[:4]}.{end_date[4:6]}.{end_date[6:]}"
    tbody = ""
    for r in rows:
        rc  = row_bg(r["ret"])
        cc  = cell_class(r["ret_minus_cap"])
        ret_str = f"{r['ret']}%" if r["ret"] is not None else "—"
        tbody += f"""
        <tr class="{rc}">
          <td class="name">{r['name']}<span class="ticker">{r['ticker']}</span></td>
          <td class="num">{fmt_ratio(r['tv_ratio'])}</td>
          <td class="num">{ret_str}</td>
          <td class="num {cc}">{fmt_pct(r['ret_minus_cap'])}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>한국 주요 종목 추적</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, 'Malgun Gothic', sans-serif;
      background: #1a1a2e;
      color: #e0e0e0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2rem 1rem;
    }}
    h1 {{ font-size: 1.3rem; margin-bottom: 0.3rem; color: #fff; }}
    .subtitle {{ font-size: 0.8rem; color: #888; margin-bottom: 0.4rem; }}
    .updated  {{ font-size: 0.75rem; color: #666; margin-bottom: 1.5rem; }}
    .table-wrap {{ overflow-x: auto; width: 100%; max-width: 680px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #16213e;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 24px rgba(0,0,0,0.5);
    }}
    thead tr {{ background: #0f3460; }}
    th {{
      padding: 12px 16px;
      font-size: 0.78rem;
      color: #a0b4d0;
      font-weight: 600;
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child {{ text-align: left; }}
    td {{
      padding: 10px 16px;
      font-size: 0.88rem;
      border-bottom: 1px solid #1e2d4a;
    }}
    tr:last-child td {{ border-bottom: none; }}
    td.name {{
      font-weight: 700;
      color: #fff;
      text-align: left;
    }}
    td.name .ticker {{
      display: block;
      font-size: 0.7rem;
      font-weight: 400;
      color: #556;
    }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}

    tr.row-yellow td {{ background: rgba(255,230,0,0.18); }}
    tr.row-green  td {{ background: rgba(80,200,100,0.15); }}
    tr.row-pink   td {{ background: rgba(230,100,100,0.13); }}

    td.cell-yellow {{ color: #ffe600; font-weight: 700; }}
    td.cell-green  {{ color: #50c864; font-weight: 600; }}
    td.cell-pink   {{ color: #ff7070; }}

    .legend {{
      margin-top: 1.2rem;
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
      justify-content: center;
    }}
    .legend-item {{
      font-size: 0.72rem;
      color: #888;
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }}
    .dot {{ width: 10px; height: 10px; border-radius: 2px; }}
    .dot-y {{ background: rgba(255,230,0,0.6); }}
    .dot-g {{ background: rgba(80,200,100,0.5); }}
    .dot-p {{ background: rgba(230,100,100,0.45); }}
  </style>
</head>
<body>
  <h1>🇰🇷 한국 주요 종목 추적</h1>
  <div class="subtitle">기준일: {START_DATE[:4]}.{START_DATE[4:6]}.{START_DATE[6:]} → {end_fmt} 종가 기준</div>
  <div class="updated">마지막 업데이트: {generated_at} (KST)</div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>종목</th>
          <th>거래대금 증가</th>
          <th>수익률</th>
          <th>수익률 − 시총증가</th>
        </tr>
      </thead>
      <tbody>{tbody}
      </tbody>
    </table>
  </div>
  <div class="legend">
    <div class="legend-item"><div class="dot dot-y"></div>수익률 ≥ 300%</div>
    <div class="legend-item"><div class="dot dot-g"></div>수익률 ≥ 120%</div>
    <div class="legend-item"><div class="dot dot-p"></div>수익률 &lt; 40%</div>
  </div>
</body>
</html>
"""


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    end_date = last_trading_day()
    now_kst  = datetime.utcnow() + timedelta(hours=9)
    generated_at = now_kst.strftime("%Y-%m-%d %H:%M")

    print(f"기준일: {START_DATE}  →  마지막 거래일: {end_date}")
    print(f"총 {len(TICKERS)}개 종목 처리 중...\n")

    results = []
    for ticker, name in TICKERS:
        print(f"  처리 중: {name} ({ticker})")
        row = fetch_metrics(ticker, name, START_DATE, end_date)
        if row:
            results.append(row)
        time.sleep(0.5)

    # 수익률 내림차순 정렬
    results.sort(key=lambda x: x["ret"] if x["ret"] is not None else -9999, reverse=True)

    html = build_html(results, generated_at, end_date)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ {OUTPUT_FILE} 생성 완료 ({len(results)}개 종목)")


if __name__ == "__main__":
    main()
