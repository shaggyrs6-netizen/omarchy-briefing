# Briefing + My Linux changes — 0.2.0, 3 October 2026

My Linux changes is now a section inside Briefing. It uses the same shared
BriefingText/BriefingButton components and Omarchy Style font/spacing tokens as
the original sections. The popup keeps Briefing's original dimensions.

## Records and synchronisation

Existing records are read directly from $XDG_STATE_HOME/my-linux-changes/
(normally ~/.local/state/my-linux-changes/). No migration, renaming or copying
of the live journal is required. The bundled changes.py retains the standalone
helper's schema, locking, due-scan logic and stale-edit checks.
Refreshing/opening either interface loads records saved by the other. Unsaved
drafts remain per-panel, survive tab switches/closing, and are lost on shell restart.

The standalone widget is disabled after testing, but its source and records
remain available for rollback. Neither news settings nor read status is changed.

## Workflow

Add why / notes on a package change pre-fills a draft with its package name,
versions and log evidence, including incomplete-transaction warnings. Reasons
are left blank. Saving this draft does not automatically handle a separately
detected inventory event: exact identity between transactions and observation
intervals is not assumed. For automatic events, use Needs context and save
through Add why / details, or choose No note needed.

Detection covers installed pacman/AUR packages and user Omarchy plugin versions
and Git revisions. Checks run every five minutes while the shell runs, except
while a journal draft is open. Shared locking and due timestamps avoid duplicate
observations if the standalone widget is re-enabled.
Settings edits, loose AppImages, Flatpak and mise changes still need manual
journal entries. Briefing's existing mise display is unchanged.
Saved undo instructions are text only, never executed.

See LINUX-CHANGES.md for the inherited journal limits and local recording CLI.
That document describes the original standalone build; in Briefing, use the
My Linux changes section rather than a separate list icon.

## Verification

- 51 tests pass: Briefing, journal and shared-state/style integration contracts.
- Native ChangesView harness saved a fictional record into isolated /tmp state,
  then opened a draft from fictional package evidence. No test records in live state.
- Live combined panel loaded and was visually checked against Briefing's styling.
- The manual journal, Briefing news settings and read-state hashes remained unchanged.
- Plugin validation passes. No plugin-specific QML errors in the checked journal.
- Backups: outputs/briefing-before-merge-20261003/ in the local work project,
  including prior Panel/manifest, shell config and private journal backup.

This combined build is being published to the source repository. Marketplace submission is separate and has not been updated for 0.2.0.
The older browser preview covers updates/news only, not the new journal section.
