#!/usr/bin/env python3
"""Private, deliberate change records. Never installs, removes or runs saved text."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
import fcntl
import json
import os
import subprocess
from pathlib import Path
import tempfile
import uuid

STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "my-linux-changes"
MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 1000
FIELDS = {"title": 160, "why": 4000, "details": 6000, "backup": 2000,
          "undo": 4000, "evidence": 2000, "date": 10, "kind": 30, "status": 30}
KINDS = ["Software", "Plugin", "Setting", "Other"]
STATUSES = ["In use", "Trying it", "Needs checking", "Removed / reverted"]


def inventory():
    """Installed packages and plugin manifests only; no available-update queries."""
    with tempfile.TemporaryFile() as output:
        subprocess.run(["pacman", "-Q"], stdout=output, stderr=subprocess.DEVNULL,
                       check=True, timeout=15)
        output.seek(0)
        raw = output.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Package inventory exceeds the safety limit")
    rows = {}
    for line in raw.decode("utf-8").splitlines():
        name, version = line.split(" ", 1)
        rows["package:" + name] = {"name": name, "version": version, "kind": "Software"}
    directory = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarchy/plugins"
    if directory.exists():
        for index, path in enumerate(sorted(directory.iterdir())):
            if index >= 200:
                raise ValueError("Too many plugin folders to scan safely")
            manifest = path / "manifest.json"
            if not manifest.is_file():
                continue
            with manifest.open("rb") as stream:
                content = stream.read(65537)
            if len(content) > 65536:
                raise ValueError("Plugin manifest exceeds the safety limit")
            data = json.loads(content)
            name, version = data.get("name", path.name), data.get("version", "unknown")
            if not isinstance(name, str) or not isinstance(version, str):
                raise ValueError("Invalid plugin manifest")
            revision = ""
            if (path / ".git").exists():
                result = subprocess.run(["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
                                        capture_output=True, text=True, check=True, timeout=2)
                revision = result.stdout.strip()
            rows["plugin:" + path.name] = {"name": name, "version": version,
                                           "revision": revision, "kind": "Plugin"}
    return rows


def read_observations(directory):
    try:
        with (directory / "observed.json").open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    try:
        if len(raw) > MAX_BYTES:
            raise ValueError()
        state = json.loads(raw)
        if state.get("schemaVersion") != 1 or not isinstance(state["inventory"], dict) or not isinstance(state["events"], list):
            raise ValueError()
        datetime.fromisoformat(state["checkedAt"])
        if len(state["events"]) > MAX_ENTRIES:
            raise ValueError()
        for key, row in state["inventory"].items():
            if not isinstance(key, str) or not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("name", "version", "kind")):
                raise ValueError()
        for event in state["events"]:
            if not isinstance(event, dict) or not all(isinstance(event.get(k), str) for k in ("id", "name", "kind", "change", "before", "after", "since", "at")) or not isinstance(event.get("handled"), bool):
                raise ValueError()
        return state
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Detection history is invalid; original preserved") from None


def compare(previous, current, stamp):
    events = list(previous["events"]) if previous else []
    if previous:
        old = previous["inventory"]
        for key in sorted(old.keys() | current.keys()):
            before, after = old.get(key), current.get(key)
            if before == after:
                continue
            item = after or before
            def label(row):
                return (row["version"] + (" · " + row["revision"][:12] if row.get("revision") else "")) if row else "Not listed"
            events.append({"id": str(uuid.uuid4()), "name": item["name"], "kind": item["kind"],
                           "change": "Newly listed" if not before else "No longer listed" if not after else "Version / revision changed",
                           "before": label(before), "after": label(after), "since": previous["checkedAt"],
                           "at": stamp, "handled": False})
    # Never silently discard events waiting for an explanation.
    if len(events) > MAX_ENTRIES:
        pending = [e for e in events if not e["handled"]]
        if len(pending) > MAX_ENTRIES:
            raise ValueError("Detection queue is full; saved baseline preserved")
        remaining = MAX_ENTRIES - len(pending)
        events = ([e for e in events if e["handled"]][-remaining:] if remaining else []) + pending
    return {"schemaVersion": 1, "checkedAt": stamp, "inventory": current, "events": events,
            "baselineAt": previous.get("baselineAt", previous["checkedAt"]) if previous else stamp}


def write_observations(directory, state):
    content = encoded(state)
    if len(content) > MAX_BYTES:
        raise ValueError("Detection history exceeds the safety limit; original preserved")
    atomic(directory / "observed.json", content)


def scan(directory, force=False):
    with locked(directory):
        previous = read_observations(directory)
        if previous and not force and (datetime.now(timezone.utc) - datetime.fromisoformat(previous["checkedAt"])).total_seconds() < 300:
            return
        current = inventory()  # Any failure preserves the entire earlier snapshot.
        write_observations(directory, compare(previous, current, now()))


def handle_event(directory, identity):
    with locked(directory):
        state = read_observations(directory)
        event = next((e for e in (state or {}).get("events", []) if e["id"] == identity), None)
        if not event:
            raise ValueError("Detected change not found; refresh the list")
        event["handled"] = True
        write_observations(directory, state)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def validate(data):
    if not isinstance(data, dict) or set(data) - set(FIELDS):
        raise ValueError("Unknown record fields")
    result = {}
    for key, limit in FIELDS.items():
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > limit or "\0" in value:
            raise ValueError(f"Invalid or oversized {key} field (limit {limit} characters)")
        result[key] = value.strip()
    if not result["title"] or not result["why"]:
        raise ValueError("Add what changed and why before saving")
    if result["kind"] not in KINDS or result["status"] not in STATUSES:
        raise ValueError("Choose a valid type and status")
    try:
        parsed = date.fromisoformat(result["date"])
        if parsed.isoformat() != result["date"]:
            raise ValueError()
    except ValueError:
        raise ValueError("Use a real date in YYYY-MM-DD format") from None
    return result


def read_store(directory):
    path = directory / "records.json"
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return {"schemaVersion": 1, "entries": []}
    if len(raw) > MAX_BYTES:
        raise ValueError("Change journal exceeds the 8 MiB limit; original preserved")
    try:
        store = json.loads(raw)
        if not isinstance(store, dict) or store.get("schemaVersion") != 1:
            raise ValueError()
        rows = store["entries"]
        if not isinstance(rows, list) or len(rows) > MAX_ENTRIES:
            raise ValueError()
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(FIELDS) | {"id", "createdAt", "updatedAt"}:
                raise ValueError()
            validate({key: row[key] for key in FIELDS})
            uuid.UUID(row["id"])
            if row["id"] in seen:
                raise ValueError()
            seen.add(row["id"])
            for key in ("createdAt", "updatedAt"):
                if datetime.fromisoformat(row[key]).tzinfo is None:
                    raise ValueError()
        return store
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Change journal is invalid; original preserved. Restore a checked backup before saving.") from None


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / "write.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def atomic(path, content):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".changes-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def encoded(store):
    return (json.dumps(store, ensure_ascii=False, indent=2) + "\n").encode()


def listing(directory):
    rows = read_store(directory)["entries"]
    detection_error = ""
    try:
        observed = read_observations(directory)
    except (OSError, ValueError) as exc:
        observed = None
        detection_error = str(exc)
    return {"entries": sorted(rows, key=lambda r: (r["date"], r["createdAt"]), reverse=True),
            "storage": str(directory / "records.json"), "kinds": KINDS, "statuses": STATUSES,
            "pending": [e for e in reversed((observed or {}).get("events", [])) if not e["handled"]],
            "checkedAt": (observed or {}).get("checkedAt", ""), "baselineAt": (observed or {}).get("baselineAt", ""),
            "detectionError": detection_error}


def save(directory, payload):
    if not isinstance(payload, dict) or set(payload) - {"record", "id", "expectedUpdatedAt"}:
        raise ValueError("Invalid save request")
    record = validate(payload.get("record"))
    identity = payload.get("id", "")
    with locked(directory):
        store = read_store(directory)
        previous = encoded(store)
        rows = store["entries"]
        stamp = now()
        if identity:
            existing = next((r for r in rows if r["id"] == identity), None)
            if existing is None:
                raise ValueError("Record no longer exists; refresh before editing")
            if payload.get("expectedUpdatedAt") != existing["updatedAt"]:
                raise ValueError("This record changed elsewhere. Your draft is kept; copy it, then refresh before editing again.")
            existing.update(record, updatedAt=stamp)
        else:
            if len(rows) >= MAX_ENTRIES:
                raise ValueError("Journal is full (1,000 entries); nothing was removed")
            identity = str(uuid.uuid4())
            rows.append(dict(record, id=identity, createdAt=stamp, updatedAt=stamp))
        content = encoded(store)
        if len(content) > MAX_BYTES:
            raise ValueError("Journal would exceed 8 MiB; nothing was changed")
        if (directory / "records.json").exists():
            atomic(directory / "records.previous.json", previous)
        atomic(directory / "records.json", content)
    return {"savedId": identity, **listing(directory)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=STATE)
    parser.add_argument("command", choices=["list", "save", "export", "scan", "check", "handled"])
    parser.add_argument("value", nargs="?", default="")
    args = parser.parse_args()
    if args.command == "save":
        import sys
        payload = sys.stdin.buffer.read(40001)
        if len(payload) > 40000:
            raise ValueError("Save request exceeds 40,000 bytes")
        result = save(args.state_dir, json.loads(payload))
    elif args.command in ("scan", "check"):
        error = ""
        try:
            scan(args.state_dir, force=args.command == "scan")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            error = f"Detection unavailable; earlier snapshot kept. {exc}"
        result = listing(args.state_dir)
        if error:
            result["detectionError"] = error
    elif args.command == "handled":
        handle_event(args.state_dir, args.value)
        result = listing(args.state_dir)
    elif args.command == "export":
        result = read_store(args.state_dir)
    else:
        result = listing(args.state_dir)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(1)
