# 나라장터 발주계획·사전규격_용역 선별기

- 페이지: `index.html` (GitHub Pages로 공개)
- 데이터: `data/latest.json` — `.github/workflows/update.yml`이 매일 한국시간 08:30·17:00에 나라장터 OpenAPI로 수집해 갱신
- 수시 갱신: Actions › 나라장터 수집 › Run workflow
- 인증키: Settings › Secrets and variables › Actions › `NARA_API_KEY`

## 경쟁사 수주 현황 (별도 페이지)
- 페이지: `result.html` — 탭 4개: 개찰결과 / 계약정보 / 업체별 / 클라이언트별
- 경쟁사 목록: `data/companies.json` (엑셀 '필터리스트' 시트 + 사업자번호). 업체를 더하려면 이 파일의 `names`에 `정규화된 업체명: 통합명`을 추가
- 개찰결과: `data/result.json` ← `scripts/update_result.py` (낙찰정보서비스)
- 계약정보: `data/contracts.json` ← 2020~2026.10은 엑셀, 이후 `scripts/update_contracts.py` (계약정보서비스)로 이어 붙임
- 자동 수집: `.github/workflows/result.yml` — 한국시간 08~19시 매시 23분
