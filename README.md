# 지원사업 찾기 에이전트

지역, 하는 일, 나이를 입력하면 받을 수 있는 정부·지자체 지원사업을 찾아 마감일 순서로 보여 주고, 신청서 초안까지 써 주는 AI 에이전트입니다.

- 공고 검색: **Liner Search API**
- 검색어 만들기, 자격 판단, 쉬운 말 요약, 신청서 초안: **Liner Model API** (`liner-claude-router`)

## 윈도우에서 처음 실행하기

### 1. 파이썬 설치 (한 번만)
1. https://www.python.org/downloads/ 에서 노란 **Download Python** 버튼을 눌러 설치 파일을 받습니다.
2. 설치 첫 화면 맨 아래 **Add python.exe to PATH** 칸에 꼭 체크한 뒤 **Install Now**를 누릅니다.

### 2. 프로그램 폴더 준비
1. `jiwon-agent.zip`을 받아 바탕화면에 압축을 풉니다.
2. `jiwon-agent` 폴더를 열고, 위쪽 주소창을 클릭해 `cmd` 라고 쓰고 엔터를 누르면 검은 창(명령 프롬프트)이 그 폴더에서 열립니다.

### 3. 필요한 도구 설치 (한 번만)
검은 창에 아래를 붙여 넣고 엔터:
```
pip install -r requirements.txt
```

### 4. API 키 넣기
1. `.streamlit` 폴더 안의 `secrets.toml.example` 파일을 복사해서, 이름을 `secrets.toml` 로 바꿉니다.
   (파일 확장자가 안 보이면 탐색기 위쪽 **보기 → 표시 → 파일 확장명**을 켜세요.)
2. 메모장으로 열어 `여기에-내-라이너-API-키` 자리에 platform.liner.com 에서 받은 키를 붙여 넣고 저장합니다.

### 5. 실행
```
streamlit run app.py
```
잠시 후 인터넷 창이 자동으로 열립니다. 끝낼 때는 검은 창에서 `Ctrl + C`.

## 꼭 지킬 것
- `secrets.toml`(API 키)은 GitHub에 올리지 마세요. `.gitignore`에 막아 두었습니다.
- 시연과 신청서 초안에는 실제 개인정보 대신 가상의 인물 정보를 쓰세요. (대회 규정 제5조)
- 에이전트의 자격 판단은 참고용입니다. 화면에 원문 링크를 함께 보여 줍니다.
