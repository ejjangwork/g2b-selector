# 나라장터 발주계획·사전규격_용역 선별기

- 페이지: `index.html` (GitHub Pages로 공개)
- 데이터: `data/latest.json` — `.github/workflows/update.yml`이 매일 한국시간 08:30·17:00에 나라장터 OpenAPI로 수집해 갱신
- 수시 갱신: Actions › 나라장터 수집 › Run workflow
- 인증키: Settings › Secrets and variables › Actions › `NARA_API_KEY`
