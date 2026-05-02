"""
한국 주요 종목 수익률 테이블 생성기
매일 GitHub Actions에서 실행되어 index.html을 업데이트합니다.

데이터 출처: 공공데이터포털 금융위원회_주식시세정보 API
환경변수: DATA_GO_KR_API_KEY (GitHub Secrets에 등록)

컬럼 정의:
  - 거래대금 증가: 최근 20일 평균 거래대금 / 초기 20일 평균 거래대금
  - 수익률: 기준일 종가 대비 현재 종가 상승률 (%)
  - 수익률 - 시총증가: 수익률(%) - 시가총액 증가율(%)
"""

import os
import time
import requests
from datetime import datetime, timedelta

# ── 설정 ──────────────────────────────────────────────────────────────────────
API_KEY    = os.environ.get("DATA_GO_KR_API_KEY", "")
BASE_URL   = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
START_DATE = "20200102"
OUTPUT_FILE = "index.html"

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

# ── API 호출 ──────────────────────────────────────────────────────────────────

def call_api(params: dict) -> list:
    """API 호출 후 items 리스트 반환"""
    try:
        r = requests.get(BASE_URL, params=params, timeout=15)
        data = r.json()
        items = data["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return sorted(items, key=lambda x: x["basDt"])
    except Exception:
        return []


def get_price_on_date(ticker: str, date: str) -> dict | None:
    """기준일 근처 종가 조회"""
    d     = datetime.strptime(date, "%Y%m%d")
    begin = (d - timedelta(days=7)).strftime("%Y%m%d")
    end   = (d + timedelta(days=7)).strftime("%Y%m%d")
    items = call_api({
        "serviceKey": API_KEY, "numOfRows": "10", "pageNo": "1",
        "resultType": "json", "beginBasDt": begin, "endBasDt": end,
        "srtnCd": ticker,
    })
    for item in items:
        if item["basDt"] >= date:
            return item
    return items[-1] if items else None


def get_price_range(ticker: str, begin: str, end: str, num: int = 25) -> list:
    """특정 기간 시세 목록"""
    return call_api({
        "serviceKey": API_KEY, "numOfRows": str(num), "pageNo": "1",
        "resultType": "json", "beginBasDt": begin, "endBasDt": end,
        "srtnCd": ticker,
    })


# ── 지표 계산 ──────────────────────────────────────────────────────────────────

def fetch_metrics(ticker: str, name: str) -> dict | None:
    if not API_KEY:
        print("  ❌ DATA_GO_KR_API_KEY 환경변수가 없습니다.")
        return None
    try:
        # 기준일 종가·시총
        start_item = get_price_on_date(ticker, START_DATE)
        if not start_item:
            print(f"  [{name}] 기준일 데이터 없음")
            return None
        start_price = int(start_item["clpr"])
        start_cap   = int(start_item["mrktTotAmt"])

        # 최근 종가·시총
        today  = datetime.today()
        recent = get_price_range(
            ticker,
            (today - timedelta(days=60)).strftime("%Y%m%d"),
            today.strftime("%Y%m%d"),
            num=25,
        )
        if not recent:
            print(f"  [{name}] 최근 데이터 없음")
            return None
        end_item  = recent[-1]
        end_price = int(end_item["clpr"])
        end_cap   = int(end_item["mrktTotAmt"])
        end_date  = end_item["basDt"]

        # 수익률
        ret = round((end_price - start_price) / start_price * 100) if start_price > 0 else None
        # 시총 증가율
        cap_growth = round((end_cap - start_cap) / start_cap * 100) if start_cap > 0 else None
        # 수익률 - 시총증가
        ret_minus_cap = round(ret - cap_growth) if (ret is not None and cap_growth is not None) else None

        # 거래대금 증가 배수
        early = get_price_range(
            ticker,
            START_DATE,
            (datetime.strptime(START_DATE, "%Y%m%d") + timedelta(days=60)).strftime("%Y%m%d"),
            num=25,
        )
        tv_ratio = None
        if early and len(early) >= 5 and len(recent) >= 5:
            e_avg = sum(int(x["trPrc"]) for x in early[:20])  / min(20, len(early))
            r_avg = sum(int(x["trPrc"]) for x in recent[-20:]) / min(20, len(recent))
            tv_ratio = round(r_avg / e_avg, 2) if e_avg > 0 else None

        print(f"  [{name}] ✅ 수익률 {ret}%  거래대금증가 {tv_ratio}x")
        return {
            "ticker": ticker, "name": name,
            "tv_ratio": tv_ratio, "ret": ret,
            "ret_minus_cap": ret_minus_cap, "end_date": end_date,
        }
    except Exception as e:
        print(f"  [{name}] 오류: {e}")
        return None


# ── HTML 생성 ──────────────────────────────────────────────────────────────────

def row_bg(ret):
    if ret is None: return ""
    if ret >= 300:  return "row-yellow"
    if ret >= 120:  return "row-green"
    if ret < 40:    return "row-pink"
    return ""

def cell_class(val):
    if val is None: return ""
    if val >= 100:  return "cell-yellow"
    if val >= 30:   return "cell-green"
    if val < 0:     return "cell-pink"
    return ""

def fmt_pct(v):   return f"{v:+d}%" if v is not None else "—"
def fmt_ratio(v): return f"{v:.2f}" if v is not None else "—"


def build_html(rows, generated_at, end_date):
    s = START_DATE
    start_fmt = f"{s[:4]}.{s[4:6]}.{s[6:]}"
    end_fmt   = f"{end_date[:4]}.{end_date[4:6]}.{end_date[6:]}"
    tbody = ""
    for r in rows:
        rc = row_bg(r["ret"])
        cc = cell_class(r["ret_minus_cap"])
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
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,'Malgun Gothic',sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:2rem 1rem}}
    h1{{font-size:1.3rem;margin-bottom:.3rem;color:#fff}}
    .subtitle{{font-size:.8rem;color:#888;margin-bottom:.4rem}}
    .updated{{font-size:.75rem;color:#666;margin-bottom:1.5rem}}
    .table-wrap{{overflow-x:auto;width:100%;max-width:680px}}
    table{{width:100%;border-collapse:collapse;background:#16213e;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.5)}}
    thead tr{{background:#0f3460}}
    th{{padding:12px 16px;font-size:.78rem;color:#a0b4d0;font-weight:600;text-align:right;white-space:nowrap}}
    th:first-child{{text-align:left}}
    td{{padding:10px 16px;font-size:.88rem;border-bottom:1px solid #1e2d4a}}
    tr:last-child td{{border-bottom:none}}
    td.name{{font-weight:700;color:#fff;text-align:left}}
    td.name .ticker{{display:block;font-size:.7rem;font-weight:400;color:#556}}
    td.num{{text-align:right;font-variant-numeric:tabular-nums}}
    tr.row-yellow td{{background:rgba(255,230,0,.18)}}
    tr.row-green td{{background:rgba(80,200,100,.15)}}
    tr.row-pink td{{background:rgba(230,100,100,.13)}}
    td.cell-yellow{{color:#ffe600;font-weight:700}}
    td.cell-green{{color:#50c864;font-weight:600}}
    td.cell-pink{{color:#ff7070}}
    .legend{{margin-top:1.2rem;display:flex;gap:1rem;flex-wrap:wrap;justify-content:center}}
    .legend-item{{font-size:.72rem;color:#888;display:flex;align-items:center;gap:.35rem}}
    .dot{{width:10px;height:10px;border-radius:2px}}
    .dot-y{{background:rgba(255,230,0,.6)}}
    .dot-g{{background:rgba(80,200,100,.5)}}
    .dot-p{{background:rgba(230,100,100,.45)}}
  </style>
</head>
<body>
  <h1>🇰🇷 한국 주요 종목 추적</h1>
  <div class="subtitle">기준일: {start_fmt} → {end_fmt} 종가 기준</div>
  <div class="updated">마지막 업데이트: {generated_at} (KST)</div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>종목</th><th>거래대금 증가</th><th>수익률</th><th>수익률 − 시총증가</th></tr></thead>
      <tbody>{tbody}</tbody>
    </table>
  </div>
  <div class="legend">
    <div class="legend-item"><div class="dot dot-y"></div>수익률 ≥ 300%</div>
    <div class="legend-item"><div class="dot dot-g"></div>수익률 ≥ 120%</div>
    <div class="legend-item"><div class="dot dot-p"></div>수익률 &lt; 40%</div>
  </div>
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    now_kst      = datetime.utcnow() + timedelta(hours=9)
    generated_at = now_kst.strftime("%Y-%m-%d %H:%M")

    print(f"기준일: {START_DATE}")
    print(f"API KEY: {'있음 ✅' if API_KEY else '없음 ❌  →  DATA_GO_KR_API_KEY 환경변수를 설정하세요'}")
    print(f"총 {len(TICKERS)}개 종목 처리 중...\n")

    results  = []
    end_date = now_kst.strftime("%Y%m%d")

    for ticker, name in TICKERS:
        print(f"  처리 중: {name} ({ticker})")
        row = fetch_metrics(ticker, name)
        if row:
            results.append(row)
            end_date = row["end_date"]
        time.sleep(0.3)

    results.sort(key=lambda x: x["ret"] if x["ret"] is not None else -9999, reverse=True)

    html = build_html(results, generated_at, end_date)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ {OUTPUT_FILE} 생성 완료 ({len(results)}개 종목)")


if __name__ == "__main__":
    main()
