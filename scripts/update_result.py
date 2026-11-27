"""나라장터 용역 개찰결과 수집 → data/result.json
GitHub Actions에서 실행: 인증키는 저장소 Secret NARA_API_KEY (조달청_나라장터 낙찰정보서비스 활용신청 필요)
사용법: python3 scripts/update_result.py data/result.json
       (처음 한 번 과거분을 채울 때: RESULT_FROM=20260101 python3 scripts/update_result.py data/result.json)

보관 기준
- 경쟁사(data/companies.json)가 개찰 1순위·최종낙찰자·참여업체 중 하나라도 있으면 → 계속 보관 (월별·연도별 집계용)
- 그 밖에 조사·연구 키워드(result.html 기본값)에 걸리는 건 → 최근 RECENT_DAYS일만 보관
- 조사·연구 키워드 사업과 경쟁사 1순위·낙찰 건은 참여업체 전체 순위(개찰순위)를 받음.
  최신 건부터 한 번에 MAX_DETAIL건씩, 받은 건은 다시 안 받음 → 과거분은 며칠에 걸쳐 채워짐
"""
import json, os, re, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import nz

KEY = os.environ['NARA_API_KEY'].strip()
OUT = sys.argv[1]
RECENT_DAYS = int(os.environ.get('RESULT_DAYS', '14'))
MAX_DETAIL = int(os.environ.get('RESULT_MAX_DETAIL', '20'))   # 15분마다 하루 약 48번 × 20 = 960건 (개발계정 하루 한도 1,000건 안쪽)
KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
start = datetime.strptime(os.environ['RESULT_FROM'], '%Y%m%d').replace(tzinfo=KST) if os.environ.get('RESULT_FROM') \
    else now - timedelta(days=RECENT_DAYS - 1)
recent_from = (now - timedelta(days=RECENT_DAYS - 1)).strftime('%Y-%m-%d')
BASE = 'https://apis.data.go.kr/1230000/as/ScsbidInfoService/'


def call(path, params):
    url = BASE + path + '?' + urllib.parse.urlencode(dict(serviceKey=KEY, type='json', **params), safe='')
    err = None
    for a in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.loads(r.read().decode())
            if 'response' not in d:
                raise RuntimeError(json.dumps(d, ensure_ascii=False)[:300])
            h = d['response'].get('header', {})
            if str(h.get('resultCode', '00')) not in ('00', '0'):
                raise RuntimeError(json.dumps(h, ensure_ascii=False))
            return d['response']['body']
        except Exception as e:
            err = e
            time.sleep(3 * (a + 1))
    raise err


def items_of(b):
    it = b.get('items') or []
    if isinstance(it, dict):
        it = it.get('item', [])
        it = [it] if isinstance(it, dict) else it
    return it


def fetch_all(path, params):
    out, p = [], 1
    while True:
        b = call(path, dict(params, pageNo=p, numOfRows=999))
        it = items_of(b)
        out += it
        if len(out) >= int(b.get('totalCount', 0) or 0) or not it:
            return out
        p += 1


def fetch_range(path, div=3):
    """7일씩 나눠서 받음. inqryDiv 1: 입력(등록)일시, 3: 개찰일시"""
    out, d = [], start
    while d.date() <= now.date():
        e = min(d + timedelta(days=6), now)
        out += fetch_all(path, dict(inqryDiv=div, inqryBgnDt=d.strftime('%Y%m%d') + '0000', inqryEndDt=e.strftime('%Y%m%d') + '2359'))
        d = e + timedelta(days=1)
    return out


# ---- 경쟁사 목록 · 기본 키워드 ----
CO = json.load(open(os.path.join(HERE, '..', 'data', 'companies.json'), encoding='utf-8'))


def grp(name, biz=''):
    return CO['biz'].get(str(biz or '').strip()) or CO['names'].get(nz(name)) or ''


html = open(os.path.join(HERE, '..', 'result.html'), encoding='utf-8').read()
kw = {k: [w.strip() for w in v.split(',') if w.strip()] for k, v in re.findall(r"^\s*(core|res|bl):\s*'([^']*)'", html, re.M)}
assert kw.get('core'), '키워드를 result.html에서 못 읽었어요'
is_kw = lambda nm: any(w in nm for w in kw['core'] + kw['res']) and not any(w in nm for w in kw['bl'])

num = lambda s: float(str(s).replace(',', '')) if str(s or '').strip() not in ('', 'None') else None
key = lambda x: '-'.join(str(x.get(k) or '0') for k in ('bidNtceNo', 'bidNtceOrd', 'bidClsfcNo', 'rbidNo'))


def corp(s):
    """opengCorpInfo: 업체명^사업자번호^대표자^투찰금액^투찰률"""
    p = (s or '').split('^')
    if len(p) < 2 or not p[0].strip():
        return None
    return {'nm': p[0].strip(), 'biz': p[1].strip(), 'amt': num(p[3]) if len(p) > 3 else None,
            'rate': num(p[4]) if len(p) > 4 else None, 'g': grp(p[0], p[1])}


# ---- 이전 결과 ----
prev = {}
try:
    prev = {x['k']: x for x in json.load(open(OUT, encoding='utf-8'))['items']}
except Exception:
    pass

# 입력일시(inptDt) 기준: 나라장터 '실제개찰일시'와 같은 값. 협상계약은 예정 개찰일(opengDt)보다 몇 주 늦게 결과가 올라와서,
# 예정일 기준으로 받으면 늦게 올라온 결과를 놓치거나 아래쪽에 묻힘
rows = fetch_range('getOpengResultListInfoServc', 1)

win, winrow = {}, {}
try:
    for x in fetch_range('getScsbidListSttusServc', 1) + fetch_range('getScsbidListSttusServc', 3):
        k = key(x)
        win[k] = {'nm': x.get('bidwinnrNm', ''), 'biz': x.get('bidwinnrBizno', ''), 'amt': num(x.get('sucsfbidAmt')),
                  'rate': num(x.get('sucsfbidRate')), 'date': str(x.get('fnlSucsfDate') or '')[:10],
                  'g': grp(x.get('bidwinnrNm'), x.get('bidwinnrBizno'))}
        winrow[k] = x
except Exception as e:
    print('낙찰자 목록 실패(건너뜀):', e)

fresh = {}
real = lambda x: str(x.get('inptDt') or x.get('opengDt') or '')[:16]
for x in sorted(rows, key=real, reverse=True):
    k = key(x)
    if k in fresh:
        continue
    status = x.get('progrsDivCdNm', '')
    cnt = int(num(x.get('prtcptCnum')) or 0)
    nm = x.get('bidNtceNm', '')
    it = {'k': k, 'no': f"{x.get('bidNtceNo')}-{x.get('bidNtceOrd', '')}", 'nm': nm,
          'inst': x.get('ntceInsttNm', ''), 'dmin': x.get('dminsttNm', ''), 'dt': real(x), 'sdt': str(x.get('opengDt', ''))[:16],
          'cnt': cnt, 'st': status, 'top': corp(x.get('opengCorpInfo')), 'win': win.get(k), 'ranks': None, 'kw': is_kw(nm)}
    old = prev.get(k)
    if old and old.get('ranks') is not None and old.get('st') == status:
        it['ranks'] = old['ranks']
    if it['ranks'] is None and cnt == 1 and it['top']:   # 단독 참가는 1순위가 곧 참여업체
        t = it['top']
        it['ranks'] = [['1', t['nm'], t['biz'], t['amt'], t['rate'], '', None, None, None]]
    fresh[k] = it

# 낙찰 목록에는 있는데 개찰 목록에 없는 경쟁사 낙찰 건도 넣음
for k, w in win.items():
    if k in fresh or not w['g']:
        continue
    x = winrow[k]
    old = prev.get(k) or {}
    fresh[k] = {'k': k, 'no': f"{x.get('bidNtceNo')}-{x.get('bidNtceOrd', '')}", 'nm': x.get('bidNtceNm', ''), 'inst': old.get('inst', ''),
                'dmin': x.get('dminsttNm', ''), 'dt': old.get('dt') or str(x.get('rlOpengDt', ''))[:16], 'cnt': int(num(x.get('prtcptCnum')) or 0),
                'st': old.get('st') or '낙찰', 'top': old.get('top'), 'win': w, 'ranks': old.get('ranks'), 'kw': is_kw(x.get('bidNtceNm', ''))}

items = dict(prev)
items.update(fresh)


def need_ranks(it):
    """참여업체 전체 순위가 필요한 건: 조사·연구 키워드 사업이거나 경쟁사가 1순위/낙찰인 건 중 2곳 이상 참가"""
    comp = (it.get('top') or {}).get('g') or (it.get('win') or {}).get('g')
    return it.get('ranks') is None and (it.get('kw') or comp) and (it.get('cnt') or 0) > 1 and '유찰' not in (it.get('st') or '')


# 개찰순위: 조사 성격이 강한 사업(추천 키워드) → 나머지 순, 각각 최신 건부터 한 번에 MAX_DETAIL건
# (과거분은 여러 번에 나눠 채움, API 하루 한도 고려)
is_core = lambda nm: any(w in nm for w in kw['core'])
newdetail, fails = 0, 0
for it in sorted((i for i in items.values() if need_ranks(i)), key=lambda i: (is_core(i['nm']), i['dt']), reverse=True):
    if newdetail >= MAX_DETAIL or fails >= 3:
        break
    no, ord_, cls, rb = it['k'].split('-')
    try:
        r = fetch_all('getOpengResultListInfoOpengCompt', dict(bidNtceNo=no, bidNtceOrd=ord_, bidClsfcNo=cls, rbidNo=rb))
        it['ranks'] = [[str(y.get('opengRank', '')), y.get('prcbdrNm', ''), y.get('prcbdrBizno', ''),
                        num(y.get('bidprcAmt')), num(y.get('bidprcrt')), y.get('rmrk', '') or '',
                        num(y.get('techEvlVal')), num(y.get('bidPrceEvlVal')), num(y.get('totalEvlAmtVal'))]
                       for y in sorted(r, key=lambda y: int(num(y.get('opengRank')) or 9999))]
        newdetail += 1
        fails = 0
    except Exception as e:
        fails += 1
        print('개찰순위 실패', it['k'], e)

# 참여업체 경쟁사 표시 + 보관 여부
for it in items.values():
    for r in it.get('ranks') or []:
        if len(r) < 10:
            r.append(grp(r[1], r[2]))
    it['g'] = sorted({g for g in [(it.get('top') or {}).get('g'), (it.get('win') or {}).get('g')] + [r[9] for r in it.get('ranks') or []] if g})
# 경쟁사 관련 → 계속 보관 / 키워드 사업 → 최근 2주 + 순위 받기 전(대기)까지 보관
keep = [it for it in items.values() if it['g'] or (it.get('kw') and (it['dt'][:10] >= recent_from or need_ranks(it)))]
keep.sort(key=lambda x: x['dt'], reverse=True)
pending = sum(1 for x in keep if need_ranks(x))

json.dump({'generatedAt': now.strftime('%Y-%m-%d %H:%M'), 'recentFrom': recent_from, 'pendingRanks': pending,
           'source': '나라장터 낙찰정보서비스 (공공데이터포털)', 'items': keep},
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'OK {now:%Y-%m-%d %H:%M} · 보관 {len(keep)}건 (경쟁사 관련 {sum(1 for x in keep if x["g"])}) · 개찰순위 새로 {newdetail}건 · 순위 대기 {pending}건')
