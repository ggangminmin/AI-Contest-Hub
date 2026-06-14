---
description: contests.json 자동 갱신 — 만료 항목 제거 + 신규 AI 공모전 검색·검증·추가
allowed-tools: Read, Edit, Write, Bash, WebSearch, WebFetch
---

# /update-contests [category]

이 프로젝트의 `contests.json`을 최신화한다. 작업 순서를 **반드시 그대로** 따라라.

## 인자
`$ARGUMENTS`가 있으면 그 카테고리만 신규 검색 대상으로 좁힌다. 값:
- `app` — 기획·앱·아이디어 공모전만
- `video` — AI 영상 공모전만
- `image` — AI 이미지 공모전만
- `audio` — AI 음악 공모전만
- (없음 또는 `all`) — 전 카테고리

카테고리가 지정되면 **2단계의 다른 카테고리 검색은 건너뛴다.** 만료 처리(1단계)는 항상 수행.

## 컨텍스트
- 프로젝트 루트: 현재 cwd
- 데이터 파일: `contests.json` (스키마는 파일 상단 `schema` 필드 참조)
- 카테고리: `image | video | audio | app`
- 지역: `domestic | overseas`
- 오늘 날짜는 시스템 환경의 currentDate에서 확인. 절대 추측 금지.

## 1단계 — 만료 항목 보존 (삭제 금지)
1. `contests.json` 읽기.
2. **만료 항목은 절대 삭제하지 않는다.** deadline이 오늘 이전인 항목은 그대로 둔다 — UI가 자동으로 '마감 공고' 탭으로 분류한다.
3. 기존 항목의 `resultDate`, `submitted` 필드는 그대로 보존한다. 이번에 결과 발표일이 새로 확인되면 `resultDate`만 갱신 가능.
4. (참고) 오늘 막 마감된 항목 title을 메모해 보고에 활용.

## 2단계 — 신규 공고 검색
다음 카테고리별로 WebSearch를 병렬 호출한다. 검색어에 **오늘 연도**를 반드시 포함.

- `cat=app`: "{YYYY} AI 활용 공모전 진행중 아이디어 기획 서비스 개발" + "{YYYY} 공공데이터 AI 활용 경진대회" + "{YYYY} 광역지자체 공공데이터 AI 창업경진대회 경기 서울 부산 인천 대구 광주 대전" + "{YYYY} 경기기업비서 OR 서울산업진흥원 OR 테크노파크 AI 공모전"
- `cat=video`: "{YYYY} AI 영상 공모전 진행중 마감" + "{YYYY} 생성형 AI 숏폼 공모전" + "{YYYY} 시청 군청 도청 AI 영상 공모전"
- `cat=image`: "{YYYY} AI 이미지 공모전 진행중 마감" + "{YYYY} AI 디지털 아트 공모전"
- `cat=audio`: "{YYYY} AI 음악 공모전 진행중 마감"
- `region=overseas`: "{YYYY} AI film festival open submission" + "{YYYY} AI art competition open call"

**참고:** 지자체(광역시·도, 시·군·구) 포털은 도메인 권위가 낮고 보도자료 노출이 약해서 일반 검색에 잘 안 걸린다. 지자체 키워드와 주요 진흥기관명을 검색어에 함께 넣어야 누락을 줄일 수 있다.

## 2-B단계 — 고정 소스 크롤링 (매 실행 포함)

WebSearch만으로는 두 종류를 구조적으로 놓친다: ① JS로 목록을 그리는 **SPA 공모전 플랫폼**, ② "일반 공모전인데 **AI 허용**"이라 제목·목록엔 AI 표시가 없고 브리핑 본문에만 적힌 건. 아래 고정 소스는 매번 전용 루틴으로 훑는다.

### loud.kr (라우드소싱) — 전용 스캐너 사용
loud.kr은 SPA(백엔드 `api.stunning.kr`)라 WebFetch로는 목록이 안 보인다. **로그인 불필요.** 전용 스크립트로 처리한다:

```bash
python scripts/loud_scan.py --today {YYYY-MM-DD}    # currentDate 사용, 추측 금지
# 사용자가 특정 링크를 줬으면: python scripts/loud_scan.py --today {today} --ids 199856,204537
```

동작: Jina Reader로 `/contest?page=N`을 다중 패스 열거(추천순이 요청마다 섞여 단일 패스는 부분만 잡힘 → union) → 각 ID를 단일 상세 API(`api.stunning.kr/api/v1/dantats/contest/{id}`, 헤더 `Origin/Referer: loud.kr`)로 정밀 판별 → `verdict`로 분류해 JSON 출력.

- `verdict=ai_allowed`: **AI 생성 결과물이 허용/환영/필수** → 4단계 검증 후보. **단, 스니펫을 반드시 눈으로 확인**한다. 분류기는 오탐이 난다(예: "AI 이미지 같은 폰트 피하라"는 디자인 제약, "AI 안전 영상"=참고자료를 양성으로 잡은 사례 있음).
- `verdict=ai_restricted`: **AI는 보조만/AI 전용작 불인정/최종물 AI 금지** → 제외. 단 스니펫은 보고에 남긴다.
- 출력에 기존 보드와 같은 행사가 **다른 마감일**로 나오면(예: 보드엔 5/29인데 포털엔 8/30) 포털 쪽이 최신 작품접수 마감인 경우가 많다 → 4단계로 교차검증 후 기존 항목 deadline 정정.

> 사용자가 앞으로 추가하는 다른 SPA 소스도 같은 패턴으로: ① 목록은 Jina Reader 렌더링, ② 상세/마감/AI허용은 그 사이트의 내부 JSON API(있으면)로 정밀 판별, ③ 본문에서 'AI 허용/생성형 AI'를 확인. 사이트별 엔드포인트는 발견하면 이 문서에 추가한다.

## 3단계 — 후보 필터링
검색 결과(2단계) + 고정 소스(2-B단계)에서 다음을 만족하는 항목만 후보로 남긴다:
- 마감일이 **오늘 이후**여야 함 (검색 스니펫에 마감일이 보이면 즉시 판단)
- `contests.json`의 기존 items에 동일/유사 title이 없어야 함 (중복 제외)
- **AI 생성/활용 결과물이 허용되는** 공모전이어야 함. ⚠️ 제목에 'AI'가 없어도 **브리핑·요강 본문에 "AI 활용 가능/생성형 AI 허용"이 있으면 포함**한다(특히 숏폼·영상·이미지·콘텐츠). 반대로 "AI 보조만 가능 / AI 전용작 불인정 / 최종물 AI 금지"면 **제외**. (audio는 기존대로 AI 생성 음악 허용분만)

## 4단계 — 공식 페이지 검증 (필수)
후보 각각에 대해 **WebFetch로 공식 URL을 직접 호출**해서 다음을 확인:
1. 페이지가 정상 응답하는가 (200)
2. 검색 스니펫의 마감일이 공식 페이지의 마감일과 일치하는가
3. 공모전 정식 명칭과 주최 기관 확인

**검증 실패한 후보는 절대 추가하지 말 것.** 마감일을 추측하거나 검색 스니펫만 믿고 추가하지 마라. 검증 통과한 항목만 다음 단계로.

## 5단계 — items 배열에 추가
검증 통과한 항목을 다음 스키마로 만든다:
```json
{
  "id": "{region-prefix}-{cat}-{slug}-{YYYY}",
  "region": "domestic|overseas",
  "cat": "image|video|audio|app",
  "title": "공식 정식 명칭",
  "desc": "1줄 요약 (~80자, AI 활용 부분 명시)",
  "deadline": "YYYY-MM-DD",
  "resultDate": "결과 발표일 (확인되면 YYYY-MM-DD, 모르면 '미정')",
  "organizer": "주최 기관",
  "addedAt": "오늘 날짜 YYYY-MM-DD",
  "submitted": false,
  "official": "검증된 공식 URL"
}
```
- `audio` 카테고리(AI 음악·노래)는 **AI 생성 음악이 허용되는** 공모전만 추가한다. AI 불가 음악 공모전은 제외.
id prefix 규칙:
- `kr-` (domestic) 또는 `intl-` (overseas)
- cat 약자: `app`, `vid`, `img`, `aud`

## 6단계 — JSON 저장
1. `generated_at` 필드를 오늘 날짜로 업데이트.
2. items를 deadline 오름차순으로 정렬.
3. Write로 `contests.json` 저장 (UTF-8, 들여쓰기 2칸).

## 7단계 — 결과 보고
사용자에게 짧게 보고:
```
## /update-contests 결과
- 제거(만료): {N}건
  - {title 목록}
- 추가(신규 검증 통과): {M}건
  - {title} (마감 {deadline}) — {organizer}
- 추가 후보였으나 검증 실패: {K}건
  - {title} — {실패 사유}
- 최종 items 수: {total}건
```

## 절대 지킬 것
- 검증되지 않은 마감일/주최/URL을 **절대 추가하지 마라.** 의심되면 빼라.
- 기존 items의 마감일을 임의로 수정하지 마라. **만료 항목 삭제 금지** (마감 공고로 보존).
- 기존 items의 `submitted` 값은 절대 건드리지 마라 (사용자 제출 표시).
- 한 번에 너무 많이 검색하지 마라 (5~8개 검색 → 5~10개 후보 → 검증 → 통상 2~5개 추가가 정상 사이클).
- 새 카테고리 추가가 필요해 보이면 user에게 묻고 멈춰라. 임의로 cat 값을 만들지 마라.
