# 자동 최신화 가이드

이 문서는 `contests.json`을 사람 손 없이 갱신하는 3가지 방법을 정리한다.
공통 전제: 갱신 로직은 모두 `/update-contests` 슬래시 커맨드(.claude/commands/update-contests.md)에 들어 있다.

## 동작 원리 (이미 구현된 것)

- `index.html`은 페이지 로드 시 `contests.json`을 fetch.
- `isOngoing()` 함수가 `deadline < 오늘`인 항목을 **화면에서 자동으로 숨김**.
  → contests.json에 만료 항목이 남아 있어도 사용자에게는 안 보임.
  → 즉 "오늘 마감 지난 항목은 자동으로 사라짐"은 코드 수준에서 이미 보장됨.
- 따라서 정기 갱신의 목적은 두 가지:
  1. 만료 항목을 JSON에서 **물리적으로 제거** (파일 비대화 방지)
  2. **신규 공고를 검색·검증해서 추가**

## 방법 1 — 수동 (가장 간단)

Claude Code 열고 입력:

```
/update-contests
```

끝. Claude가 만료 제거 → 신규 검색 → 공식 페이지 검증 → JSON 업데이트 → 결과 보고까지 한 번에 처리.

권장 주기: 주 1회.

## 방법 2 — Claude Code `/loop` (켜놓은 동안 자동)

Claude Code 켜둔 채로 입력:

```
/loop 24h /update-contests
```

24시간마다 자동 실행. **Claude Code를 닫으면 멈춤.** 데스크톱을 항상 켜두는 환경에 적합.

다른 간격:
- `/loop 12h /update-contests` — 하루 2회
- `/loop 7d /update-contests` — 주 1회

## 방법 3 — Windows 작업 스케줄러 (진짜 자동화)

Claude Code를 헤드리스 모드(`-p`)로 매일 자동 실행. PC가 켜져 있기만 하면 됨.

### 등록

PowerShell 관리자 권한으로:

```powershell
$action = New-ScheduledTaskAction -Execute "claude" -Argument "-p `"/update-contests`"" -WorkingDirectory "C:\Users\user\Desktop\민석_작업\ai 공모전 모음 poc"
$trigger = New-ScheduledTaskTrigger -Daily -At 9am
Register-ScheduledTask -TaskName "ContestsAutoUpdate" -Action $action -Trigger $trigger -Description "AI 공모전 보드 일일 갱신"
```

### 확인 / 수동 실행 / 삭제

```powershell
Get-ScheduledTask -TaskName "ContestsAutoUpdate"
Start-ScheduledTask -TaskName "ContestsAutoUpdate"
Unregister-ScheduledTask -TaskName "ContestsAutoUpdate" -Confirm:$false
```

### 주의
- `claude` 실행 파일이 PATH에 있어야 함. 없으면 `C:\Users\user\AppData\Local\...\claude.exe` 절대 경로로.
- 헤드리스 실행은 권한 프롬프트 없이 진행하려면 `.claude/settings.local.json`에 WebSearch/WebFetch/Write가 allow되어 있어야 함.
- 로그 확인: 작업 스케줄러 GUI에서 "ContestsAutoUpdate" 우클릭 → "마지막 실행 결과".

## 방법 4 — 클라우드 routine (PC 안 켜져 있어도 됨, 셋업 무거움)

`/schedule` 명령으로 Anthropic 클라우드에서 원격 에이전트를 cron 실행. 단점: 클라우드 에이전트는 로컬 `C:\...` 파일에 접근 못 함. 따라서:

1. 프로젝트를 GitHub repo로 만든다 (`git init` → `gh repo create`).
2. `/update-contests` 커맨드를 수정해서 마지막 단계에 `git add contests.json && git commit -m "auto: daily refresh" && git push` 추가.
3. `index.html`을 GitHub Pages로 호스팅하고 `contests.json`을 raw URL로 fetch.
4. `/schedule` 등록:
   ```
   /schedule create "0 9 * * *" "/update-contests"
   ```
   매일 오전 9시 KST 실행 (cron은 UTC라 `0 0 * * *`이 KST 9시).

이 방식은 GitHub 호스팅 셋업이 필요하므로, 본격 운영 단계로 가기 전까진 방법 1~3을 권장.

## 추천 흐름

- **POC 단계 (지금)**: 방법 1로 주 1회 수동.
- **운영 안정화**: 방법 3 (Windows Task Scheduler) — 가장 ROI 높음.
- **다른 사람에게 공유**: 방법 4 (GitHub Pages + routine) — 사용자 PC 의존성 제거.
