"""Email the regression report after a run.

    python scripts/send_report.py                 # newest COMPLETED run
    python scripts/send_report.py --run RUN-XXXX  # a specific run
    python scripts/send_report.py --wait          # block until the active run ends, then send
    python scripts/send_report.py --dry-run       # build and print, send nothing

Reads the run from the platform's own HTTP API (so it sees exactly what the
UI shows), regenerates reports/*.md from the persisted rows, and mails an
HTML summary with those Markdown files attached.

SMTP settings come from config/local.yaml (gitignored) or the environment:

    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_SECURITY,
    REPORT_FROM, REPORT_TO

SMTP_SECURITY is starttls (default), ssl, or none. REPORT_TO accepts a
comma-separated list. Nothing is sent when SMTP_HOST is unset — the script
says so and exits non-zero rather than failing silently.
"""
from __future__ import annotations

import argparse
import html
import os
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.request
import json
from collections import Counter, defaultdict
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backend.config  # noqa: F401,E402  — loads .env + config/local.yaml into os.environ
from backend.config import settings  # noqa: E402

# Where the platform's API lives. Defaults to this machine, but the
# report-mailer container runs beside qa-platform and must reach it by
# service name, so QA_API overrides it.
API = os.environ.get("QA_API", "").rstrip("/") or f"http://127.0.0.1:{settings.server_port}"
REPORTS = ROOT / "reports"

# Status -> (label colour, background) for the summary table.
PALETTE = {
    "PASSED":  ("#116149", "#dff3ec"),
    "FAILED":  ("#8c2f2f", "#fbe4e4"),
    "ERROR":   ("#8a4b12", "#fbeddc"),
    "BLOCKED": ("#5b4b8a", "#eae6f7"),
    "SKIPPED": ("#55606b", "#e9edf1"),
}


def api(path: str):
    with urllib.request.urlopen(f"{API}{path}", timeout=120) as r:
        return json.load(r)


def pick_run(run_id: str | None, wait: bool):
    """The requested run, the newest completed one, or — with --wait — the
    active run once it finishes."""
    deadline = time.time() + 6 * 3600
    while True:
        runs = api("/api/runs")
        runs = runs.get("runs", runs) if isinstance(runs, dict) else runs
        if run_id:
            match = [r for r in runs if r.get("id") == run_id]
            if not match:
                sys.exit(f"Run {run_id} not found.")
            run = match[0]
        else:
            done = [r for r in runs if r.get("status") == "COMPLETED"]
            active = [r for r in runs if r.get("status") == "RUNNING"]
            if wait and active:
                print(f"  waiting for {active[0]['id']} ...")
                if time.time() > deadline:
                    sys.exit("Timed out waiting for the active run.")
                time.sleep(20)
                continue
            if not done:
                sys.exit("No completed run to report on.")
            run = done[0]
        if wait and run.get("status") == "RUNNING":
            time.sleep(20)
            continue
        return api(f"/api/runs/{run['id']}")


def regenerate_reports(run_id: str) -> list[Path]:
    """Rebuild every attachment FROM THIS RUN, so nothing stale ships.

    Attachments are picked up with a glob, so any .md left in reports/ goes
    out with the mail. FAILURES.md is written by a different script than the
    rollups, and mailing last week's failures alongside this run's summary is
    worse than mailing no failures at all — so both are regenerated here, and
    a FAILURES.md that could not be rebuilt is dropped rather than sent.
    """
    for script, extra in (
            ("gen_reports.py", []),
            ("gen_failure_report.py", ["--run", run_id,
                                       "--out", str(REPORTS / "FAILURES.md")]),
    ):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *extra],
                              cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"  WARNING: {script} failed", flush=True)
            print(proc.stderr[-600:], flush=True)
            if script == "gen_failure_report.py":
                (REPORTS / "FAILURES.md").unlink(missing_ok=True)
    return sorted(REPORTS.glob("*.md"))


def build_html(run: dict) -> tuple[str, str]:
    results = run.get("results") or []
    counts = Counter(r.get("status") for r in results)
    by_wf: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        by_wf[r.get("workflow") or "—"][r.get("status")] += 1

    total = len(results)
    passed = counts.get("PASSED", 0)
    rate = f"{passed / total * 100:.0f}%" if total else "—"
    env = run.get("environment_name") or run.get("environment") or "—"

    subject = (f"[DataOne QA] {run.get('id')} — {passed}/{total} passed "
               f"({rate}) on {env}")

    def chip(status, n):
        fg, bg = PALETTE.get(status, ("#55606b", "#e9edf1"))
        return (f'<span style="display:inline-block;padding:2px 9px;border-radius:99px;'
                f'background:{bg};color:{fg};font-size:12px;font-weight:600;'
                f'margin-right:6px">{html.escape(status)} {n}</span>')

    rows = []
    for wf in sorted(by_wf):
        c = by_wf[wf]
        cells = "".join(
            f'<td style="padding:7px 10px;border-bottom:1px solid #e6ebf0;'
            f'text-align:right;font-variant-numeric:tabular-nums">{c.get(s, 0) or ""}</td>'
            for s in ("PASSED", "FAILED", "ERROR", "BLOCKED", "SKIPPED"))
        rows.append(
            f'<tr><td style="padding:7px 10px;border-bottom:1px solid #e6ebf0;'
            f'font-family:ui-monospace,monospace;font-size:13px">{html.escape(wf)}</td>{cells}</tr>')

    # Failures worth reading in the mail body itself.
    bad = [r for r in results if r.get("status") in ("FAILED", "ERROR")][:15]
    fail_rows = "".join(
        f'<tr><td style="padding:6px 10px;border-bottom:1px solid #e6ebf0;'
        f'font-family:ui-monospace,monospace;font-size:12px;white-space:nowrap">'
        f'{html.escape(str(r.get("test_id")))}</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #e6ebf0;font-size:13px">'
        f'{html.escape(str(r.get("name") or ""))[:90]}<br>'
        f'<span style="color:#8c2f2f;font-size:12px">'
        f'{html.escape(str(r.get("error") or r.get("failed_step") or ""))[:150]}</span></td></tr>'
        for r in bad)

    head = "".join(
        f'<th style="padding:7px 10px;text-align:right;font-size:11px;'
        f'letter-spacing:.07em;text-transform:uppercase;color:#6b7885;'
        f'border-bottom:1px solid #cfd8e0">{s}</th>'
        for s in ("Passed", "Failed", "Error", "Blocked", "Skipped"))

    body = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;
color:#16202b;line-height:1.55;max-width:760px">
  <h2 style="margin:0 0 4px;font-size:19px">DataOne regression — {html.escape(str(run.get('id')))}</h2>
  <p style="margin:0 0 14px;color:#55606b;font-size:14px">
    Target <strong>{html.escape(str(env))}</strong> ·
    {total} test cases · {rate} passed
  </p>
  <p style="margin:0 0 18px">{"".join(chip(s, n) for s, n in counts.most_common())}</p>

  <h3 style="margin:22px 0 6px;font-size:14px;text-transform:uppercase;
  letter-spacing:.07em;color:#6b7885">By workflow</h3>
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <thead><tr>
      <th style="padding:7px 10px;text-align:left;font-size:11px;letter-spacing:.07em;
      text-transform:uppercase;color:#6b7885;border-bottom:1px solid #cfd8e0">Workflow</th>{head}
    </tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>

  {"<h3 style='margin:26px 0 6px;font-size:14px;text-transform:uppercase;letter-spacing:.07em;color:#6b7885'>Failed / error</h3><table style='border-collapse:collapse;width:100%'><tbody>" + fail_rows + "</tbody></table>" if fail_rows else ""}

  <p style="margin:24px 0 0;font-size:12px;color:#8290a0;border-top:1px solid #e6ebf0;padding-top:12px">
    Attached: per-workflow reports, plus <strong>FAILURES.md</strong> — every
    failed and errored case with its source file and line, docstring, failing
    step and expected vs actual, grouped by root cause.
    Full evidence (screenshots, Playwright traces, assertions) at
    <a href="https://testd1.odoovietnam.net/#/runs/{html.escape(str(run.get('id')))}"
       style="color:#b0511c">testd1.odoovietnam.net</a>.
  </p>
</div>"""
    return subject, body


STATE = ROOT / "data" / "report_sent.json"


def _sent_ids() -> set[str]:
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _mark_sent(ids: set[str]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def watch(recipients: list[str], interval: int = 30) -> None:
    """Poll forever; mail each run once, as it completes.

    On the very first start the existing completed runs are recorded as
    already-sent, so switching this on does not blast out a backlog.
    """
    first = not STATE.exists()
    seen = _sent_ids()
    if first:
        try:
            runs = api("/api/runs")
            runs = runs.get("runs", runs) if isinstance(runs, dict) else runs
            seen = {r["id"] for r in runs if r.get("status") == "COMPLETED"}
            _mark_sent(seen)
            print(f"  first start: {len(seen)} run cu duoc danh dau da gui, khong mail lai",
                  flush=True)
        except Exception as e:
            print(f"  WARN: khong doc duoc danh sach run ({e}); bat dau voi state rong",
                  flush=True)

    print(f"  dang theo doi, gui toi {', '.join(recipients)} moi {interval}s", flush=True)
    while True:
        try:
            runs = api("/api/runs")
            runs = runs.get("runs", runs) if isinstance(runs, dict) else runs
            fresh = [r for r in runs
                     if r.get("status") == "COMPLETED" and r["id"] not in seen]
            for r in reversed(fresh):           # oldest first
                run = api(f"/api/runs/{r['id']}")
                subject, body = build_html(run)
                send(subject, body, regenerate_reports(r["id"]), recipients)
                print(f"  SENT {r['id']} -> {', '.join(recipients)}", flush=True)
                seen.add(r["id"])
                _mark_sent(seen)
        except Exception as e:
            # Never let one bad cycle kill the watcher.
            print(f"  WARN cycle failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
        time.sleep(interval)


def send(subject: str, body: str, attachments: list[Path],
         recipients: list[str]) -> None:
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        sys.exit("SMTP_HOST is not set — add the SMTP block to config/local.yaml.")
    port = int(os.environ.get("SMTP_PORT") or 587)
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    security = (os.environ.get("SMTP_SECURITY") or "starttls").lower()
    sender = os.environ.get("REPORT_FROM", "").strip() or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content("DataOne regression report — see the HTML version or the attachments.")
    msg.add_alternative(body, subtype="html")
    for p in attachments:
        msg.add_attachment(p.read_bytes(), maintype="text", subtype="markdown",
                           filename=p.name)

    ctx = ssl.create_default_context()
    if security == "ssl":
        srv = smtplib.SMTP_SSL(host, port, context=ctx, timeout=60)
    else:
        srv = smtplib.SMTP(host, port, timeout=60)
        if security == "starttls":
            srv.starttls(context=ctx)
    with srv:
        if user:
            srv.login(user, password)
        srv.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="run id (default: newest COMPLETED)")
    ap.add_argument("--wait", action="store_true",
                    help="block until the active run finishes, then send")
    ap.add_argument("--watch", action="store_true",
                    help="stay running and mail every run as it completes")
    ap.add_argument("--interval", type=int, default=30,
                    help="poll seconds for --watch (default 30)")
    ap.add_argument("--to", help="override REPORT_TO")
    ap.add_argument("--dry-run", action="store_true", help="build but do not send")
    args = ap.parse_args()

    if args.watch:
        to = (args.to or os.environ.get("REPORT_TO", "")).strip()
        if not to:
            sys.exit("REPORT_TO is not set (config/local.yaml or environment).")
        watch([a.strip() for a in to.split(",") if a.strip()], args.interval)
        return

    run = pick_run(args.run, args.wait)
    subject, body = build_html(run)
    attachments = regenerate_reports(run["id"])

    to = (args.to or os.environ.get("REPORT_TO", "")).strip()
    if not to:
        sys.exit("REPORT_TO is not set (config/local.yaml or environment).")
    recipients = [a.strip() for a in to.split(",") if a.strip()]

    print(f"  run     : {run.get('id')}  ({run.get('status')})")
    print(f"  subject : {subject}")
    print(f"  to      : {', '.join(recipients)}")
    print(f"  attach  : {', '.join(p.name for p in attachments) or 'none'}")

    if args.dry_run:
        print("  --dry-run: nothing sent")
        return

    send(subject, body, attachments, recipients)
    print(f"  SENT to {', '.join(recipients)}")


if __name__ == "__main__":
    main()
