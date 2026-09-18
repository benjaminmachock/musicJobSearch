#!/usr/bin/env python3
"""Search music-industry job boards and log new postings to Leads/.

Sources:
  - Greenhouse / Lever public job-board APIs for companies listed in companies.json
  - Adzuna keyword search (optional, needs free API keys in config.json)

Usage:
  python3 search_jobs.py                 # fetch, report only NEW postings since last run
  python3 search_jobs.py --show-all      # ignore the seen-cache, report everything open now
  python3 search_jobs.py --no-adzuna     # skip Adzuna even if configured
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = AGENTS_DIR.parent
LEADS_DIR = PROJECT_DIR / "Leads"
STATE_FILE = AGENTS_DIR / ".seen_jobs.json"
COMPANIES_FILE = AGENTS_DIR / "companies.json"
KEYWORDS_FILE = AGENTS_DIR / "keywords.json"
CONFIG_FILE = AGENTS_DIR / "config.json"

USER_AGENT = "musicJobSearch-agent/1.0 (personal job search tool)"


def fetch_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_greenhouse(company_name, token):
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    data = fetch_json(url)
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "id": f"greenhouse:{token}:{j['id']}",
            "company": company_name,
            "title": j.get("title", "").strip(),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "source": "Greenhouse",
        })
    return jobs


def fetch_lever(company_name, token):
    url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    data = fetch_json(url)
    jobs = []
    for j in data:
        categories = j.get("categories") or {}
        jobs.append({
            "id": f"lever:{token}:{j['id']}",
            "company": company_name,
            "title": j.get("text", "").strip(),
            "location": categories.get("location", ""),
            "url": j.get("hostedUrl", ""),
            "source": "Lever",
        })
    return jobs


def fetch_adzuna(cfg):
    app_id = cfg.get("app_id", "")
    app_key = cfg.get("app_key", "")
    if not app_id or not app_key:
        return []
    country = cfg.get("country", "us")
    location = cfg.get("location", "")
    queries = cfg.get("queries", [])
    jobs = {}
    for q in queries:
        params = f"app_id={app_id}&app_key={app_key}&what={urllib.parse.quote(q)}&results_per_page=50"
        if location:
            params += f"&where={urllib.parse.quote(location)}"
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?{params}"
        try:
            data = fetch_json(url)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"  [warn] Adzuna query '{q}' failed: {e}", file=sys.stderr)
            continue
        for r in data.get("results", []):
            jid = f"adzuna:{r.get('id')}"
            jobs[jid] = {
                "id": jid,
                "company": (r.get("company") or {}).get("display_name", "Unknown"),
                "title": (r.get("title") or "").strip(),
                "location": (r.get("location") or {}).get("display_name", ""),
                "url": r.get("redirect_url", ""),
                "source": "Adzuna",
            }
    return list(jobs.values())


def load_json(path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def title_matches(title, include, exclude):
    t = title.lower()
    if any(x.lower() in t for x in exclude):
        return False
    if include and not any(x.lower() in t for x in include):
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--show-all", action="store_true", help="ignore seen-cache, list every open role")
    parser.add_argument("--no-adzuna", action="store_true", help="skip Adzuna even if config.json has keys")
    args = parser.parse_args()

    companies = load_json(COMPANIES_FILE, [])
    keywords = load_json(KEYWORDS_FILE, {"include": [], "exclude": []})
    config = load_json(CONFIG_FILE, {})
    seen = set(load_json(STATE_FILE, []))

    all_jobs = []

    print(f"Checking {len(companies)} company board(s)...")
    for c in companies:
        name, source, token = c["name"], c["source"], c["token"]
        try:
            if source == "greenhouse":
                jobs = fetch_greenhouse(name, token)
            elif source == "lever":
                jobs = fetch_lever(name, token)
            else:
                print(f"  [warn] unknown source '{source}' for {name}", file=sys.stderr)
                continue
            jobs = [j for j in jobs if title_matches(j["title"], keywords.get("include", []), keywords.get("exclude", []))]
            print(f"  - {name}: {len(jobs)} matching role(s)")
            all_jobs.extend(jobs)
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError) as e:
            print(f"  [warn] {name} fetch failed: {e}", file=sys.stderr)

    if not args.no_adzuna and config.get("adzuna"):
        print("Checking Adzuna...")
        adzuna_jobs = fetch_adzuna(config["adzuna"])
        adzuna_jobs = [j for j in adzuna_jobs if title_matches(j["title"], keywords.get("include", []), keywords.get("exclude", []))]
        print(f"  - Adzuna: {len(adzuna_jobs)} matching role(s)")
        all_jobs.extend(adzuna_jobs)

    if args.show_all:
        new_jobs = all_jobs
    else:
        new_jobs = [j for j in all_jobs if j["id"] not in seen]

    new_jobs.sort(key=lambda j: (j["company"], j["title"]))

    if not new_jobs:
        print("\nNo new postings found.")
    else:
        print(f"\n{len(new_jobs)} new posting(s):\n")
        for j in new_jobs:
            print(f"  [{j['company']}] {j['title']} ({j['location']}) - {j['url']}")

        LEADS_DIR.mkdir(exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report_path = LEADS_DIR / f"results_{today}.md"
        with open(report_path, "a") as f:
            f.write(f"\n## Run at {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z\n\n")
            f.write("| Company | Role | Location | Source | Link |\n")
            f.write("|---|---|---|---|---|\n")
            for j in new_jobs:
                f.write(f"| {j['company']} | {j['title']} | {j['location']} | {j['source']} | [link]({j['url']}) |\n")
        print(f"\nWrote report: {report_path.relative_to(PROJECT_DIR)}")

        tracker_path = LEADS_DIR / "tracker.md"
        if tracker_path.exists():
            with open(tracker_path, "a") as f:
                for j in new_jobs:
                    f.write(f"| {j['company']} | {j['title']} | {j['location']} | {j['source']} | New | | |\n")
            print(f"Appended {len(new_jobs)} row(s) to {tracker_path.relative_to(PROJECT_DIR)}")

    if not args.show_all:
        seen.update(j["id"] for j in all_jobs)
        with open(STATE_FILE, "w") as f:
            json.dump(sorted(seen), f, indent=2)


if __name__ == "__main__":
    main()
