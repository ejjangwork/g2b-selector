"""나라장터 용역 계약정보(경쟁사) 수집 → data/contracts.json 에 이어 붙임
GitHub Actions에서 실행: 인증키는 저장소 Secret NARA_API_KEY (조달청_나라장터 계약정보서비스 활용신청 필요)
사용법: python3 scripts/update_contracts.py data/contracts.json
       (처음 한 번 엑셀 이후분을 채울 때: CONTRACT_FROM=20261001 ...)

- 등록일시 기준 최근 CONTRACT_DAYS일의 용역 계약을 받아, 업체목록에 경쟁사(data/companies.json)가 있는 것만 남김
- 공동수급이면 경쟁사마다 한 줄씩
- 같은 공고명(연도·용역·변경 등 제거)·같은 업체·같은 발주처·같은 해 계약은 한 건으로 보고 최신 계약만 남김 (변경계약 중복 제거)
  → 엑셀에서 가져온 과거 기록과 겹쳐도 API 쪽 최신 기록으로 바뀜
"""
import json, os, re, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import nz, ntitle

KEY = os.environ['NARA_API_KEY'].strip()
OUT = sys.argv[1]
KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
DAYS = int(os.environ.get('CONTRACT_DAYS', '7'))
start = datetime.strptime(os.environ['CONTRACT_FROM'], '%Y%m%d').replace(tzinfo=KST) if os.environ.get('CONTRACT_FROM') \
    else now - timedelta(days=DAYS - 1)
URL = 'https://apis.data.go.kr/1230000/ao/CntrctInfoService/getCntrctInfoListServc'
CO = json.load(open(os.path.join(HERE, '..', 'data', 'companies.json'), encoding='utf-8'))


def call(params):
    url = URL + '?' + urllib.parse.urlencode(dict(serviceKey=KEY, type='json', **params), safe='')
    err = None
    for a in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                d = json.loads(r.read().decode())
            if 'response' not in d:
                raise RuntimeError(json.dumps(d, ensure_ascii=False)[:300])
            return d['response']['body']
        except Exception as e:
            err = e
            time.sleep(3 * (a + 1))
    raise err


def fetch_day(d):
    out, p = [], 1
    while True:
        b = call(dict(inqryDiv=1, inqryBgnDt=d + '0000', inqryEndDt=d + '2359', pageNo=p, numOfRows=999))
        it = b.get('items') or []
        if isinstance(it, dict):
            it = it.get('item', [])
            it = [it] if isinstance(it, dict) else it
        out += it
        if len(out) >= int(b.get('totalCount', 0) or 0) or not it:
            return out
        p += 1


def grp(name, biz=''):
    return CO['biz'].get(str(biz or '').strip()) or CO['names'].get(nz(name)) or ''


data = json.load(open(OUT, encoding='utf-8'))
rows = data['rows']   # [날짜, 공고명, 발주처, 수주업체, 계약금액, key, 출처('x' 엑셀 / 'a' API), 통합계약번호, 기관구분, 단독·공동, 상세URL]
k_of = lambda r: (r[5], r[3], nz(r[2]), r[0][:4])
idx = {k_of(r): i for i, r in enumerate(rows)}

added = changed = scanned = 0
d = start
while d.date() <= now.date():
    for x in fetch_day(d.strftime('%Y%m%d')):
        scanned += 1
        if '용역' not in (x.get('bsnsDivNm') or ''):
            continue
        corps = [c.split('^') for c in re.findall(r'\[([^\]]*)\]', x.get('corpList') or '')]
        gs = []
        for c in corps:
            g = grp(c[3] if len(c) > 3 else '', c[9] if len(c) > 9 else '')
            if g and g not in gs:
                gs.append(g)
        if not gs:
            continue
        dm = [c.split('^') for c in re.findall(r'\[([^\]]*)\]', x.get('dminsttList') or '')]
        client = (dm[0][2] if dm and len(dm[0]) > 2 else '') or x.get('cntrctInsttNm', '')
        kind = (dm[0][3] if dm and len(dm[0]) > 3 else '') or x.get('cntrctInsttJrsdctnDivNm', '')
        date = (x.get('cntrctCnclsDate') or x.get('cntrctDate') or x.get('rgstDt') or '')[:10]
        amt = int(float(x.get('thtmCntrctAmt') or 0))
        joint = corps[0][2] if corps and len(corps[0]) > 2 else ''
        for g in gs:
            r = [date, x.get('cntrctNm', ''), client, g, amt, ntitle(x.get('cntrctNm', '')), 'a',
                 x.get('untyCntrctNo', ''), kind, joint, x.get('cntrctDtlInfoUrl', '')]
            k = k_of(r)
            if k in idx:
                old = rows[idx[k]]
                if old[6] == 'x' or old[0] <= date:
                    rows[idx[k]] = r
                    changed += 1
            else:
                idx[k] = len(rows)
                rows.append(r)
                added += 1
    d += timedelta(days=1)

rows.sort(key=lambda r: r[0], reverse=True)
data.update(generatedAt=now.strftime('%Y-%m-%d %H:%M'), rows=rows)
json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'OK {now:%Y-%m-%d %H:%M} · 계약 {scanned}건 확인 · 경쟁사 새 계약 {added}건 · 갱신 {changed}건 · 누적 {len(rows)}건')
