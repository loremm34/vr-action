# vr-action

GitHub Action for visual regression testing. Captures screenshots of your site and compares them against saved baselines — posting results as PR comments with visual diffs.

Works with **any hosting platform**: Vercel, Netlify, Render, Railway, AWS, self-hosted, or anything else.

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
  deployments: read

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

That's it. For pull requests the action automatically finds the preview deployment URL via the GitHub Deployments API, so you're always testing the actual PR changes, not production. No extra configuration needed for Vercel/Netlify/Render on standard plans.

## Inputs

| Input                   | Required | Default    | Description                                             |
| ----------------------- | -------- | ---------- | ------------------------------------------------------- |
| `api-key`               | ✅       | —          | VR API key                                              |
| `project-id`            | ✅       | —          | VR project UUID                                         |
| `site-url`              | ✅       | —          | Production URL of your site                             |
| `pages`                 | \*       | —          | JSON array of pages to test (see format below)          |
| `config-file`           | \*       | —          | Path to a JSON config file in your repo                 |
| `suite`                 |          | `website`  | Suite name for grouping runs in the dashboard           |
| `threshold`             |          | `0.1`      | Max allowed pixel diff ratio (0.0–1.0)                  |
| `detect-noise`          |          | `true`     | Auto-ignore animated regions (spinners, cursors)        |
| `auto-detect-preview`   |          | `true`     | Auto-find PR preview URL via GitHub Deployments API     |
| `preview-environment`   |          | `Preview`  | GitHub Deployment environment name to look for          |
| `preview-url`           |          | —          | Explicit preview URL (skips auto-detect, see below)     |
| `preview-bypass-secret` |          | —          | Secret token to bypass preview auth (Vercel, see below) |
| `backend-url`           |          | production | VR backend URL (no need to change)                      |

\* Either `pages` or `config-file` must be provided.

## PR preview deployments

When a pull request is opened the action needs to test the **preview version of your site** (with the PR's changes), not production. Here's how it works depending on your platform:

### Automatic detection (Vercel, Netlify, Render, Railway)

These platforms automatically register deployments to GitHub — no extra config needed. The action queries the GitHub Deployments API, waits for the preview to be ready, and uses its URL.

```yaml
- uses: loremm34/vr-action@v1
  with:
    api-key: ${{ secrets.VR_API_KEY }}
    project-id: ${{ secrets.VR_PROJECT_ID }}
    site-url: https://your-site.com # production fallback
    pages: '[{"name": "Home", "path": "/"}]'
    # auto-detect-preview: "true"   # default, no need to set
```

If your platform uses a non-default environment name (not `Preview`), set it explicitly:

```yaml
preview-environment: "staging" # or "pr-preview", "preview", etc.
```

### Vercel: bypass preview authentication

Vercel preview deployments are **publicly accessible by default** (Free plan, no protection configured). Auto-detection works out of the box — no bypass needed.

**The bypass secret is only needed if you explicitly enabled Deployment Protection** on your Vercel project (Pro/Team plans, opt-in feature). In that case, preview URLs show a "Login to Vercel" page and screenshots will be wrong without it.

To enable bypass:

1. Vercel Dashboard → your project → **Settings → Deployment Protection**
2. Enable **"Protection Bypass for Automation"** and copy the generated secret
3. Add it as a repo secret: **GitHub → Settings → Secrets → Actions → `VERCEL_BYPASS_SECRET`**

```yaml
- uses: loremm34/vr-action@v1
  with:
    api-key: ${{ secrets.VR_API_KEY }}
    project-id: ${{ secrets.VR_PROJECT_ID }}
    site-url: https://your-site.vercel.app
    preview-bypass-secret: ${{ secrets.VERCEL_BYPASS_SECRET }}
    pages: '[{"name": "Home", "path": "/"}]'
```

### Custom CI / self-hosted (AWS, custom server, etc.)

If your platform doesn't register GitHub Deployments, pass the preview URL explicitly from your own deploy step:

```yaml
jobs:
  deploy-and-test:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        id: deploy
        run: |
          # your deploy command
          echo "url=https://pr-${{ github.event.pull_request.number }}.staging.your-site.com" >> $GITHUB_OUTPUT

      - uses: loremm34/vr-action@v1
        with:
          api-key: ${{ secrets.VR_API_KEY }}
          project-id: ${{ secrets.VR_PROJECT_ID }}
          site-url: https://your-site.com
          preview-url: ${{ steps.deploy.outputs.url }}
          pages: '[{"name": "Home", "path": "/"}]'
```

### Disable preview detection entirely

If you always want to test production (e.g. push-only workflow):

```yaml
auto-detect-preview: "false"
```

## Page format

```json
[
  { "name": "Home", "path": "/" },
  { "name": "Login", "path": "/login", "wait_ms": 300, "threshold": 0.05 }
]
```

| Field       | Type   | Description                                                |
| ----------- | ------ | ---------------------------------------------------------- |
| `name`      | string | Display name shown in the dashboard and PR comment         |
| `path`      | string | URL path appended to `site-url` (or `preview-url`)         |
| `key`       | string | Unique key for baseline matching (defaults to name + path) |
| `wait_ms`   | int    | Extra wait after page load in ms (useful for animations)   |
| `threshold` | float  | Per-page threshold override                                |

## Using a config file

For larger projects, keep pages in a JSON file in your repo:

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
    { "name": "Home", "path": "/" },
    { "name": "Login", "path": "/login", "wait_ms": 200 }
  ]
}
```
