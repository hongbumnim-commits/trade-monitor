"""
한국 주요 종목 수익률 테이블 생성기
매일 GitHub Actions에서 실행되어 index.html을 업데이트합니다.

컬럼 정의:
  - 거래대금 증가: 최근 20일 평균 거래대금 / 시작일 이후 초기 20일 평균 거래대금
  - 수익률: 기준일 종가 대비 현재 종가 상승률 (%)
  - 수익률 - 시총증가: 수익률(%) - 시가총액 증가율(%)  →  자사주 매입 효과 등 측정

변경사항: pykrx → yfinance (KRX 로그인 불필요)
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

# ── 설정 ──────────────────────────────────────────────────────────────────────
START_DATE = "2020-01-02"   # 기준일 (yfinance 형식: YYYY-MM-DD)

# 추적할 종목 (야후파이낸스 티커, 표시명)
# 한국 주식은 KOSPI → .KS, KOSDAQ → .KQ 접미사
TICKERS = [
    ("005930.KS", "삼성전자"),
    ("000660.KS", "SK하이닉스"),
    ("035420.KS", "NAVER"),
    ("035720.KS", "카카오"),
    ("005380.KS", "현대차"),
    ("000270.KS", "기아"),
    ("051910.KS", "LG화학"),
    ("006400.KS", "삼성SDI"),
    ("373220.KS", "LG에너지솔루션"),
    ("207940.KS", "삼성바이오로직스"),
    ("068270.KS", "셀트리온"),
    ("005490.KS", "POSCO홀딩스"),
    ("105560.KS", "KB금융"),
    ("055550.KS", "신한지주"),
    ("086790.KS", "하나금융지주"),
    ("033780.KS", "KT&G"),
    ("012330.KS", "현대모비스"),
    ("000810.KS", "삼성화재"),
    ("017670.KS", "SK텔레콤"),
    ("028260.KS", "삼성물산"),
]

OUTPUT_FILE = "index.html"

# ── 데이터 수집 ────────────────────────────────────────────────────────────────

def fetch_metrics(yf_ticker: str, name: str, start: str) -> dict | None:
    """yfinance로 OHLCV + 시총 데이터 수집 후 지표 계산"""
    # 원본 티커 (표시용, 앞 6자리)
    display_ticker = yf_ticker.split('.')[0]

    try:
        ticker_obj = yf.Ticker(yf_ticker)

        # OHLCV (auto_adjust=True → 수정주가 적용)
        ohlcv = ticker_obj.history(start=start, auto_adjust=True)

        if ohlcv is None or ohlcv.empty or len(ohlcv) < 25:
            print(f"  [{name}] OHLCV 데이터 부족 ({len(ohlcv) if ohlcv is not None else 0}행) — 스킵")
            return None

        # ① 거래대금 증가 배수 (거래량 × 종가로 거래대금 근사)
        ohlcv = ohlcv.copy()
        ohlcv['거래대금'] = ohlcv['Close'] * ohlcv['Volume']
        first20_avg = ohlcv['거래대금'].iloc[:20].mean()
        last20_avg  = ohlcv['거래대금'].iloc[-20:].mean()
        tv_ratio = round(last20_avg / first20_avg, 2) if first20_avg > 0 else None

        # ② 수익률 (%)
        start_price = ohlcv['Close'].iloc[0]
        end_price   = ohlcv['Close'].iloc[-1]
        ret = round((end_price - start_price) / start_price * 100) if start_price > 0 else None

        # ③ 시총 증가율 (%) — info에서 shares outstanding 사용
        # yfinance info는 현재 시점 기준이므로 주가 변동률로 근사
        # (정확한 시총 변동은 발행주식수 변화 포함이 필요하나, 근사치로 주가 수익률 사용)
        info = ticker_obj.fast_info
        shares = getattr(info, 'shares', None)
        if shares and shares > 0:
            start_cap = start_price * shares
            end_cap   = end_price   * shares
            cap_growth = round((end_cap - start_cap) / start_cap * 100)
        else:
            # 발행주식수 없으면 수익률과 동일하게 처리 (ret_minus_cap = 0)
            cap_growth = ret

        # ④ 수익률 - 시총증가
        ret_minus_cap = (round(ret - cap_growth)) if (ret is not None and cap_growth is not None) else None

        end_date_str = ohlcv.index[-1].strftime("%Y%m%d")

        return {
            "ticker": display_ticker,
            "name": name,
            "tv_ratio": tv_ratio,
            "ret": ret,
            "ret_minus_cap": ret_minus_cap,
            "end_date": end_date_str,
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
    start_fmt = f"{START_DATE[:4]}.{START_DATE[5:7]}.{START_DATE[8:]}"
    end_fmt   = f"{end_date[:4]}.{end_date[4:6]}.{end_date[6:]}"
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
  <div class="subtitle">기준일: {start_fmt} → {end_fmt} 종가 기준</div>
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
    now_kst      = datetime.utcnow() + timedelta(hours=9)
    generated_at = now_kst.strftime("%Y-%m-%d %H:%M")

    print(f"기준일: {START_DATE}  →  오늘 실행")
    print(f"총 {len(TICKERS)}개 종목 처리 중...\n")

    results  = []
    end_date = ""

    for yf_ticker, name in TICKERS:
        print(f"  처리 중: {name} ({yf_ticker})")
        row = fetch_metrics(yf_ticker, name, START_DATE)
        if row:
            results.append(row)
            end_date = row["end_date"]   # 마지막으로 수집된 거래일
        time.sleep(0.3)   # 레이트 리밋 방지

    if not end_date:
        end_date = now_kst.strftime("%Y%m%d")

    # 수익률 내림차순 정렬
    results.sort(key=lambda x: x["ret"] if x["ret"] is not None else -9999, reverse=True)

    html = build_html(results, generated_at, end_date)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ {OUTPUT_FILE} 생성 완료 ({len(results)}개 종목)")


if __name__ == "__main__":
    main()
