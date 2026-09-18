# Agents

`search_jobs.py` checks music-industry job boards and logs new postings.

Uses only the Python standard library — no install needed.

## Run it

```bash
python3 search_jobs.py            # report only NEW postings since last run
python3 search_jobs.py --show-all # ignore the seen-cache, list everything open now
```

Each run:
- pulls current openings from the companies in `companies.json` (public Greenhouse/Lever board APIs)
- optionally queries Adzuna if `config.json` has API keys (see `config.example.json`)
- filters titles using `keywords.json` (edit `include`/`exclude` to narrow results)
- writes new matches to `../Leads/results_<date>.md` and appends rows to `../Leads/tracker.md`
- remembers what it has already shown you in `.seen_jobs.json`, so re-running only surfaces new postings

## Add more companies

Company boards are verified, not guessed — a wrong token just returns nothing. To check if a company
uses Greenhouse or Lever:

```bash
curl -s "https://boards-api.greenhouse.io/v1/boards/<token>/jobs" | head -c 200   # Greenhouse
curl -s "https://api.lever.co/v0/postings/<token>?mode=json" | head -c 200        # Lever
```

The token is usually visible in the company's careers page URL (e.g. `jobs.lever.co/wmg` -> token `wmg`,
or `boards.greenhouse.io/sonymusicentertainment` -> token `sonymusicentertainment`). If either curl
returns real job data (not a 404), add an entry to `companies.json`:

```json
{ "name": "Company Name", "source": "greenhouse", "token": "companytoken" }
```

Currently verified: Sony Music Entertainment, Warner Music Group, Downtown Music Holdings, Vevo.
Most other major players (Spotify, Universal Music Group, Live Nation, SiriusXM, etc.) use
in-house or Workday career sites without a public JSON API, so they aren't easy to include here —
check those manually or add a scraper if you need them.

## Enable Adzuna (optional, broader keyword search)

1. Get free API keys at https://developer.adzuna.com/
2. `cp config.example.json config.json`
3. Fill in `app_id` and `app_key`, adjust `queries`/`location`/`country`
4. `config.json` is gitignored so your keys stay local
