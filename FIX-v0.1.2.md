# Bounded package-log reader — v0.1.2

## Report and cause

Marketplace issue #8631 identified an unbounded allocation at commit
ff3f5b2f2d619ec59af8cacd5ed8fdd8de91d2cb: status() called
parse_log(log_path.read_text(errors="replace"))[:60].
The limit of 60 applied only after loading, splitting and parsing the entire
file. Both transient strings and accumulated transaction objects grew with the
log. The shell checks status every minute and when opening the panel; news
refresh intervals do not remove that exposure.

## Fix

- Open the log read-only/nonblocking, inspect that same descriptor with fstat,
  and reject non-regular files (including FIFOs).
- Make one explicit-size pread of at most 1,048,576 bytes from the end of the
  size observed by fstat. No prefix scan, whole-file read, or unbounded readline.
  Growth after fstat cannot increase the requested read size.
- If the window starts partway through the file, discard its first line
  conservatively. The parser ignores records until a transaction-start marker.
  A transaction whose start was outside the window cannot be shown as complete.
- Discard an unterminated final line, so a partially written completion marker
  cannot mark a transaction complete.
- Reject retained lines longer than 16,384 bytes, withholding package history
  with a visible error instead of silently removing evidence inside a transaction.
- Decode and parse only the bounded window; return at most 60 transactions.
  Input bytes, split-line count and parsed-record allocations are therefore
  bounded independently of total file size.
- Show a visible warning for limited history. Evidence line labels explicitly
  say "window line" when they are not full-file line numbers.
- Preserve the existing distinction between complete and incomplete records,
  and between package updates and DKMS invocations. News and mise status remain
  available if package history is rejected.

## Trade-offs and limits

This is a recent-history view, not a complete package-log archive. A very large
transaction whose start lies outside the window is omitted; fewer than 60
transactions may be available. A first line at an exact window boundary is
also conservatively discarded. File rotation is handled by reopening each
call; the open descriptor stays attached to the file opened for that call.
This does not guarantee a coherent snapshot during concurrent in-place log
rewrites. No log files, system settings or refresh intervals are changed.

The 1 MiB limit is an input-byte bound, NOT a claim that total Python process
memory is 1 MiB. Decoded strings, parser objects and the interpreter add
overhead. This fix addresses package-log growth, not a full security audit
of every other input.

## Verification — 27 September 2026

Run from the repository root:

    python -m unittest -v
    omarchy plugin validate .
    git diff --check

All 31 tests pass (20 existing, 11 new); plugin validation and whitespace
checks pass. New regression coverage includes:

- Small-log equivalence, evidence, and post-completion DKMS records.
- An 8 GiB sparse file: exactly one read, requesting at most 1 MiB.
- A dense 1 MiB tail in an 8 GiB sparse file: 60 returned transactions and
  traced Python peak allocations below a 64 MiB regression ceiling.
- A transaction cut by the window boundary.
- An unfinished final completion line remaining incomplete.
- Oversized retained lines and newline-free huge tails.
- Latest-60 retention, empty input, invalid UTF-8 and FIFO rejection.
- Package-history rejection leaving news and mise status available.

Sparse fixtures exercise large logical file sizes without allocating 8 GiB
of disk space. The 64 MiB test is a regression guard for that fixture, not a
universal process-RSS guarantee. Existing feed-test HTTPError fixtures may
emit ResourceWarnings under Python 3.14; they do not fail the tests.

## Suggested reply (not posted automatically)

Thanks for spotting this — you were right. The 60-transaction limit was applied
after the whole log had already been loaded and parsed.

Fixed in v0.1.2: package history now reads at most the newest 1 MiB through a
single bounded read, rejects oversized retained lines, and never scans the
older prefix. Boundary-cut transactions are omitted, unfinished completion
lines do not mark transactions complete, and limited history is clearly
labelled, including window-relative evidence lines.

All 31 tests pass, including 8 GiB sparse-log fixtures, a dense-tail allocation
regression test, incomplete transactions, and oversized lines. The fix and
tests are committed and the marketplace verification request has been updated
to the corrected commit. Thank you for catching it before approval.

