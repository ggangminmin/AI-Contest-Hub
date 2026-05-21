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

카테고리가 지정되면 **2단계의 다른 카테고리 검색은 건너뛴다.** 만료 제거(1단계)는 항상 수행.

## 컨텍스트
- 프로젝트 루트: 현재 cwd
- 데이터 파일: `contests.json` (스키마는 파일 상단 `schema` 필드 참조)
- 카테고리: `image | video | audio | app`
- 지역: `domestic | overseas`
- 오늘 날짜는 시스템 환경의 currentDate에서 확인. 절대 추측 금지.

## 1단계 — 만료 항목 제거
1. `contests.json` 읽기.
2. 오늘 날짜와 `deadline` 비교. **오늘 이전 마감인 항목**(deadline < today)을 items 배열에서 제거.
3. 제거한 항목들의 title을 메모.

## 2단계 — 신규 공고 검색
다음 카테고리별로 WebSearch를 병렬 호출한다. 검색어에 **오늘 연도**를 반드시 포함.

- `cat=app`: "{YYYY} AI 활용 공모전 진행중 아이디어 기획 서비스 개발" + "{YYYY} 공공데이터 AI 활용 경진대회"
- `cat=video`: "{YYYY} AI 영상 공모전 진행중 마감" + "{YYYY} 생성형 AI 숏폼 공모전"
- `cat=image`: "{YYYY} AI 이미지 공모전 진행중 마감" + "{YYYY} AI 디지털 아트 공모전"
- `cat=audio`: "{YYYY} AI 음악 공모전 진행중 마감"
- `region=overseas`: "{YYYY} AI film festival open submission" + "{YYYY} AI art competition open call"

## 3단계 — 후보 필터링
검색 결과에서 다음을 만족하는 항목만 후보로 남긴다:
- 마감일이 **오늘 이후**여야 함 (검색 스니펫에 마감일이 보이면 즉시 판단)
- `contests.json`의 기존 items에 동일/유사 title이 없어야 함 (중복 제외)
- AI 활용/생성형 AI 활용이 명시되어야 함

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
  "organizer": "주최 기관",
  "addedAt": "오늘 날짜 YYYY-MM-DD",
  "official": "검증된 공식 URL"
}
```
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
- 기존 items의 마감일을 임의로 수정하지 마라 (만료 제거만 허용).
- 한 번에 너무 많이 검색하지 마라 (5~8개 검색 → 5~10개 후보 → 검증 → 통상 2~5개 추가가 정상 사이클).
- 새 카테고리 추가가 필요해 보이면 user에게 묻고 멈춰라. 임의로 cat 값을 만들지 마라.
