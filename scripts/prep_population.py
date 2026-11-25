"""KOSIS 주민등록인구(시도/시/군/구) 엑셀 -> data/population.csv (시도, 시군구, 인구).

사용: python prep_population.py <KOSIS 엑셀> [행안부 시군구 엑셀 ...]
행안부 파일의 시도는 KOSIS 표에서 통째로 교체(또는 추가)한다(KOSIS 표에 없는 개편 지역 보완용).
기준월은 표의 마지막 월(예: 2026.10)을 쓴다. 인구 = 해당 월 '계 (명)'.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent  # night-medical/


def main(src, extra):
    raw = pd.read_excel(src, sheet_name="데이터", header=None)
    months = list(dict.fromkeys(raw.iloc[0, 1:].dropna().tolist()))  # 병합 셀 중복 제거
    last = months[-1]
    col = 1 + 3 * (len(months) - 1)  # 마지막 월의 '계' 열
    rows, sido = [], None
    for _, r in raw.iloc[2:].iterrows():
        name = str(r.iloc[0])
        pop = r.iloc[col]
        if pd.isna(pop):
            continue
        clean = name.replace("　", "").strip()
        if clean == "전국":
            continue
        if not name.startswith("　"):
            sido = clean  # 들여쓰기 없음 = 시도
            continue
        rows.append({"sido": sido, "sigungu": clean, "population": int(pop), "base_month": last})
    out = pd.DataFrame(rows)
    # 세종: 시군구 구분이 없는 단일 지역 -> 시도 인구를 그대로 사용
    sejong = raw[raw.iloc[:, 0].astype(str).str.strip() == "세종특별자치시"]
    if len(sejong):
        out = pd.concat([out, pd.DataFrame([{"sido": "세종특별자치시", "sigungu": "세종특별자치시",
                                             "population": int(sejong.iloc[0, col]), "base_month": last}])])
    # 행안부 보완 파일: 해당 시도를 교체
    for f in extra:
        d = pd.read_excel(f, header=None, dtype=str)
        body = d.iloc[3:]
        add = []
        for _, r in body.iterrows():
            name = str(r.iloc[1]).strip()
            parts = name.split()
            if len(parts) < 2:
                continue  # 시도 합계 줄
            add.append({"sido": parts[0], "sigungu": " ".join(parts[1:]),
                        "population": int(str(r.iloc[2]).replace(",", "")), "base_month": last})
        add = pd.DataFrame(add)
        out = out[~out.sido.isin(add.sido.unique())]
        out = pd.concat([out, add])
    out["sigungu"] = out["sigungu"].str.replace("^통합", "", regex=True)  # 통합청주시 -> 청주시
    out = out.reset_index(drop=True)
    out.to_csv(ROOT / "data" / "population.csv", index=False, encoding="utf-8-sig")
    print(f"기준월 {last}, 시군구 {len(out)}개 -> data/population.csv")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
