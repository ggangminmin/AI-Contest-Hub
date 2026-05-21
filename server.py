"""AI 공모전 보드 — 정적 호스팅 + /api/update 엔드포인트.

stdlib만 사용. python server.py 로 실행.
claude를 stream-json 출력 모드로 호출해서 진행 상황을 실시간 노출.
"""

import datetime
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlparse, parse_qs

PORT = 8765
HOST = "127.0.0.1"
ROOT = os.path.dirname(os.path.abspath(__file__))
CLAUDE_CMD = os.environ.get(
    "CLAUDE_BIN",
    r"C:\Users\user\AppData\Roaming\npm\claude.cmd",
)

# job_id -> {status, events: [...], stdout_tail, stderr_tail, ...}
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _summarize_event(raw_line: str) -> dict | None:
    """claude stream-json 한 줄을 사용자에게 보여줄 이벤트로 압축."""
    try:
        obj = json.loads(raw_line)
    except Exception:
        return {"kind": "raw", "text": raw_line[:200], "ts": time.time()}

    t = obj.get("type")
    if t == "system":
        sub = obj.get("subtype", "")
        return {"kind": "system", "text": f"세션 {sub}", "ts": time.time()}
    if t == "assistant":
        msg = obj.get("message", {})
        for c in msg.get("content", []):
            if c.get("type") == "tool_use":
                name = c.get("name", "?")
                inp = c.get("input", {})
                hint = ""
                if name == "WebSearch":
                    hint = inp.get("query", "")[:60]
                elif name == "WebFetch":
                    hint = inp.get("url", "")[:60]
                elif name in ("Write", "Edit", "Read"):
                    hint = inp.get("file_path", "")[:60]
                elif name == "Bash":
                    hint = (inp.get("description") or inp.get("command", ""))[:60]
                icon = {"WebSearch": "🔍", "WebFetch": "📄", "Write": "💾",
                        "Edit": "✏️", "Read": "📖", "Bash": "⚙️"}.get(name, "🔧")
                return {"kind": "tool", "text": f"{icon} {name}: {hint}", "ts": time.time()}
            if c.get("type") == "text":
                text = (c.get("text") or "").strip()
                if text:
                    return {"kind": "text", "text": text[:160], "ts": time.time()}
    if t == "user":
        msg = obj.get("message", {})
        for c in msg.get("content", []):
            if c.get("type") == "tool_result":
                content = c.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        x.get("text", "") for x in content if isinstance(x, dict)
                    )
                snippet = str(content)[:60].replace("\n", " ")
                return {"kind": "result", "text": f"  ↳ 결과: {snippet}…", "ts": time.time()}
    if t == "result":
        sub = obj.get("subtype", "")
        dur = obj.get("duration_ms", 0)
        return {"kind": "done", "text": f"✓ 완료 ({sub}, {dur/1000:.1f}s)", "ts": time.time()}
    return None


def _stream_reader(pipe, job_id: str, sink: str) -> None:
    """subprocess의 stdout/stderr 라인을 읽어 JOBS[job_id]에 누적."""
    try:
        for raw in iter(pipe.readline, ""):
            if not raw:
                break
            line = raw.rstrip("\n")
            if sink == "stdout":
                event = _summarize_event(line)
                with JOBS_LOCK:
                    if event:
                        JOBS[job_id]["events"].append(event)
                    # 원본 라인도 tail로 보관 (디버깅용, 최근 200줄)
                    tail = JOBS[job_id].setdefault("stdout_tail", [])
                    tail.append(line)
                    if len(tail) > 200:
                        del tail[: len(tail) - 200]
            else:
                with JOBS_LOCK:
                    tail = JOBS[job_id].setdefault("stderr_tail", [])
                    tail.append(line)
                    if len(tail) > 100:
                        del tail[: len(tail) - 100]
    finally:
        pipe.close()


VALID_CATS = {"app", "video", "image", "audio", "all"}


def cleanup_expired() -> dict:
    """contests.json에서 마감 지난 항목을 제거하고 결과 반환. claude 호출 안 함."""
    path = os.path.join(ROOT, "contests.json")
    today = datetime.date.today().isoformat()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    kept, removed = [], []
    for it in items:
        if it.get("deadline", "9999-99-99") < today:
            removed.append({"title": it.get("title"), "deadline": it.get("deadline")})
        else:
            kept.append(it)

    if removed:
        # 백업 한 부 떠두고 저장
        backup = path + ".bak"
        shutil.copyfile(path, backup)
        data["items"] = kept
        data["generated_at"] = today
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "removed_count": len(removed),
        "removed": removed,
        "remaining": len(kept),
        "today": today,
    }


def run_update_job(job_id: str, category: str = "all") -> None:
    with JOBS_LOCK:
        JOBS[job_id].update({
            "status": "running",
            "started_at": time.time(),
            "events": [],
            "stdout_tail": [],
            "stderr_tail": [],
        })

    cmd_arg = "/update-contests" if category == "all" else f"/update-contests {category}"
    try:
        proc = subprocess.Popen(
            [
                CLAUDE_CMD,
                "-p", cmd_arg,
                "--output-format", "stream-json",
                "--verbose",
                "--dangerously-skip-permissions",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # line-buffered
            shell=False,
        )
    except FileNotFoundError as e:
        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "error",
                "error": f"claude CLI not found: {e}. CLAUDE_BIN 환경변수 확인.",
                "ended_at": time.time(),
            })
        return
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
                "ended_at": time.time(),
            })
        return

    t_out = threading.Thread(target=_stream_reader, args=(proc.stdout, job_id, "stdout"), daemon=True)
    t_err = threading.Thread(target=_stream_reader, args=(proc.stderr, job_id, "stderr"), daemon=True)
    t_out.start()
    t_err.start()

    try:
        rc = proc.wait(timeout=900)
    except subprocess.TimeoutExpired:
        proc.kill()
        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "error",
                "error": "timeout (15분 초과)",
                "ended_at": time.time(),
            })
        return

    t_out.join(timeout=3)
    t_err.join(timeout=3)

    with JOBS_LOCK:
        JOBS[job_id].update({
            "status": "done" if rc == 0 else "error",
            "returncode": rc,
            "ended_at": time.time(),
        })


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/update":
            qs = parse_qs(parsed.query)
            cat = (qs.get("category", ["all"])[0] or "all").lower()
            if cat not in VALID_CATS:
                self._send_json(400, {"error": f"invalid category: {cat}"})
                return
            job_id = uuid.uuid4().hex[:12]
            with JOBS_LOCK:
                JOBS[job_id] = {"status": "pending", "created_at": time.time(), "category": cat}
            threading.Thread(target=run_update_job, args=(job_id, cat), daemon=True).start()
            self._send_json(202, {"job_id": job_id, "category": cat})
            return
        if parsed.path == "/api/cleanup-expired":
            try:
                result = cleanup_expired()
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"error": f"{type(e).__name__}: {e}"})
            return
        self.send_error(404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/status/"):
            job_id = parsed.path.removeprefix("/api/status/")
            # ?since=N → events[N:] 만 반환 (페이지가 incremental polling)
            since = 0
            if parsed.query:
                for kv in parsed.query.split("&"):
                    if kv.startswith("since="):
                        try: since = int(kv.split("=", 1)[1])
                        except: pass
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    self._send_json(404, {"error": "unknown job_id"})
                    return
                events = job.get("events", [])
                payload = {
                    "status": job.get("status"),
                    "returncode": job.get("returncode"),
                    "error": job.get("error"),
                    "started_at": job.get("started_at"),
                    "ended_at": job.get("ended_at"),
                    "events": events[since:],
                    "total_events": len(events),
                    "stderr_tail": job.get("stderr_tail", [])[-10:] if job.get("status") == "error" else [],
                }
            self._send_json(200, payload)
            return
        if parsed.path == "/api/jobs":
            with JOBS_LOCK:
                summary = {
                    k: {kk: vv for kk, vv in v.items() if kk in ("status", "started_at", "ended_at", "returncode")}
                    for k, v in JOBS.items()
                }
            self._send_json(200, summary)
            return
        super().do_GET()

    def log_message(self, fmt, *args) -> None:
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")


def main() -> None:
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"AI 공모전 보드 서버 실행: http://{HOST}:{PORT}/index.html")
    print(f"갱신 API: POST http://{HOST}:{PORT}/api/update")
    print(f"claude CLI: {CLAUDE_CMD}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")
        server.shutdown()


if __name__ == "__main__":
    main()
