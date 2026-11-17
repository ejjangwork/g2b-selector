"""나라장터 발주계획·사전규격(일반용역) 수집 → 엑셀과 같은 열 형식의 data/latest.json
GitHub Actions에서 실행: 인증키는 저장소 Secret NARA_API_KEY 로 전달됨
사용법: python3 scripts/update.py data/latest.json
수집 기간: 월요일은 지난주 금요일 ~ 오늘(4일), 그 외 요일은 그저께 ~ 오늘(3일)
         → 공휴일이 하루 끼어도 놓치지 않도록 하루 여유를 둠
"""
import json, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

import os
KEY = os.environ['NARA_API_KEY'].strip()
OUT = sys.argv[1]
KST = timezone(timedelta(hours=9))
now = datetime.now(KST)


def start_day(d):
    """월요일(0)이면 3일 전(지난주 금요일), 그 외에는 2일 전(그저께)"""
    return d - timedelta(days=3 if d.weekday() == 0 else 2)


bg = start_day(now).strftime('%Y%m%d') + '0000'
en = now.strftime('%Y%m%d') + '2359'
BASE = 'https://apis.data.go.kr/1230000/ao/'


def call(path, params):
    url = BASE + path + '?' + urllib.parse.urlencode(dict(serviceKey=KEY, type='json', **params), safe='')
    for a in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.loads(r.read().decode())
            if 'response' not in d:
                raise RuntimeError(json.dumps(d, ensure_ascii=False)[:300])
            return d['response']['body']
        except Exception as e:
            err = e
            time.sleep(3 * (a + 1))
    raise err


def fetch_all(path, params):
    out, p = [], 1
    while True:
        b = call(path, dict(params, pageNo=p, numOfRows=999))
        it = b.get('items') or []
        if isinstance(it, dict):
            it = it.get('item', [])
            it = [it] if isinstance(it, dict) else it
        out += it
        if len(out) >= int(b.get('totalCount', 0)) or not it:
            return out
        p += 1


def ym(dt, add):
    m = dt.year * 12 + dt.month - 1 + add
    return f'{m // 12}{m % 12 + 1:02d}'


mask = lambda s: (str(s)[:1] + '**') if s else '-'
won = lambda s: f'{int(float(s)):,}' if str(s).strip() not in ('', 'None') else ''
day = lambda s: str(s)[:10].replace('-', '/')

# 발주계획 (용역) — 엑셀의 발주시기 기본범위와 같게 이번달-2 ~ +10개월
order = fetch_all('OrderPlanSttusService/getOrderPlanSttusListServc',
                  dict(inqryDiv=1, inqryBgnDt=bg, inqryEndDt=en, orderBgnYm=ym(now, -2), orderEndYm=ym(now, 10)))
order = sorted([x for x in order if x.get('bsnsDivNm') == '일반용역'], key=lambda x: x.get('nticeDt', ''), reverse=True)
H1 = ['No', '업무구분', '업무여부', '발주시기', '조달방식', '계약방법', '사업명', '수요기관', '소관구분\n(발주계획 당시)', '소관구분\n(현행)',
      '담당부서명', '담당자', '전화번호', '진행일자', '진행상태', '참조여부', '예산금액']
R1 = [[str(i + 1), x['bsnsDivNm'], '내자', f"{x['orderYear']}/{x['orderMnth']}", x.get('prcrmntMethd', ''), x.get('cntrctMthdNm', ''),
       x['bizNm'], x.get('orderInsttNm', ''), x.get('jrsdctnDivNm', ''), x.get('jrsdctnDivNm', ''), x.get('deptNm', ''), mask(x.get('ofclNm')), '-',
       day(x.get('nticeDt', '')), '작성완료', '', won(x.get('sumOrderAmt', ''))] for i, x in enumerate(order)]

# 사전규격 (용역)
pre = fetch_all('HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc', dict(inqryDiv=1, inqryBgnDt=bg, inqryEndDt=en))
pre = sorted([x for x in pre if x.get('bsnsDivNm') == '일반용역'], key=lambda x: x.get('rgstDt', ''), reverse=True)
nows = now.strftime('%Y-%m-%d %H:%M:%S')
H2 = ['No', '업무구분', '업무여부', '사업명', '수요기관', '공고기관', '담당자', '진행일자', '진행상태', '참조여부', '업체등록수', '예산금액']
R2 = [[str(i + 1), x['bsnsDivNm'], '내자', x['prdctClsfcNoNm'], x.get('rlDminsttNm', ''), x.get('orderInsttNm', ''), mask(x.get('ofclNm')),
       day(x.get('rgstDt', '')), '게시중' if (x.get('opninRgstClseDt') or '') >= nows else '마감', '', '', won(x.get('asignBdgtAmt', ''))]
      for i, x in enumerate(pre)]

created = now.strftime('%Y/%m/%d')
rng = f'{bg[:8]} - {en[:8]}'
aoa = lambda kind, H, R: [[f'발주목록_{kind}'], ['생성일 : ' + created], [f'진행일자 : {rng}'], ['업무구분 : 일반용역'], [], H] + R
json.dump({'generatedAt': now.strftime('%Y-%m-%d %H:%M'), 'range': rng, 'source': '나라장터 OpenAPI (공공데이터포털)',
           'sets': [{'aoa': aoa('사전규격공개', H2, R2)}, {'aoa': aoa('발주계획', H1, R1)}]},
          open(OUT, 'w'), ensure_ascii=False)
print(f'OK {now:%Y-%m-%d %H:%M} 기간 {rng} · 사전규격 {len(R2)}건 · 발주계획 {len(R1)}건')
