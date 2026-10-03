# My Linux changes — private prototype 0.1.0

A local Omarchy bar journal: what changed, why, where a backup is and how to undo
it. Complements Briefing's update history; it never installs, removes, restores,
or executes text from a record. No network, AI calls, telemetry or accounts.

## Use

Open the list icon in the bar. **Saved** searches your recorded explanations.
**Needs context** holds automatically observed package/plugin changes. Choose
**Add why / details** to turn an observation into a useful record, or **No note
needed** to mark it handled. **Add a change** records settings edits or anything
the detector cannot see. Records can be edited or marked Removed / reverted;
there is deliberately no destructive delete button or executable undo button.

The first scan establishes a baseline without inventing historical events.
Checks run on opening (if due) and every five minutes while the shell is running,
except while a draft is open. **Check now** forces a scan. There are no popups.

### What detection covers

- Installed pacman packages, including AUR packages registered in pacman's DB.
- User Omarchy plugin folder presence and manifest versions; Git-managed plugins
  also compare their checked-out HEAD revision. No fetch or available-update query.
- Observations show the interval between checks, NOT an exact installation time.
  Changes occurring entirely between scans cannot be recovered.

Not covered: loose AppImages, Flatpak, mise tools, edits to system/user settings,
uncommitted plugin source changes, disabled/enabled status, or reasons for changes.
An installed plugin is not necessarily enabled or working. Failed inventory reads
preserve the previous snapshot, with a visible error. Removed folders/packages
are labelled **No longer listed**, not a claim about who removed them or why.

## Local storage and limits

`$XDG_STATE_HOME/my-linux-changes/` (default `~/.local/state/my-linux-changes/`):

- `records.json`: deliberate explanations. Required title, reason, date, type, status.
- `records.previous.json`: one previous valid journal, saved before the next write.
  This is a one-save recovery copy, not a full revision archive.
- `observed.json`: installed baseline and up to 1,000 detection events. Handled
  events may be pruned at capacity; pending events are never silently dropped.
- `write.lock`: serialises writes/scans. Stale record edits are rejected.

Atomic writes, file fsync plus directory fsync, private new files (0600) and new
state directory (0700). Invalid journals are preserved, not silently reset.
Journal reads/writes are capped at 8 MiB and 1,000 records. Fields have individual
limits. No note should contain credentials. Backup paths/evidence are descriptive
text, not opened or verified. Drafts survive closing the panel but NOT shell
restart/crash. Separate panels on separate monitors can have separate drafts.

## Adding records from an AI helper or terminal

Use `python3 changes.py save` with JSON on **stdin**, not shell interpolation.
The request has `record`, optional `id` and `expectedUpdatedAt` for an edit.
All fields are strings. No arbitrary extra keys are accepted.

```json
{"record":{"title":"Example tool","why":"Try a simpler workflow","details":"Installed for a trial","date":"2026-09-30","kind":"Software","status":"Trying it","backup":"","undo":"Not checked yet","evidence":"Recorded by the user"}}
```

Types: Software, Plugin, Setting, Other.
Statuses: In use, Trying it, Needs checking, Removed / reverted.
`python3 changes.py export` prints the manual journal as JSON to stdout for a
deliberate local export; nothing is uploaded. `list` is read-only; `check` scans
if due; `scan` forces a scan. `--state-dir PATH` isolates tests/demo state.

## Development

Requires Python standard library, pacman, Git for Git-managed plugins, and the
Omarchy Quickshell runtime. Files: manifest.json, BarWidget.qml, Panel.qml,
changes.py. Install only in the user plugin directory, not /usr/share/omarchy.

```sh
python3 -m unittest -v
omarchy plugin validate .
```

Tests use temporary fictional records and mocked inventories. No package operation
or live settings change is performed. The source contains no personal journal.
This is a private local build, not a published or marketplace-verified release.
