"""공공데이터포털 API에서 병·의원 / 응급의료기관 전체 목록을 받아 data/raw/*.csv로 저장.

사용: python fetch_data.py
키: .env 의 DATA_GO_KR_KEY (Decoding 키). 값은 출력하지 않는다.
"""
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent.parent  # night-medical/
OUT = ROOT / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)


def load_key():
    key = os.environ.get("DATA_GO_KR_KEY")
    env = next((e for e in (ROOT / ".env", ROOT.parent / ".env") if e.exists()), None)
    if not key and env:
        for line in env.read_text().splitlines():
            if line.startswith("DATA_GO_KR_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("DATA_GO_KR_KEY가 없습니다 (.env 확인)")
    return key


BASE = "https://apis.data.go.kr/B552657"
APIS = {
    "hospitals": f"{BASE}/HsptlAsembySearchService/getHsptlMdcncListInfoInqire",
    "emergency": f"{BASE}/ErmctInfoInqireService/getEgytListInfoInqire",
}


def fetch_all(url, key, rows=1000):
    items, page, total = [], 1, None
    while True:
        for attempt in range(6):
            try:
                r = requests.get(
                    url,
                    params={"serviceKey": key, "pageNo": page, "numOfRows": rows},
                    timeout=(10, 60),
                )
                r.raise_for_status()
                break
            except requests.RequestException as e:
                # 예외 메시지에 URL(=키)이 들어 있으므로 종류만 출력
                print(f"  재시도 {attempt + 1}/6: {type(e).__name__}")
                time.sleep(2 * (attempt + 1))
        else:
            sys.exit("요청 6회 실패 (키 보호를 위해 상세 생략)")
        root = ET.fromstring(r.content)
        code = root.findtext(".//resultCode")
        if code != "00":
            sys.exit(f"API 오류 resultCode={code} msg={root.findtext('.//resultMsg')}")
        total = int(root.findtext(".//totalCount") or 0)
        for it in root.findall(".//item"):
            items.append({c.tag: (c.text or "").strip() for c in it})
        print(f"  page {page}: {len(items)}/{total}")
        if len(items) >= total or not root.findall(".//item"):
            break
        page += 1
        time.sleep(0.2)
    return pd.DataFrame(items)


def split_region(addr):
    parts = str(addr).split()
    sido = parts[0] if parts else ""
    sigungu = parts[1] if len(parts) > 1 else ""
    if sido == "세종특별자치시":  # 하위 시군구가 없는 단일 지역
        sigungu = "세종특별자치시"
    return sido, sigungu


def main():
    key = load_key()
    for name, url in APIS.items():
        print(f"[{name}]")
        df = fetch_all(url, key)
        if df.empty:
            print("  결과 없음")
            continue
        df[["sido", "sigungu"]] = df["dutyAddr"].apply(lambda a: pd.Series(split_region(a)))
        df["fetched_at"] = date.today().isoformat()
        df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")

        print(f"  행 {len(df)}, 컬럼 {list(df.columns)}")
        tcols = [c for c in df.columns if c.startswith("dutyTime")]
        print("  시간 컬럼 결측률(빈 문자열):")
        print(((df[tcols].isna() | df[tcols].eq("")).mean().round(3)).to_string())
        for c in ("wgs84Lat", "wgs84Lon"):
            if c in df:
                print(f"  {c} 결측률: {df[c].eq('').mean():.3f}")
        print("  시도별 기관 수:")
        print(df["sido"].value_counts().to_string())
        print("  시군구 수:", df.groupby(["sido", "sigungu"]).ngroups)
        if tcols:
            print("  예시 시간값:", df[tcols[0]].replace("", pd.NA).dropna().head(5).tolist())


if __name__ == "__main__":
    main()
