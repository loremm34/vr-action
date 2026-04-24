# vr-action

GitHub Action for visual regression testing. Captures screenshots of your site and compares them against saved baselines — posting results as PR comments with visual diffs.

## Quick start

Add to your `.github/workflows/visual-regression.yml`:

```yaml
name: Visual Regression

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  visual:
    runs-on: ubuntu-latest
    steps:
      - uses: loremm34/vr-action@v1
        with:
          api-key: ${{ secrets.VR_API_KEY }}
          project-id: ${{ secrets.VR_PROJECT_ID }}
          site-url: https://your-site.com
          pages: |
            [
              {"name": "Home",    "path": "/"},
              {"name": "About",   "path": "/about"},
              {"name": "Contact", "path": "/contact"}
            ]
```

Add two secrets to your repo (**Settings → Secrets → Actions**):
- `VR_API_KEY` — API key from the VR dashboard
- `VR_PROJECT_ID` — Project ID (UUID) from the VR dashboard

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `api-key` | ✅ | — | VR API key |
| `project-id` | ✅ | — | VR project UUID |
| `site-url` | ✅ | — | URL to test against |
| `pages` | * | — | JSON array of pages (see format below) |
| `config-file` | * | — | Path to a JSON config file in your repo |
| `suite` | | `website` | Suite name for grouping runs |
| `threshold` | | `0.1` | Max allowed diff ratio (0.0–1.0) |
| `detect-noise` | | `true` | Auto-ignore animated regions |
| `backend-url` | | production | Backend URL (no need to change) |

\* Either `pages` or `config-file` must be provided.

## Page format

```json
[
  {"name": "Home",  "path": "/"},
  {"name": "Login", "path": "/login", "wait_ms": 300, "threshold": 0.05}
]
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Display name |
| `path` | string | URL path (appended to `site-url`) |
| `key` | string | Unique key for baseline matching (defaults to name+path) |
| `wait_ms` | int | Extra wait after page load (ms) |
| `threshold` | float | Per-page threshold override |

## Using a config file

If you prefer to keep configuration in a file:

```yaml
- uses: loremm34/vr-action@v1
  with:
    api-key: ${{ secrets.VR_API_KEY }}
    project-id: ${{ secrets.VR_PROJECT_ID }}
    site-url: https://your-site.com
    config-file: tests/vr-config.json
```

`tests/vr-config.json`:
```json
{
  "suite": "website",
  "threshold": 0.1,
  "pages": [
    {"name": "Home",  "path": "/"},
    {"name": "Login", "path": "/login", "wait_ms": 200}
  ]
}
```

## PR preview URLs (Vercel / Netlify)

For PRs you typically want to test the preview deployment, not production. Add a step before the action to resolve the preview URL:

```yaml
- name: Wait for Vercel preview
  if: github.event_name == 'pull_request'
  id: preview
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    SHA="${{ github.event.pull_request.head.sha }}"
    PREVIEW_URL=""
    for i in $(seq 1 30); do
      DEPLOY_ID=$(curl -sf \
        -H "Authorization: Bearer $GH_TOKEN" \
        "https://api.github.com/repos/${{ github.repository }}/deployments?sha=$SHA&environment=Preview" \
        | python3 -c "
    import json,sys
    deps = json.load(sys.stdin)
    if deps: print(deps[0]['id'])
    " 2>/dev/null || true)
      if [ -n "$DEPLOY_ID" ]; then
        PREVIEW_URL=$(curl -sf \
          -H "Authorization: Bearer $GH_TOKEN" \
          "https://api.github.com/repos/${{ github.repository }}/deployments/$DEPLOY_ID/statuses" \
          | python3 -c "
    import json,sys
    statuses = json.load(sys.stdin)
    for s in statuses:
        if s.get('state') == 'success' and s.get('environment_url'):
            print(s['environment_url']); break
    " 2>/dev/null || true)
        if [ -n "$PREVIEW_URL" ]; then break; fi
      fi
      sleep 10
    done
    echo "url=${PREVIEW_URL:-https://your-site.com}" >> $GITHUB_OUTPUT

- uses: loremm34/vr-action@v1
  with:
    api-key: ${{ secrets.VR_API_KEY }}
    project-id: ${{ secrets.VR_PROJECT_ID }}
    site-url: ${{ github.event_name == 'pull_request' && steps.preview.outputs.url || 'https://your-site.com' }}
    pages: |
      [{"name": "Home", "path": "/"}]
```
