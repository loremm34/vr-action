import json
import sys
import os
import urllib.request
import urllib.error
import argparse
import time
from pathlib import Path


def collect_github_context() -> dict:
    """Collect GitHub metadata from Actions env/event payload for PR notifications."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    commit_sha = os.environ.get("GITHUB_SHA")
    pr_number = None

    if event_name == "pull_request" and event_path and Path(event_path).exists():
        try:
            with open(event_path, "r", encoding="utf-8") as f:
                event = json.load(f)
            pr = event.get("pull_request", {})
            pr_number = pr.get("number")
            head_sha = pr.get("head", {}).get("sha")
            if head_sha:
                commit_sha = head_sha
        except Exception as e:
            print(f"[!] Failed to parse GitHub event payload: {e}")

    ctx = {
        "github_repo": repo,
        "github_commit_sha": commit_sha,
        "github_pr_number": pr_number,
    }
    return {k: v for k, v in ctx.items() if v}


def load_pages(args) -> tuple:
    """
    Load pages list and suite name from various sources (priority order):
      1. --pages-file  — JSON file containing an array of page objects
      2. --config-file — full config JSON with a "pages" field
      3. legacy        — tests/config/{suite}.json (backward compat)

    Returns (pages_list, suite_name).
    """
    suite = args.suite

    # 1. Inline pages file written by action from the `pages` input
    if args.pages_file:
        with open(args.pages_file, "r", encoding="utf-8") as f:
            pages = json.load(f)
        if not isinstance(pages, list):
            raise ValueError("--pages-file must contain a JSON array of page objects")
        return pages, suite

    # 2. Full config file provided via --config-file
    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        suite = config.get("suite", suite)
        pages = config.get("pages", [])
        return pages, suite

    # 3. Legacy: tests/config/{suite}.json (for users who have the old file layout)
    legacy_path = Path("tests") / "config" / f"{suite}.json"
    if legacy_path.exists():
        with open(legacy_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        suite = config.get("suite", suite)
        raw_pages = config.get("pages", [])
        config_dir = Path("tests/config")
        resolved = []
        for p in raw_pages:
            if isinstance(p, str):
                page_path = config_dir / p
                with open(page_path, "r", encoding="utf-8") as f:
                    resolved.append(json.load(f))
            else:
                resolved.append(p)
        return resolved, suite

    raise ValueError(
        "No pages source found. Provide --pages-file, --config-file, "
        f"or create tests/config/{suite}.json in your repo."
    )


def run_tests(
    backend_url: str,
    project_id: str,
    api_key: str,
    base_url: str,
    suite: str,
    pages: list,
    threshold: float = 0.1,
    detect_noise: bool = False,
    poll_interval: int = 5,
    output_file: str = "visual-report.json",
) -> dict:
    github_ctx = collect_github_context()

    payload = {
        "suite": suite,
        "base_url": base_url,
        "threshold": threshold,
        "auto_create_missing_baseline": True,
        "detect_noise": detect_noise,
        "pages": pages,
    }
    payload.update(github_ctx)

    if github_ctx:
        print(
            "[*] GitHub context: "
            f"repo={github_ctx.get('github_repo')} "
            f"sha={(github_ctx.get('github_commit_sha') or '')[:7]} "
            f"pr={github_ctx.get('github_pr_number')}"
        )
    else:
        print("[*] GitHub context not detected; PR bot notifications will be skipped")

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{backend_url}/v1/projects/{project_id}/runs",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            report = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"ERROR: HTTP {e.code}: {error_body}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to connect to backend: {e}")
        sys.exit(1)

    # Poll until the run completes (async queue returns "pending")
    if report.get("status") == "pending":
        run_id = report["id"]
        poll_url = f"{backend_url}/v1/projects/{project_id}/runs/{run_id}"
        poll_headers = {"X-API-Key": api_key}
        max_attempts = 120  # 120 × 5s = 10 min max
        print(f"[*] Run queued (id={run_id}), waiting for completion...")

        for attempt in range(1, max_attempts + 1):
            time.sleep(poll_interval)
            poll_req = urllib.request.Request(poll_url, headers=poll_headers, method="GET")
            try:
                with urllib.request.urlopen(poll_req, timeout=30) as resp:
                    report = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"[!] Poll attempt {attempt} failed: {e}")
                continue

            current_status = report.get("status", "unknown")
            if current_status != "pending":
                print(f"[*] Run completed: {current_status} (after {attempt * poll_interval}s)")
                break

            if attempt % 5 == 0:
                print(f"[*] Still pending... ({attempt * poll_interval}s elapsed)")
        else:
            print("[!] Timed out waiting for run to complete")
            sys.exit(1)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def main():
    parser = argparse.ArgumentParser(description="Run visual regression tests")
    parser.add_argument("--suite", default="website", help="Test suite name")
    parser.add_argument("--base-url", required=True, help="Base URL of the site to test")
    parser.add_argument(
        "--backend-url",
        default="https://web-production-52de4.up.railway.app",
        help="Visual regression backend URL",
    )
    parser.add_argument("--threshold", type=float, default=0.1, help="Pixel diff threshold (0.0–1.0)")
    parser.add_argument("--detect-noise", action="store_true", default=False, help="Auto-ignore animated regions")
    parser.add_argument("--pages-file", default=None, help="Path to JSON file with pages array")
    parser.add_argument("--config-file", default=None, help="Path to full JSON config file")
    parser.add_argument("--poll-interval", type=int, default=5, help="Polling interval in seconds")
    parser.add_argument("--output", default="visual-report.json", help="Output report file path")
    args = parser.parse_args()

    api_key = os.environ.get("VR_API_KEY")
    if not api_key:
        print("ERROR: VR_API_KEY environment variable not set")
        sys.exit(1)

    project_id = os.environ.get("VR_PROJECT_ID")
    if not project_id:
        print("ERROR: VR_PROJECT_ID environment variable not set")
        sys.exit(1)

    try:
        pages, suite = load_pages(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"[*] Project:    {project_id}")
    print(f"[*] Suite:      {suite}")
    print(f"[*] Pages:      {len(pages)}")
    print(f"[*] Backend:    {args.backend_url}")
    print(f"[*] Site URL:   {args.base_url}")
    print(f"[*] Threshold:  {args.threshold}")
    print(f"[*] Noise det.: {args.detect_noise}")

    report = run_tests(
        backend_url=args.backend_url,
        project_id=project_id,
        api_key=api_key,
        base_url=args.base_url,
        suite=suite,
        pages=pages,
        threshold=args.threshold,
        detect_noise=args.detect_noise,
        poll_interval=args.poll_interval,
        output_file=args.output,
    )

    status = report.get("status", "unknown")
    if status != "pass":
        print(f"\n[!] VISUAL REGRESSION FAILED: status={status}")
        results = report.get("report_data", {}).get("results", report.get("results", []))
        for r in results:
            if r.get("status") != "pass":
                print(f"    - {r.get('name')}: {r.get('status')} ({r.get('mismatch_percent', 0):.1f}% diff)")
        sys.exit(1)

    print("\n[+] VISUAL REGRESSION PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
