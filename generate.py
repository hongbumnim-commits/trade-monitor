"""
한국 거래대금 상위 종목 1주일 수익률 테이블
- 종목 선정: 당일 거래대금 상위 20개 자동 선정
- 기준 기간: 실행일 기준 1주일 전 대비 오늘
- 데이터: 공공데이터포털 금융위원회_주식시세정보 API
- 환경변수: DATA_GO_KR_API_KEY (GitHub Secrets)
"""

import os
import time
import requests
from datetime import datetime, timedelta

API_KEY  = os.environ.get("DATA_GO_KR_API_KEY", "")
BASE_URL = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
OUTPUT   = "index.html"
TOP_N    = 20


# ── API ───────────────────────────────────────────────────────────────────────

def call_api(params: dict) -> list:
    try:
        r = requests.get(
            BASE_URL,
            params={**params, "serviceKey": API_KEY, "resultType": "json"},
            timeout=15,
        )
        body  = r.json()["response"]["body"]
        total = int(body.get("totalCount", 0))
        if total == 0:
            return []
        items = body["items"]["item"]
        return [items] if isinstance(items, dict) else items
    except Exception as e:
        print(f"    API 오류: {e}")
        return []


def latest_trading_date(before: str) -> str:
    """before(YYYYMMDD) 이하 가장 최근 거래일 반환"""
    begin = (datetime.strptime(before, "%Y%m%d") - timedelta(days=10)).strftime("%Y%m%d")
    # 삼성전자로 거래일 탐색
    items = call_api({"numOfRows": "10", "pageNo": "1",
                      "beginBasDt": begin, "endBasDt": before, "srtnCd": "005930"})
    if not items:
        return before
    return max(i["basDt"] for i in items if i["basDt"] <= before)


# ── 데이터 수집 ───────────────────────────────────────────────────────────────

def get_top_volume(date: str, n: int = 20) -> list:
    """해당 날짜 거래대금 상위 n개"""
    # 페이지당 100개씩 가져와서 정렬 후 상위 n개 추림
    all_items = []
    for page in range(1, 4):
        items = call_api({"numOfRows": "100", "pageNo": str(page), "basDt": date})
        if not items:
            break
        all_items.extend(items)
        if len(items) < 100:
            break

    if not all_items:
        return []

    # 거래대금 내림차순
    try:
        all_items.sort(key=lambda x: int(x.get("trPrc", 0) or 0), reverse=True)
    except Exception:
        pass
    return all_items[:n]


def get_stock_on_date(isin_cd: str, date: str) -> dict | None:
    """
    isinCd(12자리 국제코드)로 특정 날짜 이전 가장 최근 시세 조회.
    isinCd는 srtnCd보다 매칭이 정확합니다.
    """
    begin = (datetime.strptime(date, "%Y%m%d") - timedelta(days=10)).strftime("%Y%m%d")
    items = call_api({
        "numOfRows": "10",
        "pageNo":    "1",
        "beginBasDt": begin,
        "endBasDt":   date,
        "isinCd":    isin_cd,       # ← srtnCd 대신 isinCd 사용 (고유 매칭)
    })
    if not items:
        return None
    # date 이하 중 가장 최근
    candidates = sorted(
        [i for i in items if i["basDt"] <= date],
        key=lambda x: x["basDt"],
    )
    return candidates[-1] if candidates else None


# ── 지표 계산 ─────────────────────────────────────────────────────────────────

def build_row(today_item: dict, week_ago_date: str) -> dict | None:
    isin_cd   = today_item.get("isinCd", "")
    srtn_cd   = today_item.get("srtnCd", "")
    name      = today_item.get("itmsNm", srtn_cd)

    try:
        end_price = int(today_item["clpr"])
        end_tv    = int(today_item.get("trPrc", 0) or 0)
        end_cap   = int(today_item.get("mrktTotAmt", 0) or 0)
        flt_rt    = today_item.get("fltRt", "—")
    except Exception:
        return None

    if not isin_cd:
        return None

    # 1주일 전 시세 — isinCd로 정확히 매칭
    w = get_stock_on_date(isin_cd, week_ago_date)
    if not w:
        print(f"    [{name}] 1주일 전 데이터 없음")
        return None

    try:
        start_price = int(w["clpr"])
        start_tv    = int(w.get("trPrc", 0) or 0)
        start_cap   = int(w.get("mrktTotAmt", 0) or 0)
    except Exception:
        return None

    if start_price <= 0 or end_price <= 0:
        return None

    ret           = round((end_price - start_price) / start_price * 100, 1)
    cap_growth    = round((end_cap - start_cap) / start_cap * 100, 1) if start_cap > 0 else ret
    ret_minus_cap = round(ret - cap_growth, 1)
    tv_ratio      = round(end_tv / start_tv, 2) if start_tv > 0 else None

    return {
        "ticker":        srtn_cd,
        "name":          name,
        "end_price":     end_price,
        "start_price":   start_price,
        "flt_rt":        flt_rt,
        "ret":           ret,
        "ret_minus_cap": ret_minus_cap,
        "tv_ratio":      tv_ratio,
        "end_tv":        end_tv,
    }


# ── HTML ──────────────────────────────────────────────────────────────────────

def ret_color(v):
    if v is None: return "#aaa"
    return "#ff5b5b" if v > 0 else ("#4fc3f7" if v < 0 else "#aaa")

def p(v):    return f"{v:+.1f}%" if v is not None else "—"
def pr(v):   return f"{v:,}원"   if v else "—"
def ptv(v):  return f"{v//100000000:,}억" if v and v > 0 else "—"
def prat(v): return f"{v:.2f}x"  if v is not None else "—"


def build_html(rows, today_date, week_ago_date, generated_at):
    td = f"{today_date[:4]}.{today_date[4:6]}.{today_date[6:]}"
    wd = f"{week_ago_date[:4]}.{week_ago_date[4:6]}.{week_ago_date[6:]}"

    tbody = ""
    for r in rows:
        rc  = ret_color(r["ret"])
        flt = str(r["flt_rt"])
        fc  = "#ff5b5b" if "-" not in flt else "#4fc3f7"
        rmc_c = "#ffe600" if r["ret_minus_cap"] and r["ret_minus_cap"] > 10 else "#888"

        tbody += f"""
      <tr>
        <td class="name">{r['name']}<span class="tc">{r['ticker']}</span></td>
        <td class="n">{pr(r['end_price'])}</td>
        <td class="n" style="color:{fc}">{flt}%</td>
        <td class="n" style="color:{rc};font-weight:700">{p(r['ret'])}</td>
        <td class="n" style="color:#888">{pr(r['start_price'])}</td>
        <td class="n">{ptv(r['end_tv'])}</td>
        <td class="n">{prat(r['tv_ratio'])}</td>
        <td class="n" style="color:{rmc_c}">{p(r['ret_minus_cap'])}</td>
      </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>거래대금 상위 종목 1주 수익률</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,'Malgun Gothic',sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:2rem 1rem}}
    h1{{font-size:1.3rem;margin-bottom:.3rem;color:#fff}}
    .sub{{font-size:.8rem;color:#888;margin-bottom:.25rem}}
    .upd{{font-size:.72rem;color:#555;margin-bottom:1.5rem}}
    .wrap{{overflow-x:auto;width:100%;max-width:960px}}
    table{{width:100%;border-collapse:collapse;background:#16213e;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.5)}}
    thead tr{{background:#0f3460}}
    th{{padding:10px 12px;font-size:.72rem;color:#a0b4d0;font-weight:600;text-align:right;white-space:nowrap}}
    th:first-child{{text-align:left}}
    td{{padding:9px 12px;font-size:.83rem;border-bottom:1px solid #1e2d4a}}
    tr:last-child td{{border-bottom:none}}
    tr:hover td{{background:rgba(255,255,255,.03)}}
    td.name{{font-weight:700;color:#fff;text-align:left;min-width:110px}}
    td.name .tc{{display:block;font-size:.68rem;font-weight:400;color:#445}}
    td.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
  </style>
</head>
<body>
  <h1>🇰🇷 거래대금 상위 {len(rows)}개 종목</h1>
  <div class="sub">기간: {wd} → {td} (1주일 수익률)</div>
  <div class="upd">업데이트: {generated_at} KST</div>
  <div class="wrap">
    <table>
      <thead><tr>
        <th>종목</th><th>현재가</th><th>전일대비</th>
        <th>1주 수익률</th><th>1주전 종가</th>
        <th>거래대금</th><th>거래대금증가</th><th>수익률-시총증가</th>
      </tr></thead>
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

    today_str    = now_kst.strftime("%Y%m%d")
    week_ago_str = (now_kst - timedelta(days=7)).strftime("%Y%m%d")

    today_date    = latest_trading_date(today_str)
    week_ago_date = latest_trading_date(week_ago_str)
    print(f"오늘 거래일: {today_date}  /  1주일 전 거래일: {week_ago_date}")

    print(f"\n거래대금 상위 {TOP_N}개 수집 중 ({today_date})...")
    top_items = get_top_volume(today_date, TOP_N)
    print(f"수집 완료: {len(top_items)}개\n")

    rows = []
    for item in top_items:
        name = item.get("itmsNm", "")
        cd   = item.get("srtnCd", "")
        print(f"  {name} ({cd}) — 1주전 시세 조회 중...")
        row = build_row(item, week_ago_date)
        if row:
            rows.append(row)
        time.sleep(0.25)

    rows.sort(key=lambda x: x["ret"] if x["ret"] is not None else -999, reverse=True)

    html = build_html(rows, today_date, week_ago_date, generated_at)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 완료: {len(rows)}개 종목 / {OUTPUT} 생성")


if __name__ == "__main__":
    main()
