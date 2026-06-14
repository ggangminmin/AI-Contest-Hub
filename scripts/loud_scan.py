#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
loud.kr AI 공모전 스캐너 — /update-contests 의 고정 소스 크롤러.

loud.kr 은 SPA(백엔드 api.stunning.kr)라 일반 WebFetch 로는 목록이 안 보인다.
또한 '일반 숏폼/영상 공모전이지만 AI 허용'인 건은 제목/목록엔 AI 표시가 없고
브리핑 본문 '특이사항'에만 적혀 있어 키워드 검색으로 놓치기 쉽다.

이 스크립트는 두 가지 확정 경로를 조합해 누락을 막는다:
  1) ID 열거: Jina Reader 로 https://www.loud.kr/contest?page=N 를 여러 번(패스) 렌더링해
     contest/view/{id} 를 union (loud 의 추천순 정렬이 요청마다 섞여 단일 패스는 부분만 잡힘)
  2) 정밀 판별: https://api.stunning.kr/api/v1/dantats/contest/{id} (로그인 불필요, 깔끔한 JSON)
     → title / recruitEndDate(UTC) / totalPrize / briefing 본문 텍스트

판정: 마감일(KST) >= 오늘  AND  (제목+브리핑 본문에 AI|인공지능|생성형 매칭)
출력: 후보를 JSON 으로 stdout (그대로 검증 후 contests.json 에 추가)

사용:
  python scripts/loud_scan.py --today 2026-06-14 [--pages 8] [--passes 2] [--ids 199856,204537]
  (인터넷 차단 환경이면 --ids 로 알고 있는 ID 만 정밀 판별도 가능)
"""
import sys, re, json, argparse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

# Windows 콘솔(cp949)에서도 한글 JSON 출력이 깨지지 않도록 UTF-8 고정
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
AI_RE = re.compile(r"(인공지능|생성형|\bAI\b|\bA\.I\b)", re.IGNORECASE)
KST = timezone(timedelta(hours=9))


def classify_ai(title, brief):
    """제목+브리핑에서 AI 관련 문장을 뽑아 허용/제한을 판정.
    반환: (verdict, snippets)  verdict ∈ {ai_allowed, ai_restricted, none}
    - ai_allowed   : AI(생성)로 만든 결과물이 허용/환영/필수  → 보드 추가 후보
    - ai_restricted: AI는 보조만 / AI 전용작 불인정 / 최종물 AI 금지 → 제외(보고는 함)
    - none         : AI 무관
    """
    text = title + " . " + brief
    # 문장 단위 분리 (한국어 마침표/구분자)
    parts = re.split(r"[.。·\n]|(?:\s-\s)|※", text)
    NEG = re.compile(r"(인정되지\s*않|인정\s*안|불가|금지|제외|보조\s*도구|최종\s*(작업물|결과물).{0,12}(사용|AI))")
    POS = re.compile(r"(생성형\s*AI|인공지능|AI).{0,15}(가능|허용|환영|필수|활용|제작|영상|이미지|콘텐츠)")
    # 'AI' 가 어도비 일러스트레이터 파일/단순 면책일 때 제외할 노이즈
    NOISE = re.compile(r"(PSD\s*,?\s*AI|AI\s*등|AI\s*파일|\.ai\b|활용\s*내역|저작권\s*문제)")
    snippets, pos_hit, neg_hit = [], False, False
    for s in parts:
        s = s.strip()
        if not s or not AI_RE.search(s):
            continue
        if NOISE.search(s) and not POS.search(s):
            continue  # 일러스트 파일/면책 등 노이즈 문장은 스킵
        snippets.append(s[:120])
        if NEG.search(s):
            neg_hit = True
        if POS.search(s):
            pos_hit = True
    if not snippets:
        return "none", []
    # 제목에 AI 가 있으면 강한 양성 신호
    if AI_RE.search(title):
        pos_hit = True
    if pos_hit and not neg_hit:
        return "ai_allowed", snippets
    if neg_hit and not pos_hit:
        return "ai_restricted", snippets
    # 양/음 혼재 → 사람이 봐야 함 (보수적으로 restricted 로 분류하되 스니펫 제공)
    return ("ai_allowed" if (AI_RE.search(title)) else "ai_restricted"), snippets


def _get(url, headers=None, timeout=45):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def enumerate_ids(pages, passes):
    """Jina 로 목록 페이지를 여러 패스 렌더링해 contest id 를 union."""
    ids = set()
    for _ in range(passes):
        for p in range(1, pages + 1):
            url = f"https://r.jina.ai/https://www.loud.kr/contest?page={p}"
            try:
                txt = _get(url)
            except Exception as e:
                print(f"  [warn] page {p}: {e}", file=sys.stderr)
                continue
            found = re.findall(r"contest/view/(\d+)", txt)
            ids.update(found)
    return ids


def fetch_detail(cid):
    """단일 공모전 상세 — api.stunning.kr (Origin/Referer 헤더 필요)."""
    url = f"https://api.stunning.kr/api/v1/dantats/contest/{cid}"
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Origin": "https://www.loud.kr",
        "Referer": "https://www.loud.kr/",
    }
    try:
        d = json.loads(_get(url, headers, timeout=25))
    except Exception as e:
        return None
    rd = d.get("resultData")
    if not rd:
        return None
    # 브리핑 본문 텍스트 평탄화 (HTML 태그/URL 제거 후 매칭 — 안 그러면 이미지 URL 의 'ai' 등에 오탐)
    brief_txt = ""
    try:
        for c in rd.get("briefing", {}).get("contents", []) or []:
            brief_txt += " " + str(c.get("content", ""))
    except Exception:
        pass
    brief_txt = re.sub(r"<[^>]+>", " ", brief_txt)   # 태그 제거
    brief_txt = re.sub(r"https?://\S+", " ", brief_txt)  # URL 제거
    brief_txt = re.sub(r"\s+", " ", brief_txt)
    verdict, snippets = classify_ai(rd.get("title", ""), brief_txt)
    end_utc = rd.get("recruitEndDate")
    deadline_kst = None
    if end_utc:
        try:
            dt = datetime.fromisoformat(end_utc.replace("Z", "+00:00")).astimezone(KST)
            deadline_kst = dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return {
        "id": cid,
        "title": rd.get("title", "").strip(),
        "deadline": deadline_kst,
        "totalPrize": rd.get("totalPrize"),
        "official": f"https://www.loud.kr/contest/view/{cid}/brief",
        "verdict": verdict,        # ai_allowed | ai_restricted | none
        "ai_snippets": snippets,   # 근거 문장 (사람이 최종 확인)
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", required=True, help="YYYY-MM-DD (시스템 currentDate)")
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--ids", default="", help="쉼표구분 ID (열거 건너뛰고 이것만 판별)")
    args = ap.parse_args()

    if args.ids.strip():
        ids = {x.strip() for x in args.ids.split(",") if x.strip()}
    else:
        print("[*] loud.kr 목록 열거 (Jina 다중 패스)...", file=sys.stderr)
        ids = enumerate_ids(args.pages, args.passes)
    print(f"[*] 대상 ID {len(ids)}개 정밀 판별...", file=sys.stderr)

    candidates = []
    for cid in sorted(ids):
        info = fetch_detail(cid)
        if not info or not info["deadline"]:
            continue
        if info["deadline"] < args.today:
            continue  # 만료
        if info["verdict"] == "none":
            continue  # AI 무관 (로고/브랜딩 등)
        candidates.append(info)

    candidates.sort(key=lambda x: (x["verdict"] != "ai_allowed", x["deadline"]))
    print(json.dumps(candidates, ensure_ascii=False, indent=2))
    allowed = [c for c in candidates if c["verdict"] == "ai_allowed"]
    print(f"\n[*] ai_allowed {len(allowed)}건 / ai_restricted {len(candidates)-len(allowed)}건 "
          f"(마감>= {args.today}). ai_allowed 만 검증 후 추가, restricted 는 스니펫 보고 판단.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
