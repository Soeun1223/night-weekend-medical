# 밤·주말 의료 접근성 대시보드

**질문** 밤이나 주말에 아플 때, 우리 동네에서 갈 수 있는 병·의원과 응급의료기관은 인구 대비 얼마나 다른가?

Streamlit 대시보드입니다. 지역(시도·시군구), 요일, 시각, 기관 종류를 바꾸면 숫자와 차트가 함께 바뀝니다.

- 배포 주소: (Streamlit Community Cloud 주소를 여기에 적기)
- 실행: `python -m pip install -r requirements.txt` → `python -m streamlit run app.py`

## 차트
1. 인구 10만 명당 응급의료기관 수 (시도 또는 시군구별 막대)
2. 선택한 요일·시각에 운영 중인 병·의원 수 (10만 명당 막대)
3. 요일·시각 히트맵 (선택 지역)
4. 요일별 운영 시간 등록률
5. 지도: 운영 중 병·의원과 응급의료기관, 표와 CSV 저장

## 데이터 (자세한 기준은 sources.md)
| 파일 | 출처 |
|---|---|
| `data/facilities.csv` | 국립중앙의료원 전국 병·의원 찾기 서비스 (공공데이터포털) |
| `data/emergency.csv` | 국립중앙의료원 전국 응급의료기관 정보 조회 서비스 (공공데이터포털) |
| `data/population.csv` | 행정안전부 주민등록인구현황 (KOSIS 및 행안부 통계) 2026.10 |

앱은 `data/` 의 CSV만 읽으므로 배포에 API 키가 필요 없습니다.

## 데이터 다시 만들기 (선택)
1. `.env` 에 `DATA_GO_KR_KEY=<공공데이터포털 Decoding 키>` (저장소에 올리지 않음)
2. `python scripts/fetch_data.py` → `data/raw/*.csv`
3. `python scripts/prep_population.py <KOSIS 엑셀> [행안부 시군구 엑셀 ...]` → `data/population.csv`
4. `python scripts/build_app_data.py` → `data/facilities.csv`, `data/emergency.csv`, `data/meta.json`

## 한계
미등록 운영 시간은 '휴무'가 아니라 '모름'이며(일요일·공휴일은 등록률이 낮음), 기관 수는 거리·병상·진료과를 반영하지 않습니다. 인구가 적은 군 지역은 값이 크게 흔들립니다. 앱 화면의 "결론과 한계"에 같은 내용이 있습니다.
