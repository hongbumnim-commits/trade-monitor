"""
한국 주요 종목 수익률 테이블 생성기
- 종목 선정: 당일 거래대금 상위 20개 자동 선정
- 기준 기간: 1주일 전 대비 오늘
- 데이터: 공공데이터포털 금융위원회_주식시세정보 API
- 환경변수: DATA_GO_KR_API_KEY (GitHub Secrets)
"""

import os
import time
import requests
from datetime import datetime, timedelta

# ── 설정 ──────────────────────────────────────────────────────────────────────
API_KEY   = os.environ.get("DATA_GO_KR_API_KEY", "")
BASE_URL  = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
OUTPUT    = "index.html"
TOP_N     = 20   # 거래대금 상위 N개


# ── API 호출 ──────────────────────────────────────────────────────────────────

def call_api(params: dict) -> list:
    """API 호출 → items 리스트 반환 (실패 시 빈 리스트)"""
    try:
        r = requests.get(BASE_URL, params={**params, "serviceKey": API_KEY, "resultType": "json"}, timeout=15)
        body = r.json()["response"]["body"]
        total = int(body.get("totalCount", 0))
        if total == 0:
            return []
        items = body["items"]["item"]
        return [items] if isinstance(items, dict) else items
    except Exception as e:
        print(f"    API 오류: {e}")
        return []


def find_latest_trading_day(days_back: int = 0) -> str:
    """오늘 기준 N 영업일 이전 날짜 탐색 (공휴일·주말 자동 스킵)"""
    target = datetime.today() - timedelta(days=days_back)
    # 최근 14일 범위에서 데이터 있는 가장 최근 날 찾기
    end_dt  = target
    begin_dt = target - timedelta(days=14)
    items = call_api({
        "numOfRows": "5",
        "pageNo":    "1",
        "beginBasDt": begin_dt.strftime("%Y%m%d"),
        "endBasDt":   end_dt.strftime("%Y%m%d"),
        "srtnCd":    "005930",   # 삼성전자로 거래일 탐색
    })
    if not items:
        return end_dt.strftime("%Y%m%d")
    items.sort(key=lambda x: x["basDt"])
    return items[-1]["basDt"]


def get_top_by_volume(date: str, top_n: int = 20) -> list:
    """특정 날짜 거래대금 상위 N 종목 조회"""
    items = call_api({
        "numOfRows": str(top_n * 3),   # 여유있게 가져와서 상위 N개 추림
        "pageNo":    "1",
        "basDt":     date,
        "mrktCls":   "KOSPI",           # KOSPI 기준
    })
    if not items:
        # KOSPI 필터 없이 재시도
        items = call_api({
            "numOfRows": "100",
            "pageNo":    "1",
            "basDt":     date,
        })

    # 거래대금(trPrc) 내림차순 정렬 → 상위 N개
    try:
        items.sort(key=lambda x: int(x.get("trPrc", 0)), reverse=True)
    except Exception:
        pass
    return items[:top_n]


def get_price_on_date(srtn_cd: str, date: str) -> dict | None:
    """특정 종목의 특정 날짜 (또는 가장 가까운 이전 거래일) 시세"""
    begin = (datetime.strptime(date, "%Y%m%d") - timedelta(days=7)).strftime("%Y%m%d")
    items = call_api({
        "numOfRows": "10",
        "pageNo":    "1",
        "beginBasDt": begin,
        "endBasDt":   date,
        "srtnCd":    srtn_cd,
    })
    if not items:
        return None
    items.sort(key=lambda x: x["basDt"])
    # 날짜 <= date 중 가장 최근
    candidates = [i for i in items if i["basDt"] <= date]
    return candidates[-1] if candidates else items[-1]


# ── 지표 계산 ──────────────────────────────────────────────────────────────────

def build_row(today_item: dict, week_ago_date: str) -> dict | None:
    srtn_cd   = today_item.get("srtnCd", "")
    name      = today_item.get("itmsNm", srtn_cd)
    try:
        end_price   = int(today_item["clpr"])
        end_tv      = int(today_item.get("trPrc", 0))
        end_cap     = int(today_item.get("mrktTotAmt", 0))
        flt_rt      = today_item.get("fltRt", "")   # 전일 대비 등락률
    except Exception:
        return None

    # 1주일 전 시세
    week_item = get_price_on_date(srtn_cd, week_ago_date)
    if not week_item:
        return None
    try:
        start_price = int(week_item["clpr"])
        start_cap   = int(week_item.get("mrktTotAmt", 0))
        start_tv    = int(week_item.get("trPrc", 0))
    except Exception:
        return None

    if start_price <= 0 or end_price <= 0:
        return None

    # 수익률 (1주일)
    ret = round((end_price - start_price) / start_price * 100, 1)

    # 시총 증가율
    cap_growth = round((end_cap - start_cap) / start_cap * 100, 1) if start_cap > 0 else ret

    # 수익률 - 시총증가 (자사주 효과 등)
    ret_minus_cap = round(ret - cap_growth, 1)

    # 거래대금 증가 배수
    tv_ratio = round(end_tv / start_tv, 2) if start_tv > 0 else None

    return {
        "ticker":        srtn_cd,
        "name":          name,
        "end_price":     end_price,
        "start_price":   start_price,
        "flt_rt":        flt_rt,        # 오늘 등락률
        "ret":           ret,
        "cap_growth":    cap_growth,
        "ret_minus_cap": ret_minus_cap,
        "tv_ratio":      tv_ratio,
        "end_tv":        end_tv,
    }


# ── HTML 생성 ──────────────────────────────────────────────────────────────────

def color_ret(v):
    if v is None:    return "#aaa"
    if v > 0:        return "#ff5b5b"   # 상승: 빨강 (한국 주식 관습)
    if v < 0:        return "#4fc3f7"   # 하락: 파랑
    return "#aaa"

def fmt_price(v):  return f"{v:,}" if v else "—"
def fmt_pct(v):    return f"{v:+.1f}%" if v is not None else "—"
def fmt_ratio(v):  return f"{v:.2f}x" if v is not None else "—"
def fmt_tv(v):     return f"{v//100000000:,}억" if v and v > 0 else "—"


def build_html(rows: list, today_date: str, week_ago_date: str, generated_at: str) -> str:
    td = f"{today_date[:4]}.{today_date[4:6]}.{today_date[6:]}"
    wd = f"{week_ago_date[:4]}.{week_ago_date[4:6]}.{week_ago_date[6:]}"

    tbody = ""
    for r in rows:
        ret    = r["ret"]
        rc     = color_ret(ret)
        flt    = r["flt_rt"]
        flt_c  = "#ff5b5b" if flt and "-" not in str(flt) else "#4fc3f7"

        tbody += f"""
      <tr>
        <td class="name">
          {r['name']}<span class="ticker">{r['ticker']}</span>
        </td>
        <td class="num" style="color:#e0e0e0">{fmt_price(r['end_price'])}원</td>
        <td class="num" style="color:{flt_c}">{flt}%</td>
        <td class="num" style="color:{rc};font-weight:600">{fmt_pct(ret)}</td>
        <td class="num" style="color:#888">{fmt_price(r['start_price'])}원</td>
        <td class="num">{fmt_tv(r['end_tv'])}</td>
        <td class="num">{fmt_ratio(r['tv_ratio'])}</td>
        <td class="num" style="color:{'#ffe600' if r['ret_minus_cap'] and r['ret_minus_cap'] > 10 else '#888'}">{fmt_pct(r['ret_minus_cap'])}</td>
      </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>한국 거래대금 상위 종목</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,'Malgun Gothic',sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:2rem 1rem}}
    h1{{font-size:1.3rem;margin-bottom:.3rem;color:#fff}}
    .subtitle{{font-size:.8rem;color:#888;margin-bottom:.3rem}}
    .updated{{font-size:.72rem;color:#555;margin-bottom:1.5rem}}
    .wrap{{overflow-x:auto;width:100%;max-width:900px}}
    table{{width:100%;border-collapse:collapse;background:#16213e;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.5)}}
    thead tr{{background:#0f3460}}
    th{{padding:10px 12px;font-size:.72rem;color:#a0b4d0;font-weight:600;text-align:right;white-space:nowrap}}
    th:first-child{{text-align:left}}
    td{{padding:9px 12px;font-size:.83rem;border-bottom:1px solid #1e2d4a}}
    tr:last-child td{{border-bottom:none}}
    tr:hover td{{background:rgba(255,255,255,.03)}}
    td.name{{font-weight:700;color:#fff;text-align:left;min-width:120px}}
    td.name .ticker{{display:block;font-size:.68rem;font-weight:400;color:#445}}
    td.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
  </style>
</head>
<body>
  <h1>🇰🇷 거래대금 상위 {len(rows)}개 종목</h1>
  <div class="subtitle">기간: {wd} → {td} (1주일 수익률)</div>
  <div class="updated">업데이트: {generated_at} KST</div>
  <div class="wrap">
    <table>
      <thead>
        <tr>
          <th>종목</th>
          <th>현재가</th>
          <th>전일대비</th>
          <th>1주 수익률</th>
          <th>1주전 종가</th>
          <th>거래대금</th>
          <th>거래대금증가</th>
          <th>수익률-시총증가</th>
        </tr>
      </thead>
      <tbody>{tbody}</tbody>
    </table>
  </div>
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    now_kst      = datetime.utcnow() + timedelta(hours=9)
    generated_at = now_kst.strftime("%Y-%m-%d %H:%M")

    print(f"API KEY: {'있음 ✅' if API_KEY else '없음 ❌'}")

    # 오늘 & 1주일 전 거래일 탐색
    print("거래일 탐색 중...")
    today_date    = find_latest_trading_day(days_back=0)
    week_ago_date = find_latest_trading_day(days_back=7)
    print(f"오늘: {today_date}  /  1주일 전: {week_ago_date}")

    # 오늘 거래대금 상위 종목 수집
    print(f"\n거래대금 상위 {TOP_N}개 종목 수집 중...")
    top_items = get_top_by_volume(today_date, TOP_N)
    print(f"수집된 종목 수: {len(top_items)}")

    # 각 종목 지표 계산
    rows = []
    for item in top_items:
        name = item.get("itmsNm", "")
        cd   = item.get("srtnCd", "")
        print(f"  처리 중: {name} ({cd})")
        row = build_row(item, week_ago_date)
        if row:
            rows.append(row)
        time.sleep(0.2)

    # 수익률 내림차순 정렬
    rows.sort(key=lambda x: x["ret"] if x["ret"] is not None else -999, reverse=True)

    html = build_html(rows, today_date, week_ago_date, generated_at)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ {OUTPUT} 생성 완료 ({len(rows)}개 종목)")


if __name__ == "__main__":
    main()
