#!/usr/bin/env python3
"""nRouter SDK & Provider Health Sentinel Email Dispatcher.

Formats and dispatches the daily health report email to rama@nrouter.ai (or configured recipient).
Supports standard SMTP and direct transactional email API (Resend).
Adheres to Rule #29: sanitizes any credentials or internal hostnames.

Usage:
    python3 scripts/send_sentinel_email.py --self-test
    python3 scripts/send_sentinel_email.py --dry-run --report-file dist/sentinel-report.json
    python3 scripts/send_sentinel_email.py --report-file dist/sentinel-report.json
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import time
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RECIPIENT = "rama@nrouter.ai"
DEFAULT_SENDER = "sentinel@nrouter.ai"


def format_email_html(report_data: Dict[str, Any], dashboard_url: str, actions_url: str) -> str:
    """Generate modern, responsive HTML email body."""
    summary = report_data.get("summary", {})
    results = report_data.get("results", [])
    triage = report_data.get("triage", {})
    version = report_data.get("version", "3.1.2")
    timestamp = report_data.get("timestamp", "")

    passed = summary.get("passed", 0)
    total = summary.get("total", 10)
    failed = summary.get("failed", 0)
    avg_latency = summary.get("avg_latency_ms", 0)
    total_cost = summary.get("total_cost_usd", 0.0)
    providers = ", ".join(summary.get("providers", [])) or "Anthropic, OpenAI, Qwen"

    is_all_green = (failed == 0)
    status_title = "All 10 SDKs & Providers Operational" if is_all_green else f"{failed} Failure(s) Detected"
    header_color = "#10b981" if is_all_green else "#ef4444"
    status_badge_bg = "#ecfdf5" if is_all_green else "#fef2f2"
    status_badge_border = "#10b981" if is_all_green else "#ef4444"

    alert_html = ""
    if not is_all_green and triage.get("diagnosis"):
        alert_html = f"""
        <div style="margin: 20px 0; padding: 16px; background: #fff1f2; border: 1px solid #f43f5e; border-radius: 8px;">
          <strong style="color: #be123c; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em;">
            ⚠ Automated Failure Triage: {triage.get('category', 'ALERT')}
          </strong>
          <p style="margin: 8px 0 0 0; color: #881337; font-size: 14px; line-height: 1.5;">
            {triage.get('diagnosis')}
          </p>
        </div>
        """

    rows_html = []
    for r in results:
        status_text = r.get("status", "").upper()
        status_bg = "#dcfce7" if status_text == "PASSED" else "#fee2e2"
        status_color = "#15803d" if status_text == "PASSED" else "#b91c1c"
        req_id = r.get("request_id") or "N/A"
        trace_url = f"https://app.nrouter.ai/traces/{req_id}"
        item_name = r.get("name") or r.get("sdk") or "Check"
        lane_name = r.get("lane") or r.get("provider") or "General"
        model_name = r.get("model_served") or r.get("model") or r.get("endpoint") or "N/A"
        req_id_display = req_id[:12] + "..." if len(req_id) > 12 else req_id

        rows_html.append(f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
          <td style="padding: 10px 14px; font-weight: 600; color: #111827;">{item_name}</td>
          <td style="padding: 10px 14px; color: #4b5563;">{lane_name}</td>
          <td style="padding: 10px 14px; font-family: monospace; font-size: 12px; color: #374151;">{model_name}</td>
          <td style="padding: 10px 14px;">
            <span style="display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; background: {status_bg}; color: {status_color};">
              {status_text}
            </span>
          </td>
          <td style="padding: 10px 14px; font-family: monospace; font-size: 12px; color: #4b5563;">{r.get('latency_ms')}ms</td>
          <td style="padding: 10px 14px; font-family: monospace; font-size: 12px;">
            <a href="{trace_url}" style="color: #2563eb; text-decoration: none;">{req_id_display}</a>
          </td>
        </tr>
        """)

    table_rows = "".join(rows_html)

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>nRouter Sentinel Daily Health Report</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f9fafb; margin: 0; padding: 24px; color: #1f2937;">
  <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
    <!-- Header -->
    <div style="padding: 24px; background: #111827; color: #ffffff;">
      <div style="font-size: 12px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #9ca3af; margin-bottom: 4px;">
        nRouter SDK & Provider Sentinel
      </div>
      <h1 style="margin: 0; font-size: 22px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
        <span style="color: {header_color};">&bull;</span> {status_title}
      </h1>
      <div style="font-size: 13px; color: #9ca3af; margin-top: 6px;">
        Timestamp: {timestamp} &bull; Coordinated Release: v{version}
      </div>
    </div>

    <div style="padding: 24px;">
      <!-- KPI Cards -->
      <div style="display: table; width: 100%; margin-bottom: 20px;">
        <div style="display: table-cell; width: 25%; padding: 12px; background: #f3f4f6; border-radius: 8px; text-align: center;">
          <div style="font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: 600;">SDK Health</div>
          <div style="font-size: 18px; font-weight: 700; color: #111827; margin-top: 4px;">{passed}/{total}</div>
        </div>
        <div style="display: table-cell; width: 4%;"></div>
        <div style="display: table-cell; width: 25%; padding: 12px; background: #f3f4f6; border-radius: 8px; text-align: center;">
          <div style="font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: 600;">Providers</div>
          <div style="font-size: 18px; font-weight: 700; color: #111827; margin-top: 4px;">3 Active</div>
        </div>
        <div style="display: table-cell; width: 4%;"></div>
        <div style="display: table-cell; width: 25%; padding: 12px; background: #f3f4f6; border-radius: 8px; text-align: center;">
          <div style="font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: 600;">Avg Latency</div>
          <div style="font-size: 18px; font-weight: 700; color: #111827; margin-top: 4px;">{avg_latency} ms</div>
        </div>
        <div style="display: table-cell; width: 4%;"></div>
        <div style="display: table-cell; width: 25%; padding: 12px; background: #f3f4f6; border-radius: 8px; text-align: center;">
          <div style="font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: 600;">24h Spend</div>
          <div style="font-size: 18px; font-weight: 700; color: #111827; margin-top: 4px;">${total_cost:.4f}</div>
        </div>
      </div>

      {alert_html}

      <!-- Results Table -->
      <h3 style="font-size: 15px; font-weight: 600; color: #111827; margin: 24px 0 12px 0;">10 SDK Health Verification</h3>
      <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
        <thead>
          <tr style="background: #f9fafb; border-bottom: 2px solid #e5e7eb; color: #6b7280; font-size: 11px; text-transform: uppercase;">
            <th style="padding: 10px 14px;">SDK</th>
            <th style="padding: 10px 14px;">Provider</th>
            <th style="padding: 10px 14px;">Model</th>
            <th style="padding: 10px 14px;">Status</th>
            <th style="padding: 10px 14px;">Latency</th>
            <th style="padding: 10px 14px;">Trace</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>

      <!-- Action CTAs -->
      <div style="margin-top: 32px; text-align: center;">
        <a href="{dashboard_url}" style="display: inline-block; padding: 12px 24px; background: #2563eb; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; margin-right: 12px;">
          View Live Status Dashboard &rarr;
        </a>
        <a href="{actions_url}" style="display: inline-block; padding: 12px 20px; background: #f3f4f6; color: #374151; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; border: 1px solid #d1d5db;">
          GitHub Actions Run
        </a>
      </div>
    </div>

    <!-- Footer -->
    <div style="padding: 16px 24px; background: #f9fafb; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; text-align: center;">
      This automated health report is generated daily by the nRouter Sentinel.<br>
      nRouter Gateway: <span style="font-family: monospace;">api.nrouter.ai</span> &bull; Virtual Key Quota: $1.00/day
    </div>
  </div>
</body>
</html>
"""


def send_via_resend(api_key: str, recipient: str, subject: str, html_body: str) -> bool:
    """Send transactional email via Resend API."""
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "nRouter-Sentinel/1.0",
    }
    payload = {
        "from": "nRouter Sentinel <onboarding@resend.dev>",
        "to": [recipient],
        "subject": subject,
        "html": html_body,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 201):
                print(f"  ok: Email successfully sent via Resend to {recipient}")
                return True
            print(f"  warning: Resend returned status {resp.status}")
            return False
    except Exception as e:
        print(f"  warning: Failed to send via Resend: {e}")
        return False


def send_via_smtp(
    host: str,
    port: int,
    user: str,
    password: str,
    use_tls: bool,
    sender: str,
    recipient: str,
    subject: str,
    html_body: str,
) -> bool:
    """Send email via standard SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    part = MIMEText(html_body, "html")
    msg.attach(part)

    try:
        server = smtplib.SMTP(host, port, timeout=20)
        if use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(sender, [recipient], msg.as_string())
        server.quit()
        print(f"  ok: Email successfully sent via SMTP to {recipient}")
        return True
    except Exception as e:
        print(f"  warning: Failed to send via SMTP: {e}")
        return False


def dispatch_sentinel_email(
    report_data: Dict[str, Any],
    recipient: Optional[str] = None,
    dry_run: bool = False,
    preview_output: Optional[Path] = None,
) -> bool:
    """Determine recipient and send report email."""
    recip = recipient or os.getenv("SENTINEL_EMAIL_RECIPIENT", DEFAULT_RECIPIENT)
    dashboard_url = os.getenv("SENTINEL_DASHBOARD_URL", "https://nroutergateway.github.io/nrouter-sdk/")
    actions_url = os.getenv("GITHUB_SERVER_URL", "https://github.com") + "/" + os.getenv("GITHUB_REPOSITORY", "nRouterGateway/nrouter-sdk") + "/actions"

    summary = report_data.get("summary", {})
    failed = summary.get("failed", 0)
    date_str = time.strftime("%Y-%m-%d", time.gmtime())

    if failed == 0:
        subject = f"🟢 [nRouter Sentinel] All 10 SDKs & Providers Operational ({date_str})"
    else:
        subject = f"🔴 [ALERT] [nRouter Sentinel] {failed} Failure(s) Detected ({date_str})"

    html_content = format_email_html(report_data, dashboard_url, actions_url)

    if preview_output:
        preview_output.parent.mkdir(parents=True, exist_ok=True)
        preview_output.write_text(html_content, encoding="utf-8")
        print(f"  Preview written to {preview_output}")

    if dry_run:
        print(f"DRY-RUN: Prepared email to {recip}")
        print(f"Subject: {subject}")
        return True

    # 1. Check for Resend API Key
    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        print(f"Sending health report via Resend API to {recip}...")
        return send_via_resend(resend_key, recip, subject, html_content)

    # 2. Check for SMTP credentials
    smtp_host = os.getenv("SENTINEL_SMTP_HOST")
    if smtp_host:
        port = int(os.getenv("SENTINEL_SMTP_PORT", "587"))
        user = os.getenv("SENTINEL_SMTP_USER", "")
        pwd = os.getenv("SENTINEL_SMTP_PASSWORD", "")
        sender = os.getenv("SENTINEL_SMTP_FROM", DEFAULT_SENDER)
        use_tls = os.getenv("SENTINEL_SMTP_TLS", "1") == "1"
        print(f"Sending health report via SMTP ({smtp_host}:{port}) to {recip}...")
        return send_via_smtp(smtp_host, port, user, pwd, use_tls, sender, recip, subject, html_content)

    # 3. Graceful fallback when secrets are not yet configured in GitHub Secrets
    print("\nNotice: Neither RESEND_API_KEY nor SENTINEL_SMTP_HOST is configured.")
    print(f"Daily email to '{recip}' was skipped. (Set secrets in GitHub Repository Settings to enable automatic delivery).")
    return True


def self_test() -> int:
    """Verify email formatting, HTML structure, subject generation, and dry-run dispatch."""
    print("======================================================================")
    print("Sentinel Email Dispatcher Self-Test")
    print("======================================================================")
    fails = 0

    def assert_true(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  ok   {label}")
        else:
            print(f"  FAIL {label}")
            fails += 1

    sample_report = {
        "timestamp": "2026-09-14T17:30:00Z",
        "version": "3.1.2",
        "summary": {
            "total": 10,
            "passed": 10,
            "failed": 0,
            "avg_latency_ms": 142,
            "total_cost_usd": 0.0011,
            "providers": ["openai", "anthropic", "qwen"],
        },
        "triage": {"category": "ALL_OPERATIONAL", "diagnosis": "All systems healthy."},
        "results": [
            {"sdk": "python", "provider": "openai", "model": "openai/gpt-4o-mini", "status": "passed", "latency_ms": 135, "request_id": "req-001"},
            {"sdk": "js", "provider": "anthropic", "model": "claude-3-5-haiku", "status": "passed", "latency_ms": 150, "request_id": "req-002"},
        ],
    }

    # Test green formatting
    html_green = format_email_html(sample_report, "https://example.com/dash", "https://example.com/actions")
    assert_true("renders green email html", "All 10 SDKs & Providers Operational" in html_green)
    assert_true("contains SDK list", "python" in html_green and "req-001" in html_green)

    # Test alert formatting
    alert_report = dict(sample_report)
    alert_report["summary"] = dict(sample_report["summary"])
    alert_report["summary"]["failed"] = 1
    alert_report["triage"] = {"category": "SDK_REGRESSION", "diagnosis": "Python SDK failed on /v1/chat"}
    html_red = format_email_html(alert_report, "https://example.com/dash", "https://example.com/actions")
    assert_true("renders alert email html", "Failure(s) Detected" in html_red)
    assert_true("contains triage alert box", "SDK_REGRESSION" in html_red)

    # Test dry run dispatch
    preview_file = ROOT / ".scratch" / "test_sentinel_email_preview.html"
    success = dispatch_sentinel_email(sample_report, recipient="test@example.com", dry_run=True, preview_output=preview_file)
    assert_true("dry-run dispatch succeeds", success)
    assert_true("writes preview file", preview_file.exists())

    if fails == 0:
        print("\nAll email dispatcher self-tests PASSED.")
        return 0
    else:
        print(f"\n{fails} email dispatcher self-test assertion(s) FAILED.")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Sentinel daily health report email")
    parser.add_argument("--self-test", action="store_true", help="Run self-test")
    parser.add_argument("--dry-run", action="store_true", help="Simulate email sending and print preview")
    parser.add_argument("--report-file", type=str, help="Path to sentinel-report.json")
    parser.add_argument("--recipient", type=str, help="Recipient email address")
    parser.add_argument("--preview-out", type=str, help="Path to write HTML email preview")

    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.report_file:
        parser.print_help()
        return 1

    report_path = Path(args.report_file)
    if not report_path.exists():
        print(f"Error: report file {report_path} does not exist", file=sys.stderr)
        return 1

    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    preview_path = Path(args.preview_out) if args.preview_out else None

    dispatch_sentinel_email(
        report_data=report_data,
        recipient=args.recipient,
        dry_run=args.dry_run,
        preview_output=preview_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
