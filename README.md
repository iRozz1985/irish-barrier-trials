# Barrier Trial Watch

A small site that lists any horse from the **ITM Barrier Trials (Leopardstown,
26 August)** that is declared to run under rules today, with its trial batch,
finishing position, course, time and current price.

It rebuilds **first thing each morning** on GitHub's servers and publishes the
result to GitHub Pages, so you just open a URL — nothing to run yourself.

## How it works

| Piece | What it does |
|-------|--------------|
| `build_barrier_page.py` | Scans today's UK + Irish racecards via the Ladbrokes feed, matches runners against the trial list, and writes `index.html`. |
| `barrier_trial_horses.csv` | The trial horses (columns: batch, position, horse). Edit this to change the watch list. |
| `lads_client.py` | Ladbrokes API client. Reads the key from the `LADS_API_KEY` environment variable. |
| `.github/workflows/update-barrier.yml` | Runs the builder every morning (05:30 UTC) and commits the page. |

The Ladbrokes API needs a private key, so this tool can't run purely in a
browser (the key would be exposed, and the browser can't call that API
directly). Instead, the key is stored as an encrypted **GitHub Secret** and
only used by the morning build job on GitHub's servers. It is never committed.

## One-time setup

### 1. Create the repo and upload these files
Create a new repository and upload everything in this folder, **including the
hidden `.github` folder** (enable "hidden items" in File Explorer so you can see
it, or create the workflow file directly in GitHub's web editor).

### 2. Add your Ladbrokes API key as a secret
This is the important bit — the tool won't work without it.
1. In the repo, go to **Settings &rarr; Secrets and variables &rarr; Actions**.
2. Click **New repository secret**.
3. Name: `LADS_API_KEY`
4. Value: your Ladbrokes API key.
5. **Add secret**.

### 3. Enable GitHub Pages
1. **Settings &rarr; Pages**.
2. Source: **Deploy from a branch**, branch **main**, folder **/ (root)**, **Save**.
3. The live URL appears after a minute: `https://<username>.github.io/<repo>/`.

### 4. Build the first page
The page only appears after the builder has run once.
1. Go to the **Actions** tab.
2. Pick **Update barrier-trial page**, click **Run workflow**.
3. When it finishes (green tick), reload your Pages URL.

After that it rebuilds automatically every morning.

## Changing the watch list

Edit `barrier_trial_horses.csv` (batch, position, horse) and commit. The next
build uses the new list. Matching is by exact horse name (case and punctuation
are ignored), so a renamed horse won't be caught.

## Running locally (optional)

```bash
pip install -r requirements.txt
set LADS_API_KEY=your_key_here      # Windows:  $env:LADS_API_KEY on PowerShell
python build_barrier_page.py --day today
```

Then open `index.html`. Use `--day tomorrow`, `--day all`, or `--day YYYY-MM-DD`
to look further ahead.

## Note

The trial list is a point-in-time set from one meeting. As those horses stop
racing it naturally goes quiet; that's expected.
