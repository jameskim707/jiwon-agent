# 지원사업 찾기 에이전트 (라이너 해커톤 .EXE-THON 출품작 2차 버전)
# 흐름: 상황 입력 → Liner Model이 검색어 생성 → Liner Search로 공고 검색 (공식 사이트 우선)
#      → 공고 원문 페이지를 직접 읽어 마감일·자격 발췌
#      → Liner Model이 자격 판단·쉬운 말 요약 → 모집 중 / 지난 공고 분류, 마감일순 정렬
#      → 신청서 초안 작성

import os
import json
import re
import datetime as dt
import time
import threading
import hashlib
from html import escape
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st

# ---------- 설정 ----------
MODEL = "liner-claude-router"
SEARCH_URL = "https://platform.liner.com/api/v1/tools/search/web"
CHAT_URL = "https://platform.liner.com/api/v1/chat/completions"


def get_api_key():
    try:
        return st.secrets["LINER_API_KEY"]
    except Exception:
        return os.environ.get("LINER_API_KEY", "")


API_KEY = get_api_key()
# 서버가 해외(UTC)에 있어도 한국 날짜로 계산 (자정~오전 9시에 D-day가 하루 어긋나는 것을 막음)
TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


# ---------- 크레딧 보호: 하루 호출 횟수 상한 ----------
# 링크를 아는 누구나 누를 수 있으므로, 하루에 쓸 수 있는 횟수를 정해 둡니다.
# 숫자를 바꾸려면 스트림릿 앱 설정의 비밀 설정(Secrets)에 DAILY_SEARCH_LIMIT = 50 처럼 적으세요.
def _setting(name, default):
    try:
        return int(st.secrets[name])
    except Exception:
        try:
            return int(os.environ.get(name, default))
        except Exception:
            return default


DAILY_SEARCH_LIMIT = _setting("DAILY_SEARCH_LIMIT", 30)   # '지원사업 찾기' 하루 횟수
DAILY_DRAFT_LIMIT = _setting("DAILY_DRAFT_LIMIT", 60)     # '신청서 초안' 하루 횟수


@st.cache_resource
def _usage():
    # 모든 접속자가 함께 쓰는 오늘의 사용 횟수 (앱이 다시 시작되면 0으로 돌아갑니다)
    return {"lock": threading.Lock(), "day": "", "search": 0, "draft": 0}


def _limit(kind):
    return DAILY_SEARCH_LIMIT if kind == "search" else DAILY_DRAFT_LIMIT


def use_quota(kind):
    """kind: 'search' 또는 'draft'. 한도 안이면 1 올리고 True, 넘으면 False."""
    u = _usage()
    with u["lock"]:
        if u["day"] != TODAY.isoformat():
            u["day"], u["search"], u["draft"] = TODAY.isoformat(), 0, 0
        if u[kind] >= _limit(kind):
            return False
        u[kind] += 1
        return True


def remaining(kind):
    u = _usage()
    with u["lock"]:
        if u["day"] != TODAY.isoformat():
            return _limit(kind)
        return max(0, _limit(kind) - u[kind])


def quota_text():
    return f"오늘 남은 시연 횟수: 검색 {remaining('search')}회 · 신청서 초안 {remaining('draft')}회"


LIMIT_MSG = "오늘 시연 한도에 도달했어요. 크레딧을 지키려고 하루 횟수를 제한하고 있어요. 내일 다시 시도해 주세요."

st.set_page_config(page_title="지원사업 찾기", page_icon="📮", layout="centered")

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
.stButton > button {
  font-size: 1.15rem !important; font-weight: 700; padding: 0.7rem 1.4rem;
  background: #0E5E6F; color: #FFFFFF; border: none; border-radius: 10px;
}
.stButton > button:hover { background: #0A4855; color: #FFFFFF; }
.stButton > button:focus-visible { outline: 3px solid #F2B705; outline-offset: 2px; }
.card {
  display: flex; gap: 1.1rem; align-items: flex-start;
  border: 2px solid #D5DEE5; border-radius: 12px; padding: 1rem 1.2rem; margin: 0.9rem 0;
}
.dday { min-width: 5.2rem; text-align: center; }
.dday b { display: block; font-size: 1.9rem; line-height: 1.1; color: #0E5E6F; }
.dday.urgent b { color: #B42318; }
.dday span { font-size: 0.8rem; color: #4B5563; }
.body h3 { margin: 0 0 0.3rem 0; font-size: 1.2rem; }
.badge { display: inline-block; font-size: 0.85rem; font-weight: 700; padding: 0.15rem 0.6rem; border-radius: 999px; margin-bottom: 0.4rem; }
.ok { background: #E3F4E8; color: #1F7A3A; }
.check { background: #FFF2D6; color: #8A5300; }
.no { background: #EEF0F3; color: #4B5563; }
.body p { margin: 0.25rem 0; line-height: 1.6; }
.src { font-size: 0.85rem; }
.dday.past b { color: #6B7280; font-size: 1.3rem; }
.official { display: inline-block; font-size: 0.75rem; font-weight: 700; color: #0E5E6F;
  border: 1.5px solid #0E5E6F; border-radius: 6px; padding: 0 0.35rem; margin-left: 0.35rem; }
.docs { margin: 0.1rem 0 0.5rem 1.2rem; padding: 0; line-height: 1.6; }
.next { background: #EEF6F8; border-radius: 8px; padding: 0.35rem 0.6rem; font-weight: 600; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------- Liner 호출 함수 ----------
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
    """모델 답변에서 JSON만 꺼내기 (```json 감싸기 등 제거)"""
    text = text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"(\[.*\]|\{.*\})", text, re.S)
    return json.loads(match.group(1) if match else text)


def liner_search(query, max_results=8, recent=True):
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
            "제출서류", "제출 서류", "구비서류", "구비 서류", "신청서류", "신청 서류", "첨부서류", "필요서류", "필요 서류"]


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

아래 검색 결과 중 실제 지원사업·보조금·보험·교육 공고로 보이는 것만 골라 정리하세요.
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
 "documents": ["'원문 발췌'에 실제로 적힌 필수 제출 서류 이름들. 짧게 (예: '사업자등록증 사본'). 원문에 없으면 빈 배열 []"]
}}

status: 오늘 날짜와 마감일을 비교해 정하세요. 마감일이 지났으면 "지난 공고".
documents는 '원문 발췌'에 글자로 적힌 서류만 쓰세요. 일반적으로 필요할 것 같은 서류를 추측해서 채우지 마세요. 첨부 파일 안에만 있어서 읽지 못한 서류는 적지 마세요.
verdict는 '자격'만 봅니다(마감 여부와 상관없이): 지역·업종·나이 조건이 분명히 맞으면 "가능", 정보가 부족하면 "확인 필요", 조건이 분명히 안 맞으면 "해당 없음".

검색 결과:
{listing}"""
    items = parse_json(llm(prompt, system=system, max_tokens=4500))
    for it in items:
        it["documents"] = clean_docs(it.get("documents"))
        idx = it.get("index")
        if isinstance(idx, int) and 0 <= idx < len(results):
            it["url"] = results[idx].get("url", "")
            it["host"] = results[idx].get("hostname", "")
    return items


def clean_docs(v):
    """모델이 준 서류 목록을 안전하게 정리: 문자열만, 중복 제거, 최대 10개, 각 50자"""
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        t = re.sub(r"\s+", " ", str(x)).strip()[:50]
        if t and t not in out:
            out.append(t)
    return out[:10]


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


def calendar_items(items):
    """달력에 넣을 사업: 아직 마감 전이고 마감일이 분명하며, 자격이 '해당 없음'이 아닌 것"""
    out = []
    for it in items:
        d = days_left(it.get("deadline") or "")
        if d is not None and d >= 0 and it.get("verdict") != "해당 없음":
            out.append(it)
    return out


def _ics_text(t):
    return str(t).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\n", "\\n")


def _ics_fold(line):
    """ICS는 한 줄이 75바이트를 넘으면 다음 줄을 공백으로 시작해 이어 쓴다"""
    out, cur, size = [], "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if size + b > (75 if not out else 74):
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += b
    out.append(cur)
    return "\r\n ".join(out)


def build_ics(items):
    """마감일을 종일 일정으로 담은 달력 파일(.ics). 마감 3일 전·하루 전·당일 오전 9시에 알림을 설정한다."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//jiwon-agent//지원사업 찾기//KO", "CALSCALE:GREGORIAN"]
    for it in items:
        due = dt.date.fromisoformat(it["deadline"])
        url = it.get("url", "") if str(it.get("url", "")).startswith(("http://", "https://")) else ""
        uid = hashlib.sha1(f"{it.get('name')}|{it['deadline']}|{url}".encode("utf-8")).hexdigest()[:24] + "@jiwon-agent"
        docs = ", ".join(it.get("documents") or []) or "공고 원문에서 확인"
        desc = (f"주관 기관: {it.get('agency') or '확인 필요'}\n준비할 서류: {docs}\n"
                f"최종 마감일과 서류는 반드시 공고 원문에서 확인하세요." + (f"\n공고: {url}" if url else ""))
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{(due + dt.timedelta(days=1)).strftime('%Y%m%d')}",
                  f"SUMMARY:{_ics_text('[마감] ' + str(it.get('name') or '지원사업'))}",
                  f"DESCRIPTION:{_ics_text(desc)}"]
        if url:
            lines.append(f"URL:{url}")
        for trig, label in (("-P2DT15H", "마감 3일 전"), ("-PT15H", "마감 하루 전"), ("PT9H", "오늘 마감")):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(label + ': ' + str(it.get('name') or ''))}",
                      f"TRIGGER:{trig}", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(l) for l in lines) + "\r\n"


def draft_application(profile, item):
    prompt = f"""아래 지원사업의 신청서 초안을 써 주세요.

신청자 상황: {profile}
사업 이름: {item.get('name')}
주관 기관: {item.get('agency')}
지원 내용: {item.get('summary')}
자격: {item.get('eligibility')}

규칙:
- 이름, 주민등록번호, 연락처, 주소, 사업자번호 같은 개인정보는 절대 채우지 말고 [이름], [연락처]처럼 빈칸으로 두세요.
- 실제 공고 양식을 모르므로 일반적인 항목(신청 동기, 현재 사업 현황, 지원금 사용 계획, 기대 효과)으로 구성하세요.
- 신청자가 고쳐 쓰기 쉽게 쉬운 말로, 각 항목 3~5문장.
- 맨 끝에 "제출 전 공고 원문의 서식과 필요 서류를 꼭 확인하세요."를 넣으세요."""
    return llm(prompt, max_tokens=2500)


# ---------- 화면 ----------
st.title("내가 받을 수 있는 지원사업 찾기")
st.write("지역, 하는 일, 나이를 적으면 받을 수 있는 지원사업을 찾아 마감일 순서로 보여 드려요.")

if not API_KEY:
    st.error("Liner API 키가 없어요. 설명서의 'API 키 넣기'를 따라 .streamlit/secrets.toml 파일을 만들어 주세요.")
    st.stop()

if "example" not in st.session_state:
    st.session_state.example = {}

# 시연용 예시 3가지 (모두 가상 인물입니다)
EXAMPLES = {
    "피조개": {"region": "경남 통영시", "job": "피조개 양식업", "age": 58, "years": 3,
            "memo": "가족과 함께 운영, 시설 노후로 장비 교체 필요"},
    "귀농": {"region": "경남 산청군", "job": "옷가게·카페 운영 후 귀농 준비", "age": 52, "years": 8,
           "memo": "옷가게와 카페를 정리하는 중, 귀농 준비 중, 농업 교육을 받고 싶음"},
    "재취업": {"region": "경북 구미시", "job": "제조업(기계 가공) 퇴직", "age": 57, "years": 20,
            "memo": "작년 퇴직, 기계 다룬 경력 20년, 재취업이나 기술 교육 희망"},
}
def apply_example(key):
    # 예시를 바꿀 때 앞에서 찾은 결과와 신청서 초안도 함께 지워서, 이전 예시 결과가 남아 보이지 않게 합니다
    st.session_state.example = EXAMPLES[key]
    st.session_state.items = None
    st.session_state.draft = None


ex_col1, ex_col2, ex_col3 = st.columns(3)
if ex_col1.button("예시로 채우기 (통영 피조개 양식)"):
    apply_example("피조개")
if ex_col2.button("예시: 귀농 준비"):
    apply_example("귀농")
if ex_col3.button("예시: 제조업 퇴직·재취업"):
    apply_example("재취업")
ex = st.session_state.example

region = st.text_input("사는 곳 (시·군까지)", value=ex.get("region", ""), placeholder="예: 경남 통영시")
job = st.text_input("하는 일", value=ex.get("job", ""), placeholder="예: 피조개 양식업, 카페 운영, 제조업 퇴직")
col1, col2 = st.columns(2)
age = col1.number_input("나이", min_value=19, max_value=100, value=int(ex.get("age", 55)))
years = col2.number_input("그 일을 한 지 (년)", min_value=0, max_value=60, value=int(ex.get("years", 3)))
memo = st.text_area("더 알려 주고 싶은 사정 (선택)", value=ex.get("memo", ""), placeholder="예: 귀농 준비 중, 장비 교체 필요, 재취업 희망")

quota_box = st.empty()  # 남은 횟수 표시 자리 (횟수를 센 뒤에 채워서 실제와 어긋나지 않게 함)
run_search = st.button("지원사업 찾기", type="primary")
if run_search and region and job and not use_quota("search"):
    st.warning(LIMIT_MSG)  # 한도에 걸려도 앞서 찾은 결과는 계속 보이게 둡니다
    run_search = False
quota_box.caption(quota_text())
if run_search:
    if not region or not job:
        st.warning("사는 곳과 하는 일을 적어 주세요.")
        st.stop()
    profile = f"{region}, {job} {years}년차, {age}세" + (f", {memo}" if memo else "")
    st.session_state.profile = profile
    st.session_state.draft = None
    with st.status("공고를 찾고 있어요...", expanded=True) as status:
        queries = make_queries(profile, f"{region} {job}")
        # AI 검색어가 너무 길거나 좁을 때를 대비해 단순한 검색어도 항상 함께
        for q in (f"{region} {job} 지원사업 {TODAY.year}", f"{job} 소상공인 지원사업 공고"):
            if q not in queries:
                queries.append(q)
        st.write("검색어: " + " / ".join(queries))
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
        st.write(f"검색 결과 {raw}개 (SNS·영상 {raw - len(results)}개 제외)")
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
        st.write(f"찾은 문서 {len(results)}개. 공고 원문을 읽고 있어요...")
        n_read = read_pages(results)
        st.write(f"원문 {n_read}개를 읽었어요. 자격과 마감일을 확인하고 있어요...")
        try:
            items = judge(profile, results)
        except Exception as e:
            status.update(label="정리하다 문제가 생겼어요. 다시 눌러 주세요.", state="error")
            st.write(str(e))
            st.stop()
        st.session_state.items = sort_items(items)
        status.update(label=f"지원사업 {len(items)}개를 찾았어요", state="complete", expanded=False)

items = st.session_state.get("items")
badge = {"가능": "ok", "확인 필요": "check", "해당 없음": "no"}


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
    docs = it.get("documents") or []
    if docs:
        docs_html = ("<p><b>준비할 서류</b> (공고 원문 기준)</p><ul class='docs'>"
                     + "".join(f"<li>{escape(x)}</li>" for x in docs) + "</ul>")
    else:
        docs_html = "<p><b>준비할 서류:</b> 원문에서 찾지 못했어요. 공고 원문과 첨부 파일에서 꼭 확인해 주세요.</p>"
    st.markdown(
        f"""<div class='card'>{dday}<div class='body'>
<span class='badge {badge.get(verdict, "check")}'>{escape(verdict)}</span>
<h3>{e('name')}</h3>
{nxt}
<p>{e('summary')}</p>
<p><b>받을 수 있는 사람:</b> {e('eligibility')}</p>
<p><b>판단 이유:</b> {e('reason')}</p>
<p><b>주관 기관:</b> {e('agency')}</p>
{docs_html}
{src}</div></div>""",
        unsafe_allow_html=True,
    )


if items:
    show_all = st.checkbox("'해당 없음'도 보기", value=False)
    visible = [it for it in items if show_all or it.get("verdict") != "해당 없음"]
    open_items = [it for it in visible if not is_past(it)]
    past_items = [it for it in visible if is_past(it)]

    st.subheader(f"지금 신청할 수 있는 사업 ({len(open_items)})")
    cal_items = calendar_items(open_items)
    if cal_items:
        st.download_button(f"마감일을 달력에 넣기 (.ics) · {len(cal_items)}개", build_ics(cal_items),
                           file_name="지원사업_마감일.ics", mime="text/calendar")
        st.caption("내려받은 파일을 열면 달력에 마감일이 들어가고, 마감 3일 전·하루 전·당일 오전 9시에 알림이 울리도록 해 두었어요. 알림이 실제로 울리는지는 쓰는 달력 앱에 따라 달라요.")
    if not open_items:
        st.write("지금 모집 중인 공고는 찾지 못했어요. 아래 지난 공고를 보고 다음 모집을 미리 준비해 보세요.")
    for it in open_items:
        render_card(it)

    if past_items:
        st.subheader(f"지난 공고 · 다시 나올 때 미리 준비하세요 ({len(past_items)})")
        st.caption("이런 지원사업은 해마다 비슷한 시기에 다시 공고되는 경우가 많아요.")
        for it in past_items:
            render_card(it)
    st.caption("최종 자격과 마감일은 반드시 공고 원문에서 확인하세요.")

    st.subheader("신청서 초안 만들기")
    names = [it.get("name", "") for it in items if it.get("verdict") != "해당 없음"]
    if names:
        pick = st.selectbox("어떤 사업의 신청서를 쓸까요?", names)
        if st.button("신청서 초안 만들기"):
            chosen = next(it for it in items if it.get("name") == pick)
            ok_draft = use_quota("draft")
            quota_box.caption(quota_text())  # 방금 쓴 횟수를 바로 반영
            if not ok_draft:
                st.warning(LIMIT_MSG)
            else:
                with st.spinner("초안을 쓰고 있어요..."):
                    body_text = draft_application(st.session_state.profile, chosen)
                    docs = chosen.get("documents") or []
                    head = ("## 준비할 서류 (공고 원문 기준)\n" + "\n".join(f"- ☐ {x}" for x in docs) + "\n\n") if docs else \
                           "## 준비할 서류\n- 원문에서 찾지 못했어요. 공고 원문과 첨부 파일에서 꼭 확인해 주세요.\n\n"
                    st.session_state.draft = head + body_text
        if st.session_state.get("draft"):
            st.markdown(st.session_state.draft)
            st.download_button("초안 내려받기 (.txt)", st.session_state.draft, file_name="신청서_초안.txt")
