# 지원사업 찾기 에이전트 (라이너 해커톤 .EXE-THON 출품작 4차 버전: 실행 계획·문의처 전화 추가)
# 흐름: 상황 입력 → Liner Model이 검색어 생성 → Liner Search로 공고 검색 (공식 사이트 우선)
#      → 공고 원문 페이지를 직접 읽어 마감일·자격 발췌
#      → Liner Model이 자격 판단·쉬운 말 요약 → 모집 중 / 지난 공고 분류, 마감일순 정렬
#      → 신청서 초안 작성

import os
import json
import re
import datetime as dt
import time
import uuid
from html import escape
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st

# ---------- 설정 ----------
APP_NAME = "지원콕"  # 서비스 이름: 팀에서 정하면 이 글자만 바꾸세요
TAGLINE = "사는 곳과 하는 일을 적으면, 받을 수 있는 정부·지자체 지원사업을 찾아 마감일 순서로 알려 드려요."
MODEL = "liner-claude-router"
SEARCH_URL = "https://platform.liner.com/api/v1/tools/search/web"
CHAT_URL = "https://platform.liner.com/api/v1/chat/completions"


def get_api_key():
    try:
        return st.secrets["LINER_API_KEY"]
    except Exception:
        return os.environ.get("LINER_API_KEY", "")


API_KEY = get_api_key()
# 서버가 UTC여도 한국 날짜 기준으로 계산 (한국은 서머타임이 없어 고정 UTC+9; Windows에서 tzdata 없이도 동작)
KST = dt.timezone(dt.timedelta(hours=9))
TODAY = dt.datetime.now(KST).date()

st.set_page_config(page_title=f"{APP_NAME} · 지원사업 찾기", page_icon="📮", layout="centered")

# ---------- 화면 스타일 (큰 글씨, 높은 대비) ----------
st.markdown(
    """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
html, body, [class*="css"], .stMarkdown, input, textarea, button, label {
  font-family: 'Pretendard', 'Malgun Gothic', sans-serif !important;
}
html { font-size: 20px; }
.stApp { background: #FFFFFF; color: #1F2A37; }
h1 { font-size: 2.1rem !important; font-weight: 800 !important; color: #0E5E6F !important; letter-spacing: -0.02em; }
label, .stTextInput label p, .stNumberInput label p, .stTextArea label p { font-size: 1.05rem !important; font-weight: 600 !important; }
input, textarea { font-size: 1.1rem !important; }
.stButton > button, .stDownloadButton > button {
  font-size: 1.05rem !important; font-weight: 700; padding: 0.6rem 1.1rem;
  background: #FFFFFF; color: #0E5E6F; border: 2px solid #0E5E6F; border-radius: 10px;
}
.stButton > button:hover, .stDownloadButton > button:hover { background: #EEF6F8; color: #0A4855; border-color: #0A4855; }
.stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"], button[data-testid="baseButton-primary"] {
  font-size: 1.2rem !important; padding: 0.8rem 1.4rem; background: #0E5E6F; color: #FFFFFF; border: none;
}
.stButton > button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="baseButton-primary"]:hover { background: #0A4855; color: #FFFFFF; }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible { outline: 3px solid #F2B705; outline-offset: 2px; }
/* 머리 부분 */
.brand { padding: 0.4rem 0 1.2rem 0; border-bottom: 3px solid #0E5E6F; margin-bottom: 1.4rem; }
.brand-name { font-size: 3rem; font-weight: 900; color: #0E5E6F; letter-spacing: -0.04em; line-height: 1.1; }
.brand-name small { font-size: 1.1rem; font-weight: 700; color: #1F2A37; letter-spacing: -0.01em; margin-left: 0.6rem; }
.brand-line { font-size: 1.05rem; color: #374151; margin: 0.5rem 0 0 0; line-height: 1.6; }
/* 단계 제목 */
.step { display: flex; align-items: center; gap: 0.6rem; font-size: 1.35rem; font-weight: 800; color: #1F2A37; margin: 1.6rem 0 0.6rem 0; }
.step i { font-style: normal; display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem;
  border-radius: 50%; background: #0E5E6F; color: #FFFFFF; font-size: 1.05rem; flex: none; }
/* 결과 한눈 요약 */
.tally { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.6rem; margin: 0.4rem 0 1rem 0; }
.tally div { border-radius: 10px; padding: 0.7rem 0.5rem; text-align: center; }
.tally b { display: block; font-size: 1.8rem; line-height: 1.1; }
.tally span { font-size: 0.85rem; font-weight: 600; }
.tally .t-ok { background: #E3F4E8; color: #1F7A3A; }
.tally .t-check { background: #FFF2D6; color: #8A5300; }
.tally .t-past { background: #EEF0F3; color: #4B5563; }
h3 { font-size: 1.3rem !important; }
.body h3 { font-size: 1.2rem !important; }
.call { display: inline-block; margin-left: 0.4rem; padding: 0.15rem 0.7rem; border-radius: 999px;
  background: #0E5E6F; color: #FFFFFF !important; font-weight: 700; font-size: 0.95rem; text-decoration: none !important; }
.task { display: flex; gap: 0.7rem; align-items: baseline; }
.kind { flex: none; font-size: 0.8rem; font-weight: 700; padding: 0.1rem 0.5rem; border-radius: 6px; background: #EEF6F8; color: #0E5E6F; }
.kind.k-접수 { background: #FDECEA; color: #B42318; }
.kind.k-전화 { background: #FFF2D6; color: #8A5300; }
.poweredby { font-size: 0.85rem; color: #4B5563; line-height: 1.6; margin-top: 0.4rem; }
.poweredby b { color: #0E5E6F; }
.card { display: flex; gap: 1.1rem; align-items: flex-start; }
.dday { width: 5.6rem; height: 5.6rem; flex: none; border-radius: 50%; border: 4px double #0E5E6F; color: #0E5E6F;
  display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
  transform: rotate(-6deg); margin-top: 0.2rem; }
.dday b { display: block; font-size: 1.35rem; line-height: 1.1; font-weight: 900; }
.dday span { font-size: 0.68rem; color: inherit; font-weight: 600; }
.dday.urgent { border-color: #B42318; color: #B42318; }
.body h3 { margin: 0 0 0.3rem 0; font-size: 1.2rem; }
.badge { display: inline-block; font-size: 0.85rem; font-weight: 700; padding: 0.15rem 0.6rem; border-radius: 999px; margin-bottom: 0.4rem; }
.ok { background: #E3F4E8; color: #1F7A3A; }
.check { background: #FFF2D6; color: #8A5300; }
.no { background: #EEF0F3; color: #4B5563; }
.body p { margin: 0.25rem 0; line-height: 1.6; }
.src { font-size: 0.85rem; }
.dday.past { border: 2px dashed #9CA3AF; color: #6B7280; transform: none; }
.dday.past b { font-size: 1.15rem; }
@media (max-width: 520px) { .card { flex-direction: column; } .brand-name { font-size: 2.4rem; } }
.official { display: inline-block; font-size: 0.75rem; font-weight: 700; color: #0E5E6F;
  border: 1.5px solid #0E5E6F; border-radius: 6px; padding: 0 0.35rem; margin-left: 0.35rem; }
.next { background: #EEF6F8; border-radius: 8px; padding: 0.35rem 0.6rem; font-weight: 600; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------- Liner 호출 함수 ----------
@st.cache_data(persist="disk", show_spinner=False)
def llm(prompt, system="", max_tokens=2500):
    # openai 패키지 없이 Liner Model API(Chat Completions)를 직접 호출
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    r = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "max_tokens": max_tokens},
        timeout=120,
    )
    if r.status_code == 402:
        raise RuntimeError("크레딧이 부족해요 (402). Liner 플랫폼에서 잔여 크레딧을 확인해 주세요.")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def parse_json(text):
    """모델 답변에서 JSON만 꺼내기 (```json 감싸기 등 제거). 답이 중간에 잘렸으면 완성된 항목까지만 살린다."""
    text = text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"(\[.*\]|\{.*\})", text, re.S)
    body = match.group(1) if match else text
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start = text.find("[")
        if start < 0:
            raise
        # 끝에서부터 '}' 위치를 하나씩 줄여 가며, 완성된 항목까지만 잘라 배열로 닫아 본다
        cut = len(text)
        while True:
            cut = text.rfind("}", start, cut)
            if cut < 0:
                raise
            try:
                return json.loads(text[start:cut + 1] + "]")
            except json.JSONDecodeError:
                continue


@st.cache_data(persist="disk", show_spinner=False)
def _search_cached(query, max_results, recent, day):
    return _liner_search_raw(query, max_results, recent)


def liner_search(query, max_results=8, recent=True):
    # 같은 날 같은 검색어는 저장된 결과를 다시 써서 크레딧을 아낌
    return _search_cached(query, max_results, recent, TODAY.isoformat())


def _liner_search_raw(query, max_results=8, recent=True):
    body = {
        "query": query,
        "country_code": "kr",
        "lang": "ko",
        "max_results": max_results,
        "include_knowledge": False,  # 숫자 데이터가 필요 없어서 끄면 비용이 절반
    }
    if recent:
        body["date_range"] = "past_year"
    for attempt in range(2):
        r = requests.post(SEARCH_URL, headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
                          json=body, timeout=30)
        if r.status_code == 429 and attempt == 0:  # 너무 빨리 많이 부르면 잠깐 쉬었다 다시
            time.sleep(2)
            continue
        break
    r.raise_for_status()
    return r.json().get("results", [])


# ---------- 공고 원문 읽기 ----------
OFFICIAL_SUFFIX = (".go.kr", ".or.kr", ".re.kr")
KEYWORDS = ["신청기간", "접수기간", "모집기간", "신청 기간", "접수 기간", "마감", "공고일",
            "지원대상", "신청자격", "지원 대상", "지원내용", "지원 내용", "지원규모",
            "제출서류", "제출 서류", "구비서류", "구비 서류", "신청서류", "첨부서류", "증빙서류",
            "문의", "문의처", "담당", "연락처", "전화"]


BLOCKED_HOSTS = ("youtube.com", "youtu.be", "instagram.com", "facebook.com", "tiktok.com",
                 "x.com", "twitter.com", "threads.net", "pinterest.com")
LOW_PRIORITY = ("blog.naver.com", "m.blog.naver.com", "tistory.com", "brunch.co.kr", "cafe.naver.com")


def host_of(url):
    return re.sub(r"^https?://", "", url or "").split("/")[0].lower()


def source_rank(url):
    """0 = 공식 사이트, 1 = 일반, 2 = 블로그·카페, 9 = SNS·영상(제외)"""
    h = host_of(url)
    if any(h == b or h.endswith("." + b) for b in BLOCKED_HOSTS):
        return 9
    if is_official(url):
        return 0
    if any(h == b or h.endswith("." + b) for b in LOW_PRIORITY):
        return 2
    return 1


def is_official(url):
    host = re.sub(r"^https?://", "", url or "").split("/")[0].lower()
    return host.endswith(OFFICIAL_SUFFIX)


class _TextGrab(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "nav", "header", "footer"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "nav", "header", "footer") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def fetch_page_text(url, limit=3200):
    """공고 페이지를 열어 마감일·자격이 적힌 부분 위주로 글자를 뽑는다. 실패하면 빈 문자열."""
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if "html" not in r.headers.get("Content-Type", "html"):
            return ""
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        g = _TextGrab()
        g.feed(r.text)
        text = re.sub(r"\s+", " ", " ".join(g.parts))
    except Exception:
        return ""
    spans = []
    for kw in KEYWORDS:
        for m in re.finditer(re.escape(kw), text):
            spans.append((max(0, m.start() - 150), m.end() + 300))
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    picked = " … ".join(text[a:b] for a, b in merged)
    out = (text[:500] + " … " + picked) if picked else text[:1500]
    return out[:limit]


def read_pages(results, n=12):
    targets = results[:n]
    with ThreadPoolExecutor(max_workers=6) as ex:
        texts = list(ex.map(lambda r: fetch_page_text(r.get("url", "")), targets))
    for r, t in zip(targets, texts):
        r["page_text"] = t
    return sum(1 for t in texts if t)


# ---------- 에이전트 단계 ----------
def make_queries(profile, short):
    prompt = f"""다음 사람이 받을 수 있는 한국 정부·지자체 지원사업, 보조금, 정책보험, 재취업·교육 지원 공고를 찾으려 합니다.
웹 검색어 5개를 만들어 주세요. 지역명, 업종, 연도({TODAY.year})를 적절히 넣고, 서로 다른 각도(지자체 공고, 중앙부처 사업, 보험, 교육·재취업 등)로 만드세요.
정부·공공기관 공고문이 잘 걸리도록 '공고', '모집', '시행계획' 같은 공고문 단어와 주관 기관 이름(예: 시청, 도청, 해양수산부, 소상공인시장진흥공단)을 넣으세요.
JSON 문자열 배열로만 답하세요.

상황: {profile}"""
    try:
        queries = parse_json(llm(prompt, max_tokens=500))
        return [q for q in queries if isinstance(q, str)][:5]
    except Exception:
        return [f"{short} 지원사업 {TODAY.year}", f"{short} 보조금 공고"]


def judge(profile, results):
    listing = "\n".join(
        f"[{i}] 제목: {r.get('title','')}\n    날짜: {r.get('date','')}\n    URL: {r.get('url','')}"
        f"{'  (공식 사이트)' if is_official(r.get('url','')) else ''}\n    요약: {r.get('description','')}"
        + (f"\n    원문 발췌: {r['page_text']}" if r.get('page_text') else "")
        for i, r in enumerate(results)
    )
    system = "당신은 중장년 자영업자·농어업인·퇴직자를 돕는 지원사업 상담사입니다. 검색 결과에 없는 사실은 절대 지어내지 않습니다."
    prompt = f"""오늘 날짜: {TODAY.isoformat()}
신청자 상황: {profile}

아래 검색 결과 중 실제 지원사업·보조금·보험·교육 공고로 보이는 것만 골라 정리하세요. 최대 12개까지만, 신청자에게 가장 쓸모 있는 순서로 고르세요.
같은 사업이 여러 번 나오면 하나로 합치고, 이때 index는 공식 사이트(.go.kr 등) 결과를 고르세요.
지원사업이 아닌 뉴스·광고·블로그 잡담은 빼세요.
마감일·자격은 '원문 발췌'를 가장 먼저 보고, 없으면 요약을 보세요. 근거 없는 날짜를 지어내지 마세요.
각 항목은 아래 JSON 객체로, 전체는 JSON 배열로만 답하세요.

{{
 "index": 검색결과 번호(정수),
 "name": "사업 이름",
 "agency": "주관 기관 (모르면 '확인 필요')",
 "summary": "무엇을 얼마나 지원하는지 중학생도 알아듣게 1~2문장",
 "eligibility": "누가 받을 수 있는지 쉬운 말로",
 "deadline": "YYYY-MM-DD 형식 신청 마감일. 근거가 없으면 null",
 "announce_date": "YYYY-MM-DD 형식 공고일. 근거가 없으면 null",
 "status": "모집 중" 또는 "모집 예정" 또는 "지난 공고" 또는 "알 수 없음",
 "next_expected": "지난 공고일 때만: 이 공고가 나온 시기를 근거로 내년 언제쯤 다시 나올지 한 문장 (예: '매년 1월 공고, 2027년 1월 무렵 재공고 예상'). 근거 없으면 null",
 "verdict": "가능" 또는 "확인 필요" 또는 "해당 없음",
 "reason": "그렇게 판단한 이유 한 문장",
 "documents": ["원문 발췌에 적힌 제출 서류 이름들 (예: '사업자등록증 사본'). 원문에 서류 목록이 없으면 빈 배열 []. 절대 지어내지 마세요"],
 "next_month": "지난 공고일 때만: 다음 공고가 나올 것으로 예상되는 달 YYYY-MM. 근거 없으면 null",
 "contact": "원문 발췌에 적힌 담당 부서와 전화번호 (예: '통영시청 수산과 055-650-0000'). 원문에 없으면 null. 전화번호를 절대 지어내지 마세요"
}}

status: 오늘 날짜와 마감일을 비교해 정하세요. 마감일이 지났으면 "지난 공고".
verdict는 '자격'만 봅니다(마감 여부와 상관없이): 지역·업종·나이 조건이 분명히 맞으면 "가능", 정보가 부족하면 "확인 필요", 조건이 분명히 안 맞으면 "해당 없음".

검색 결과:
{listing}"""
    items = parse_json(llm(prompt, system=system, max_tokens=8000))
    items = [it for it in items if isinstance(it, dict)]
    for it in items:
        idx = it.get("index")
        if isinstance(idx, int) and 0 <= idx < len(results):
            it["url"] = results[idx].get("url", "")
            it["host"] = results[idx].get("hostname", "")
    return items


def days_left(deadline):
    try:
        return (dt.date.fromisoformat(deadline) - TODAY).days
    except Exception:
        return None


def is_past(it):
    d = days_left(it.get("deadline") or "")
    if d is not None:
        return d < 0
    return it.get("status") == "지난 공고"


def sort_items(items):
    order = {"가능": 0, "확인 필요": 1, "해당 없음": 2}

    def key(it):
        d = days_left(it.get("deadline") or "")
        return (order.get(it.get("verdict"), 1), d if d is not None and d >= 0 else 9999)

    return sorted(items, key=key)


def draft_application(profile, item):
    prompt = f"""아래 지원사업의 신청서 초안을 써 주세요.

신청자 상황: {profile}
사업 이름: {item.get('name')}
주관 기관: {item.get('agency')}
지원 내용: {item.get('summary')}
자격: {item.get('eligibility')}
공고에 적힌 제출 서류: {', '.join(item.get('documents') or []) or '알 수 없음'}

규칙:
- 이름, 주민등록번호, 연락처, 주소, 사업자번호 같은 개인정보는 절대 채우지 말고 [이름], [연락처]처럼 빈칸으로 두세요.
- 실제 공고 양식을 모르므로 일반적인 항목(신청 동기, 현재 사업 현황, 지원금 사용 계획, 기대 효과)으로 구성하세요.
- 신청자가 고쳐 쓰기 쉽게 쉬운 말로, 각 항목 3~5문장.
- 제출 서류가 주어졌으면 맨 끝에 "함께 낼 서류" 체크 목록(- [ ] 형식)으로 정리하세요.
- 맨 끝에 "제출 전 공고 원문의 서식과 필요 서류를 꼭 확인하세요."를 넣으세요."""
    return llm(prompt, max_tokens=2500)


PHONE_RE = re.compile(r"(0\d{1,2}|1\d{3})[-.\s)]?\d{3,4}[-.\s]?\d{4}|1\d{3}[-.\s]\d{4}")


def phone_of(text):
    """문의처 문장에서 전화번호 하나를 꺼내 (보여줄 글자, tel: 번호)로 돌려줌"""
    m = PHONE_RE.search(text or "")
    if not m:
        return None
    shown = m.group(0)
    return shown, re.sub(r"\D", "", shown)


def make_plan(profile, chosen):
    """고른 지원사업들로 오늘부터 마감까지 날짜별 할 일 목록을 만든다."""
    listing = "\n".join(
        f"- 사업: {it.get('name')}\n  상태: {it.get('status')} / 자격 판단: {it.get('verdict')} ({it.get('reason')})\n"
        f"  마감일: {it.get('deadline') or '알 수 없음'}\n  재공고 예상: {it.get('next_expected') or '-'}\n"
        f"  제출 서류: {', '.join(it.get('documents') or []) or '원문 확인 필요'}\n  문의처: {it.get('contact') or '원문 확인 필요'}"
        for it in chosen
    )
    system = "당신은 중장년 신청자가 지원사업을 놓치지 않고 실제로 신청하도록 돕는 실행 코치입니다. 주어진 정보에 없는 사실은 지어내지 않습니다."
    prompt = f"""오늘 날짜: {TODAY.isoformat()} ({'월화수목금토일'[TODAY.weekday()]}요일)
신청자 상황: {profile}

아래 지원사업들을 실제로 신청하기 위한 날짜별 할 일 목록을 만드세요.

{listing}

규칙:
- 날짜는 오늘부터 각 사업 마감일 사이로 잡으세요. 접수는 마감 2일 전까지 끝내도록 여유를 두세요.
- 순서: 자격이 '확인 필요'면 먼저 문의처에 전화로 확인 → 서류 떼기 → 신청서 작성 → 접수.
- 서류는 제출 서류 목록에 있는 것만 할 일로 만드세요. 목록이 없으면 '공고 원문에서 제출 서류 확인하기'를 할 일로 넣으세요.
- 전화번호를 지어내지 마세요. 문의처를 모르면 '공고 원문에서 문의처 찾아 전화하기'로 쓰세요.
- 마감일을 모르는 사업은 이번 주 안에 '원문에서 마감일 확인하기'를 넣으세요.
- 지난 공고는 재공고 전에 미리 할 수 있는 준비(서류 미리 떼기 등)만 넣고, 재공고 예상 달이 있으면 그 달 1일에 '재공고 확인'을 넣으세요.
- 하루에 할 일은 2개 이하로, 중장년이 부담 없게 나누세요. 전체 15개 이하.
- 할 일 문장은 "무엇을 어디서" 하는지 짧고 쉬운 말로.

JSON 배열로만 답하세요. 각 항목:
{{"date": "YYYY-MM-DD", "program": "사업 이름", "kind": "전화" 또는 "서류" 또는 "작성" 또는 "접수" 또는 "확인", "task": "할 일 한 문장"}}"""
    tasks = parse_json(llm(prompt, system=system, max_tokens=3000))
    out = []
    for t in tasks:
        if not isinstance(t, dict) or not t.get("task"):
            continue
        try:
            d = dt.date.fromisoformat(str(t.get("date")))
        except ValueError:
            d = TODAY
        t["date"] = max(d, TODAY).isoformat()
        out.append(t)
    return sorted(out, key=lambda t: t["date"])


def tasks_ics(tasks):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//jiwon-agent//KO", "CALSCALE:GREGORIAN"]
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for t in tasks:
        day = dt.date.fromisoformat(t["date"])
        title = f"[{t.get('kind') or '할 일'}] {t['task']}"
        lines += [
            "BEGIN:VEVENT", f"UID:{uuid.uuid4()}@jiwon-agent", f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_text(title)}", f"DESCRIPTION:{_ics_text('사업: ' + str(t.get('program') or ''))}",
            "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(title)}", "TRIGGER:PT9H", "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


# ---------- 달력(.ics) 만들기 ----------
def _ics_text(t):
    return str(t).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    # 달력 파일 규칙: 한 줄 75바이트 넘으면 접기 (한글이 깨지지 않게 글자 단위로)
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 73:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n".join(out)


def event_for(it):
    """모집 중이면 마감일, 지난 공고면 재공고 예상 달 1일에 일정을 만든다. 날짜가 없으면 None."""
    name = it.get("name") or "지원사업"
    if not is_past(it) and days_left(it.get("deadline") or "") is not None:
        day = dt.date.fromisoformat(it["deadline"])
        title, alarm = f"[마감] {name}", "-P3D"
    elif is_past(it) and re.fullmatch(r"\d{4}-\d{2}", it.get("next_month") or ""):
        y, m = map(int, it["next_month"].split("-"))
        day = dt.date(y, m, 1)
        if day <= TODAY:
            return None
        title, alarm = f"[재공고 확인] {name}", "-P0D"
    else:
        return None
    docs = it.get("documents") or []
    desc = (f"{it.get('summary') or ''}\n주관: {it.get('agency') or ''}\n"
            + (f"준비 서류: {', '.join(docs)}\n" if docs else "")
            + f"원문: {it.get('url') or ''}\n최종 자격과 마감일은 공고 원문에서 확인하세요.")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@jiwon-agent",
        f"DTSTAMP:{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_ics_text(title)}",
        f"DESCRIPTION:{_ics_text(desc)}",
    ] + ([f"URL:{it['url']}"] if it.get("url") else []) + [
        "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(title)}",
        f"TRIGGER;VALUE=DURATION:{alarm}" if alarm != "-P0D" else "TRIGGER:PT9H",
        "END:VALARM", "END:VEVENT",
    ]
    return lines


def make_ics(items):
    events = [ev for ev in (event_for(it) for it in items) if ev]
    if not events:
        return None, 0
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//jiwon-agent//KO", "CALSCALE:GREGORIAN"]
    for ev in events:
        lines += ev
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n", len(events)


# ---------- 화면 ----------
def step(n, text):
    st.markdown(f"<div class='step'><i>{n}</i>{escape(text)}</div>", unsafe_allow_html=True)


st.markdown(f"<div class='brand'><div class='brand-name'>{escape(APP_NAME)}<small>내가 받을 수 있는 지원사업 찾기</small></div>"
            f"<p class='brand-line'>{escape(TAGLINE)}</p></div>", unsafe_allow_html=True)

if not API_KEY:
    st.error("Liner API 키가 없어요. 설명서의 'API 키 넣기'를 따라 .streamlit/secrets.toml 파일을 만들어 주세요.")
    st.stop()

EXAMPLES = {
    "🐚 피조개 양식": {"region": "경남 통영시", "job": "피조개 양식업", "age": 58, "years": 3,
                    "memo": "가족과 함께 운영, 시설 노후로 장비 교체 필요"},
    "🌱 귀농 준비": {"region": "전북 완주군", "job": "카페 운영 (귀농 준비 중)", "age": 52, "years": 6,
                  "memo": "옷가게와 카페를 운영해 왔고, 내년 귀농해서 작물 재배를 시작하고 싶음"},
    "🏭 퇴직 후 재취업": {"region": "경남 창원시", "job": "제조업 퇴직 (생산직)", "age": 61, "years": 28,
                      "memo": "기계 부품 공장에서 28년 근무 후 퇴직, 재취업이나 기술 교육 희망"},
}
# 입력 칸 기본값 (처음 한 번만)
for k, v in {"region": "", "job": "", "age": 55, "years": 3, "memo": ""}.items():
    st.session_state.setdefault(k, v)


def fill_example(data):
    # 버튼을 누르면 화면을 그리기 전에 입력 칸 값을 바로 바꿈
    for k, v in data.items():
        st.session_state[k] = v


step(1, "내 상황 적기")
form = st.container(border=True)
form.write("**예시로 채우기** (가상의 인물이에요)")
cols = form.columns(len(EXAMPLES))
for col, (label, data) in zip(cols, EXAMPLES.items()):
    col.button(label, use_container_width=True, on_click=fill_example, args=(data,))

region = form.text_input("사는 곳 (시·군까지)", key="region", placeholder="예: 경남 통영시")
job = form.text_input("하는 일", key="job", placeholder="예: 피조개 양식업, 카페 운영, 제조업 퇴직")
col1, col2 = form.columns(2)
age = col1.number_input("나이", min_value=19, max_value=100, key="age")
years = col2.number_input("그 일을 한 지 (년)", min_value=0, max_value=60, key="years")
memo = form.text_area("더 알려 주고 싶은 사정 (선택)", key="memo", placeholder="예: 귀농 준비 중, 장비 교체 필요, 재취업 희망")

if form.button("지원사업 찾기", type="primary", use_container_width=True):
    if not region or not job:
        st.warning("사는 곳과 하는 일을 적어 주세요.")
        st.stop()
    profile = f"{region}, {job} {years}년차, {age}세" + (f", {memo}" if memo else "")
    st.session_state.profile = profile
    st.session_state.draft = None
    st.session_state.plan = None
    with st.status("공고를 찾고 있어요...", expanded=True) as status:
        queries = make_queries(profile, f"{region} {job}")
        # AI 검색어가 너무 길거나 좁을 때를 대비해 단순한 검색어도 항상 함께
        for q in (f"{region} {job} 지원사업 {TODAY.year}", f"{job} 소상공인 지원사업 공고"):
            if q not in queries:
                queries.append(q)
        st.write(f"① AI가 검색어 {len(queries)}개를 만들었어요")
        st.caption(" / ".join(queries))
        seen, results = set(), []
        for q in queries:
            try:
                for r in liner_search(q):
                    if r.get("url") and r["url"] not in seen:
                        seen.add(r["url"])
                        results.append(r)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 402:
                    status.update(label="Liner 크레딧이 부족해요", state="error")
                    st.write("잔여 크레딧이 $0이라 검색할 수 없어요. 크레딧이 들어오면 다시 눌러 주세요.")
                    st.stop()
                st.write(f"'{q}' 검색 실패: {e}")
            except Exception as e:
                st.write(f"'{q}' 검색 실패: {e}")
        raw = len(results)
        results = [r for r in results if source_rank(r.get("url", "")) < 9]  # SNS·영상 제외
        status.update(label="공고 원문을 읽고 있어요...")
        st.write(f"② Liner Search로 문서 {raw}개를 찾았어요 (SNS·영상 {raw - len(results)}개 제외)")
        if not results:
            st.write("범위를 넓혀서 한 번 더 찾아볼게요...")
            for q in (f"{job} 지원사업", f"{region} 소상공인 지원사업"):
                try:
                    for r in liner_search(q, recent=False):
                        if r.get("url") and r["url"] not in seen and source_rank(r["url"]) < 9:
                            seen.add(r["url"])
                            results.append(r)
                except Exception as e:
                    st.write(f"'{q}' 검색 실패: {e}")
        if not results:
            status.update(label="찾은 공고가 없어요. 이 상자를 눌러 자세한 내용을 확인해 주세요.", state="error")
            st.stop()
        results.sort(key=lambda r: source_rank(r.get("url", "")))  # 공식 사이트 먼저, 블로그는 뒤로
        results = results[:24]
        n_read = read_pages(results)
        st.write(f"③ 공식 사이트 우선으로 {len(results)}개를 골라, 공고 원문 {n_read}개를 읽었어요")
        status.update(label="자격과 마감일을 확인하고 있어요...")
        try:
            items = judge(profile, results)
        except Exception as e:
            status.update(label="정리하다 문제가 생겼어요. 다시 눌러 주세요.", state="error")
            st.write(str(e))
            st.stop()
        st.session_state.items = sort_items(items)
        st.write(f"④ 자격과 마감일을 확인해 지원사업 {len(items)}개로 정리했어요")
        status.update(label=f"지원사업 {len(items)}개를 찾았어요", state="complete", expanded=False)

items = st.session_state.get("items")
badge = {"가능": "ok", "확인 필요": "check", "해당 없음": "no"}


def ordered_items(items):
    return [it for it in items if not is_past(it)] + [it for it in items if is_past(it)]


def render_extras(it, i):
    """카드 바로 아래: 준비 서류 체크리스트와 달력 저장 버튼"""
    docs = [d for d in (it.get("documents") or []) if isinstance(d, str) and d.strip()]
    uid = f"{i}_{abs(hash(it.get('name', '')))}"
    left, right = st.columns([3, 2])
    with left.expander(f"📋 준비 서류 {len(docs)}개" if docs else "📋 준비 서류"):
        if docs:
            done = sum(st.checkbox(d, key=f"doc_{uid}_{j}") for j, d in enumerate(docs))
            st.progress(done / len(docs), text=f"{done}/{len(docs)} 준비 완료")
        else:
            st.write("공고 원문에서 서류 목록을 찾지 못했어요. 출처 링크에서 '제출 서류'를 확인해 주세요.")
    ics, _ = make_ics([it])
    if ics:
        label = "📅 마감일 달력에 넣기" if not is_past(it) else "📅 재공고 알림 넣기"
        right.download_button(label, ics.encode("utf-8"), file_name=f"지원사업_{i + 1}.ics",
                              mime="text/calendar", key=f"ics_{uid}", use_container_width=True)


def render_card(it):
    verdict = it.get("verdict", "확인 필요")
    e = lambda k: escape(str(it.get(k) or ""))
    d = days_left(it.get("deadline") or "")
    if is_past(it):
        dday = "<div class='dday past'><b>지난</b><span>공고</span></div>"
    elif d is None:
        label = "모집 예정" if it.get("status") == "모집 예정" else "마감일 확인"
        dday = f"<div class='dday'><b>?</b><span>{label}</span></div>"
    else:
        cls = "dday urgent" if d <= 7 else "dday"
        dday = f"<div class='{cls}'><b>D-{d}</b><span>{escape(it['deadline'])}</span></div>"
    url = it.get("url", "")
    if not url.startswith(("http://", "https://")):
        url = ""
    official = " <span class='official'>공식</span>" if url and is_official(url) else ""
    src = (f"<p class='src'>출처: <a href='{escape(url)}' target='_blank' rel='noopener'>"
           f"{escape(it.get('host') or url)}</a>{official}</p>") if url else ""
    nxt = f"<p class='next'>📅 {e('next_expected')}</p>" if is_past(it) and it.get("next_expected") else ""
    contact = ""
    if it.get("contact"):
        ph = phone_of(it["contact"])
        call = (f" <a class='call' href='tel:{ph[1]}'>📞 전화 걸기</a>") if ph else ""
        contact = f"<p><b>문의처:</b> {e('contact')}{call}</p>"
    st.markdown(
        f"""<div class='card'>{dday}<div class='body'>
<span class='badge {badge.get(verdict, "check")}'>{escape(verdict)}</span>
<h3>{e('name')}</h3>
{nxt}
<p>{e('summary')}</p>
<p><b>받을 수 있는 사람:</b> {e('eligibility')}</p>
<p><b>판단 이유:</b> {e('reason')}</p>
<p><b>주관 기관:</b> {e('agency')}</p>
{contact}
{src}</div></div>""",
        unsafe_allow_html=True,
    )


if items:
    show_all = st.session_state.get("show_all", False)
    visible = [it for it in items if show_all or it.get("verdict") != "해당 없음"]
    open_items = [it for it in visible if not is_past(it)]
    past_items = [it for it in visible if is_past(it)]

    step(2, "받을 수 있는 지원사업")
    n_ok = sum(1 for it in open_items if it.get("verdict") == "가능")
    st.markdown(f"<div class='tally'><div class='t-ok'><b>{n_ok}</b><span>지금 신청 가능</span></div>"
                f"<div class='t-check'><b>{len(open_items) - n_ok}</b><span>자격 확인 필요</span></div>"
                f"<div class='t-past'><b>{len(past_items)}</b><span>지난 공고</span></div></div>",
                unsafe_allow_html=True)
    st.checkbox("자격이 맞지 않는 사업('해당 없음')도 보기", key="show_all")
    st.subheader(f"지금 신청할 수 있는 사업 ({len(open_items)})")
    if not open_items:
        st.write("지금 모집 중인 공고는 찾지 못했어요. 아래 지난 공고를 보고 다음 모집을 미리 준비해 보세요.")
    for i, it in enumerate(open_items):
        with st.container(border=True):
            render_card(it)
            render_extras(it, i)

    if past_items:
        st.subheader(f"지난 공고: 다시 나올 때 미리 준비하세요 ({len(past_items)})")
        st.caption("이런 지원사업은 해마다 비슷한 시기에 다시 공고되는 경우가 많아요.")
        for i, it in enumerate(past_items, start=len(open_items)):
            with st.container(border=True):
                render_card(it)
                render_extras(it, i)
    st.caption("최종 자격과 마감일은 반드시 공고 원문에서 확인하세요.")

    all_ics, n_ev = make_ics(open_items + past_items)
    if all_ics:
        st.download_button(f"📅 일정 {n_ev}개 한꺼번에 달력에 넣기", all_ics.encode("utf-8"),
                           file_name="지원사업_일정.ics", mime="text/calendar", key="ics_all")
        st.caption("내려받은 파일을 열면 휴대폰·PC 달력에 들어가요. 마감 3일 전에 알림이 와요.")

    step(3, "이번 주부터 할 일")
    st.write("신청할 사업을 고르면, 마감일과 서류를 보고 날짜별 할 일을 짜 드려요.")
    candidates = [it for it in ordered_items(items) if it.get("verdict") != "해당 없음"]
    cand_names = [it.get("name", "") for it in candidates]
    default = [it.get("name", "") for it in candidates if not is_past(it)][:3] or cand_names[:1]
    picked = st.multiselect("신청할 사업 (여러 개 고를 수 있어요)", cand_names, default=default)
    if st.button("할 일 목록 만들기", type="primary", disabled=not picked):
        chosen = [it for it in candidates if it.get("name") in picked]
        with st.spinner("마감일과 서류를 보고 할 일을 짜고 있어요..."):
            try:
                st.session_state.plan = make_plan(st.session_state.profile, chosen)
            except Exception as err:
                st.session_state.plan = None
                st.error(f"할 일 목록을 만들다 문제가 생겼어요. 다시 눌러 주세요. ({err})")
    plan = st.session_state.get("plan")
    if plan:
        groups = [("이번 주", 0, 6), ("다음 주", 7, 13), ("그 뒤", 14, 10_000)]
        done_n = 0
        with st.container(border=True):
            for title, lo, hi in groups:
                rows = [t for t in plan if lo <= (dt.date.fromisoformat(t["date"]) - TODAY).days <= hi]
                if not rows:
                    continue
                a = TODAY + dt.timedelta(days=lo)
                rng = f" ({a.month}/{a.day}~{(a + dt.timedelta(days=6)).month}/{(a + dt.timedelta(days=6)).day})" if hi < 10_000 else ""
                st.markdown(f"**{title}{rng}**")
                for j, t in enumerate(rows):
                    d = dt.date.fromisoformat(t["date"])
                    label = f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]})  [{t.get('kind') or '할 일'}] {t['task']}"
                    # 같은 날 같은 문장이 여러 사업에 나와도 겹치지 않게: 묶음·순번·사업명까지 key에 넣음
                    key = f"task_{lo}_{j}_{t['date']}_{abs(hash((t.get('program') or '', t['task'])))}"
                    done_n += st.checkbox(label, key=key,
                                          help=f"사업: {t.get('program') or ''}")
            st.progress(done_n / len(plan), text=f"{done_n}/{len(plan)} 완료")
        st.download_button(f"📅 할 일 {len(plan)}개 달력에 넣기", tasks_ics(plan).encode("utf-8"),
                           file_name="지원사업_할일.ics", mime="text/calendar", key="ics_tasks")

    step(4, "신청서 초안 만들기")
    names = [it.get("name", "") for it in ordered_items(items) if it.get("verdict") != "해당 없음"]
    if names:
        pick = st.selectbox("어떤 사업의 신청서를 쓸까요?", names)
        if st.button("신청서 초안 만들기", type="primary"):
            chosen = next(it for it in items if it.get("name") == pick)
            with st.spinner("초안을 쓰고 있어요..."):
                st.session_state.draft = draft_application(st.session_state.profile, chosen)
        if st.session_state.get("draft"):
            with st.container(border=True):
                st.markdown(st.session_state.draft)
            st.download_button("초안 내려받기 (.txt)", st.session_state.draft, file_name="신청서_초안.txt")


st.divider()
st.markdown("<p class='poweredby'>공고 검색은 <b>Liner Search</b>, 검색어 만들기·자격 판단·쉬운 말 요약·신청서 초안은 "
            "<b>Liner Model</b>이 맡아요. 결과는 참고용이에요. 최종 자격과 마감일은 공고 원문에서 확인하세요.</p>",
            unsafe_allow_html=True)
with st.expander("저장된 검색 결과 지우기"):
    st.write("같은 조건으로 다시 찾으면 크레딧을 아끼려고 저장해 둔 결과를 보여 드려요. "
             "완전히 새로 찾고 싶을 때만 아래 버튼을 누르세요. (이후 검색엔 크레딧이 다시 쓰여요)")
    if st.button("저장된 결과 지우기"):
        st.cache_data.clear()
        st.success("지웠어요. 이제 다시 찾으면 새로 검색해요.")
