# Omarchy Briefing

**Updates explained. News in one place.**

![Omarchy Briefing promotional thumbnail](preview.png)

A small Omarchy bar plugin for understanding completed package updates and catching up with Omarchy news. Click the newspaper icon to open it. A dot indicates unread news; hover to see the count.

The image above is promotional artwork, not a screenshot. The actual panel follows your Omarchy theme.

## Updates explained

- Shows recorded package transactions with exact old and new versions.
- Gives plain-English descriptions for a small selection of common packages. Unknown packages are labelled honestly.
- Separates installs, upgrades, downgrades, reinstalls and packaging revisions.
- Shows DKMS driver build/install invocations separately from driver version upgrades.
- Links matching Omarchy release announcements from the cached official release feed. Refresh news to populate this cache.
- Lets you expand the original log evidence. Incomplete transactions are explicitly flagged.

This is an explainer. It does not install, remove, roll back or upgrade software.

### mise-managed tools (0.1.1)

Codex CLI, Node.js and other installed mise tools appear separately from pacman packages. Selected versions in the home configuration are shown first; older installed versions can be expanded in the native panel. Briefing runs `mise ls --installed --json` from the home directory, with a ten-second timeout, and checks that returned installation directories exist. It never runs mise install/update commands or queries available versions.

The first check establishes a baseline. Existing installations are labelled as discovered; no previous-version or installation-time history is guessed. Subsequent differences record newly observed installed versions, selection changes and installations no longer listed, with the interval between observations. Events entirely between checks cannot be recovered. A failure retains the previous snapshot and displays a stale-data warning. Observations are stored locally in `mise.json` and do not depend on the news refresh interval.

## Omarchy news

- Official Omarchy news and GitHub releases enabled by default.
- Optional GitHub Discussions and r/omarchy feeds, clearly labelled as community sources.
- Manual refresh, or checks every 2, 6, 8, 12 or 24 hours.
- Official-only and unread-only filters.
- Mark individual stories read/unread, mark shown stories read, or mark all stories from enabled sources read.
- Local cache and persistent read state. Failed refreshes retain saved headlines and show an error.

Extracts are text from the source, not AI summaries. No API key, AI service or paid subscription is required. Notifications are off; this version does not send desktop notifications.

## Requirements

- Omarchy 4.x with its Quickshell desktop shell and plugin CLI.
- Python 3 (standard library only).
- mise on the desktop shell's PATH for mise-tool observations; package history and news remain available if mise is missing.
- Read access to `/var/log/pacman.log` for package history.
- HTTPS access for fetching news. Saved headlines remain readable offline.

## Install

```sh
omarchy plugin add https://github.com/shaggyrs6-netizen/omarchy-briefing --enable
omarchy bar move shaggyrs6.briefing --section right --index 0
```

Open the newspaper icon, select **Omarchy News**, and choose **Refresh news**. Configure sources and the refresh interval under **Settings**. Refresh is manual by default. Automatic checks run only while the desktop shell is running and do not wake a sleeping computer.

Open or close through the shell:

```sh
omarchy-shell shell summon shaggyrs6.briefing '{}'
omarchy-shell shell hide shaggyrs6.briefing
```

## Update

```sh
omarchy plugin update shaggyrs6.briefing
```

Review the changes when prompted. If the old interface remains cached after an update, run `omarchy restart shell`.

## Disable or remove

Hide the plugin while preserving its installation and history:

```sh
omarchy plugin disable shaggyrs6.briefing
```

Remove through Omarchy's normal plugin command:

```sh
omarchy plugin remove shaggyrs6.briefing
```

Cached headlines, preferences and read status remain in `$XDG_STATE_HOME/omarchy-briefing` (normally `~/.local/state/omarchy-briefing`). You may remove that specific directory separately if you want to discard those records. Uninstallation does not restore an old whole-shell configuration over later changes.

## Files, permissions and network access

The plugin reads `/var/log/pacman.log` and installed-tool metadata through mise. It writes only its own state directory: `settings.json`, `news.json`, `read.json`, `mise.json` and a lock file. Writes are atomic and serialised. Its Python helper runs without elevated privileges. Installation and bar placement use Omarchy's explicit CLI commands; the plugin itself does not rewrite your shell configuration.

Enabled news sources are fetched directly over HTTPS:

- `https://omarchy.org/news/rss.xml`
- `https://github.com/omacom/omarchy/releases.atom`
- `https://github.com/omacom/omarchy/discussions.atom`
- `https://www.reddit.com/r/omarchy/new/.rss`

Requests carry normal connection metadata such as your IP address and the reader's user agent. Package inventories and logs are never uploaded. Feed content is rendered as plain text; original links open in your browser when selected. Feed text cannot execute commands. There are no arbitrary user-supplied feed URLs, credentials, analytics or AI calls.

The optional development HTTP preview is not used by the native plugin. Run `python3 briefing.py --state-dir .preview-state preview` from this repository to open a separate local review surface at `http://127.0.0.1:8765`. Stop it with Ctrl+C. No local server or background service is installed automatically.

## Scope and limitations

- Package history covers the latest 60 transactions in the current pacman log, including AUR packages installed through pacman. It does not import rotated logs, pre-existing mise update history, Flatpak changes or shell-plugin updates. mise inventory observations are retained separately, with the latest 200 events saved and 20 displayed.
- Several pacman transactions may belong to one Omarchy update. The interface groups by date without claiming to know session boundaries.
- A completed transaction does not prove all subsequent hooks succeeded. A DKMS invocation does not prove its build succeeded.
- Version-specific release details currently match Omarchy destination tags only. Intermediate releases and packaging changes may be omitted. Other package links are explicitly unmatched, and unavailable release details are stated.
- Documented manual-action guidance is not yet checked. The plugin does not claim no action is needed or that a particular fault is fixed.
- At most 200 headlines are retained per source. Exact URL duplicates share read status; separate posts about the same story are not merged by meaning.
- News-source availability and rate limits are outside the plugin's control. Failures retain the previous cache.

The author reported five days of personal use without issues before preparing this release. That is practical experience on one installation, not a claim of compatibility with every system.

## Development checks

```sh
python3 -m unittest -v
omarchy plugin validate .
```

Tests cover transaction classification, interrupted records, feed parsing, HTTP failures and unchanged responses, read persistence, refresh timing, release matching and independent news/history errors.

## Licence and artwork

MIT © 2026 Lee Shand. See [LICENSE](LICENSE). The promotional thumbnail was created using AI image generation for this project. The newspaper icon in the running plugin is drawn with native QML shapes and follows your theme.
