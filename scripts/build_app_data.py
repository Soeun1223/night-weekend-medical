"""data/raw/*.csv + data/population.csv -> 앱이 읽는 가벼운 CSV 3개 + meta.json.

실행: python scripts/build_app_data.py   (night-medical 폴더에서)
  data/facilities.csv  병·의원(요일별 운영 시간 포함, 앱에서 쓰는 열만)
  data/emergency.csv   응급의료기관
  data/meta.json       기준일과 제외 건수(앱이 출처·한계 문구에 그대로 사용)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "data"

# 의료기관이 아닌 분류(약국·구급차 등)는 제외한다.
DROP_KINDS = ["기타", "기타(구급차)"]


def main():
    pop = pd.read_csv(OUT / "population.csv", dtype={"base_month": str})
    key = ["sido", "sigungu"]
    meta = {"population_base_month": str(pop["base_month"].iloc[0]), "population_total": int(pop["population"].sum())}

    h = pd.read_csv(RAW / "hospitals.csv", dtype=str)
    meta["collected_at"] = h["fetched_at"].iloc[0]
    meta["hospitals_raw"] = len(h)
    h = h[~h["dutyDivNam"].isin(DROP_KINDS)].copy()
    meta["hospitals_after_kind_filter"] = len(h)

    # 인구 파일과 시군구가 맞지 않는 기관(주소에 시군구가 없는 경우 등)은 제외
    merged = h.merge(pop[key].assign(_ok=1), on=key, how="left")
    h = h[merged["_ok"].notna().values].copy()
    meta["hospitals_unmatched_region"] = meta["hospitals_after_kind_filter"] - len(h)

    out = pd.DataFrame({
        "hpid": h["hpid"], "name": h["dutyName"], "kind": h["dutyDivNam"],
        "sido": h["sido"], "sigungu": h["sigungu"], "addr": h["dutyAddr"],
        "lat": h["wgs84Lat"].astype(float).round(5), "lon": h["wgs84Lon"].astype(float).round(5),
        "er": (h["dutyEryn"] == "1").astype(int),
    })
    invalid = 0
    for d in range(1, 9):
        s = pd.to_numeric(h[f"dutyTime{d}s"], errors="coerce")
        c = pd.to_numeric(h[f"dutyTime{d}c"], errors="coerce")
        bad = s.notna() & c.notna() & (c <= s)  # 종료가 시작보다 이르거나 같음 = 입력 오류
        invalid += int(bad.sum())
        s, c = s.mask(bad), c.mask(bad)
        out[f"s{d}"] = s.astype("Int64")
        out[f"c{d}"] = c.astype("Int64")
    meta["invalid_time_cells"] = invalid
    out.to_csv(OUT / "facilities.csv", index=False)

    e = pd.read_csv(RAW / "emergency.csv", dtype=str)
    meta["emergency_raw"] = len(e)
    e = e.merge(pop[key].assign(_ok=1), on=key, how="left")
    meta["emergency_unmatched_region"] = int(e["_ok"].isna().sum())
    e = e[e["_ok"].notna()]
    pd.DataFrame({
        "hpid": e["hpid"], "name": e["dutyName"], "kind": e["dutyEmclsName"],
        "sido": e["sido"], "sigungu": e["sigungu"], "addr": e["dutyAddr"],
        "lat": e["wgs84Lat"].astype(float).round(5), "lon": e["wgs84Lon"].astype(float).round(5),
    }).to_csv(OUT / "emergency.csv", index=False)

    meta["facilities"], meta["emergency"] = len(out), len(e)
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
