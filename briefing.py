#!/usr/bin/env python3
"""Local update evidence + public feeds. Python standard library only.

No package operations, arbitrary commands, AI calls or inventory uploads.
Workspace previews use an explicit state directory, separate from installation.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCES = {
    "official": {"name": "Omarchy news", "label": "Official", "url": "https://omarchy.org/news/rss.xml"},
    "releases": {"name": "Omarchy releases", "label": "Official release", "url": "https://github.com/omacom/omarchy/releases.atom"},
    "discussions": {"name": "GitHub Discussions", "label": "Community discussion", "url": "https://github.com/omacom/omarchy/discussions.atom"},
    "reddit": {"name": "r/omarchy", "label": "Reddit", "url": "https://www.reddit.com/r/omarchy/new/.rss"},
}
INTERVALS = (0, 2, 6, 8, 12, 24)
DEFAULTS = {"intervalHours": 0, "enabledSources": ["official", "releases"]}
PACKAGES = {
    "omarchy": ("Omarchy", "The desktop tools and defaults that make this an Omarchy computer.", "Desktop", "https://github.com/omacom/omarchy/releases"),
    "omarchy-settings": ("Omarchy settings", "Shared system settings supplied with Omarchy.", "Desktop", "https://github.com/omacom/omarchy/releases"),
    "linux-omarchy": ("Omarchy kernel", "The core of Linux: it connects software to your computer’s hardware.", "System", "https://github.com/omacom/omarchy/releases"),
    "linux-omarchy-headers": ("Kernel build files", "Files needed to build hardware drivers for the Omarchy kernel.", "System", "https://github.com/omacom/omarchy/releases"),
    "google-chrome": ("Google Chrome", "Your web browser.", "Application", "https://chromereleases.googleblog.com/search/label/Stable%20updates"),
    "nvidia-open-dkms": ("NVIDIA graphics driver", "Lets Linux use supported NVIDIA graphics cards; rebuilt when the kernel changes.", "Hardware", "https://www.nvidia.com/en-us/drivers/unix/"),
    "nvidia-utils": ("NVIDIA support files", "Graphics libraries and tools used with the NVIDIA driver.", "Hardware", "https://www.nvidia.com/en-us/drivers/unix/"),
    "mise-bin": ("mise", "Keeps development tools such as Node.js and Python at the versions your projects need.", "Development", "https://github.com/jdx/mise/releases"),
    "cursor-bin": ("Cursor", "A code editor with AI assistance.", "Application", "https://cursor.com/changelog"),
    "archlinux-keyring": ("Arch package signing keys", "Helps check that downloaded Arch packages were signed by trusted packagers.", "System", "https://archlinux.org/packages/core/any/archlinux-keyring/"),
    "openai-codex-desktop": ("Codex", "The desktop app for working with a coding agent.", "Application", "https://developers.openai.com/codex/changelog/"),
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def timestamp(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc).isoformat(timespec="seconds")


def safe_url(value):
    try:
        p = urllib.parse.urlsplit(value.strip())
        if p.scheme == "https" and p.hostname and not p.username and not p.password:
            return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))
    except ValueError:
        pass
    return ""


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("p", "li", "br", "div", "h1", "h2", "h3"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(value, limit=360):
    parser = PlainText()
    parser.feed(value)
    text = " ".join("".join(parser.parts).split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def parse_feed(body, source):
    if len(body) > 2_000_000 or re.search(br"<!\s*(DOCTYPE|ENTITY)", body, re.I):
        raise ValueError("Feed is too large or uses unsupported XML declarations")
    root = ET.fromstring(body)
    atom = "{http://www.w3.org/2005/Atom}"
    is_atom = root.tag == atom + "feed"
    if not is_atom and root.tag != "rss":
        raise ValueError("Source did not return an RSS or Atom feed")
    entries = root.findall(atom + "entry") if is_atom else root.findall("./channel/item")
    items = []
    for entry in entries[:100]:
        if is_atom:
            links = entry.findall(atom + "link")
            url = next((link.get("href", "") for link in links if link.get("rel", "alternate") == "alternate"), "")
            title = entry.findtext(atom + "title", "")
            published = entry.findtext(atom + "published") or entry.findtext(atom + "updated")
            content = entry.findtext(atom + "summary") or entry.findtext(atom + "content", "")
        else:
            url = entry.findtext("link", "")
            title = entry.findtext("title", "")
            published = entry.findtext("pubDate")
            content = entry.findtext("description", "") or entry.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")
        url = safe_url(url)
        if not url or not title.strip():
            continue
        items.append({"id": hashlib.sha256(url.encode()).hexdigest()[:24], "url": url,
                      "title": plain(title, 200), "published": timestamp(published),
                      "excerpt": plain(content), "source": source,
                      "label": SOURCES[source]["label"]})
    return items


def read_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return fallback
    # Corruption is an error; never replace a damaged file with empty defaults.


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".briefing-", delete=False) as tmp:
        json.dump(value, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    os.replace(tmp.name, path)


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load_settings(directory):
    value = read_json(directory / "settings.json", dict(DEFAULTS))
    validate_settings(value)
    return value


def validate_settings(value):
    if type(value.get("intervalHours")) is not int or value["intervalHours"] not in INTERVALS:
        raise ValueError("Choose manual refresh, or 2, 6, 8, 12 or 24 hours")
    enabled = value.get("enabledSources")
    if not isinstance(enabled, list) or any(x not in SOURCES for x in enabled):
        raise ValueError("Unknown news source")


class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl):
            raise ValueError("Source redirected to a non-HTTPS URL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_source(key, previous):
    record = dict(previous)
    record["lastAttempt"] = now()
    headers = {"User-Agent": "OmarchyBriefing/0.1 (public feed reader)", "Accept": "application/atom+xml, application/rss+xml, application/xml"}
    for cached, header in (("etag", "If-None-Match"), ("modified", "If-Modified-Since")):
        if previous.get(cached):
            headers[header] = previous[cached]
    try:
        request = urllib.request.Request(SOURCES[key]["url"], headers=headers)
        with urllib.request.build_opener(HTTPSOnly()).open(request, timeout=15) as response:
            items = parse_feed(response.read(2_000_001), key)
            # Keep older cached headlines so a short upstream feed does not erase history.
            merged = {x["id"]: x for x in previous.get("items", [])}
            merged.update({x["id"]: x for x in items})
            record.update(items=sorted(merged.values(), key=lambda x: x["published"] or "", reverse=True)[:200],
                          etag=response.headers.get("ETag"), modified=response.headers.get("Last-Modified"),
                          lastSuccess=now(), error=None)
    except urllib.error.HTTPError as error:
        if error.code == 304 and "items" in previous:
            record.update(lastSuccess=now(), error=None)
        else:
            record["error"] = f"Source returned HTTP {error.code}; keeping saved headlines."
    except (OSError, ValueError, ET.ParseError) as error:
        record["error"] = f"Could not refresh: {str(error)[:180]}. Keeping saved headlines."
    return record


def refresh(directory, force=False):
    # Serialise fetch/save with settings and read-state changes, including other instances.
    with locked(directory):
        settings = load_settings(directory)
        cache = read_json(directory / "news.json", {})
        hours = settings["intervalHours"]
        if not force and hours == 0:
            return
        current = datetime.now(timezone.utc)
        due = []
        for key in settings["enabledSources"]:
            previous = cache.get(key, {})
            last = timestamp(previous.get("lastAttempt"))
            elapsed = (current - datetime.fromisoformat(last)).total_seconds() if last else float("inf")
            if force or elapsed >= hours * 3600:
                due.append(key)
        if due:
            with ThreadPoolExecutor(max_workers=4) as pool:
                fetched = list(pool.map(lambda key: fetch_source(key, cache.get(key, {})), due))
            cache.update(zip(due, fetched))
            write_json(directory / "news.json", cache)


def package_info(name):
    if name in PACKAGES:
        title, description, category, url = PACKAGES[name]
        return {"title": title, "description": description, "category": category, "sourceUrl": url, "descriptionKind": "Plain-English description"}
    return {"title": name, "description": "No plain-English explanation is available for this package yet.",
            "category": "Other package", "sourceUrl": "", "descriptionKind": "Unknown package"}


def parse_log(text):
    transactions, pending, current = [], None, None
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\[([^\]]+)\] \[([^\]]+)\] (.*)$", line)
        if not match:
            continue
        at, channel, message = match.groups()
        if channel == "ALPM" and message == "transaction started":
            if pending:
                transactions.append(pending)
            pending = {"id": f"{at}:{number}", "started": at, "completed": None, "status": "Incomplete record", "changes": [], "rebuilds": []}
            current = pending
        elif channel == "ALPM" and message == "transaction completed" and pending:
            pending.update(completed=at, status="Completed")
            transactions.append(pending)
            current, pending = pending, None
        elif channel == "ALPM" and pending:
            change = re.match(r"(upgraded|downgraded|installed|reinstalled|removed) ([^ ]+) \((.+)\)$", message)
            if change:
                action, name, versions = change.groups()
                parts = versions.split(" -> ", 1)
                old = parts[0] if action in ("upgraded", "downgraded", "removed", "reinstalled") else None
                new = parts[-1] if action != "removed" else None
                entry = dict(package=name, action=action, oldVersion=old, newVersion=new,
                             at=at, line=number, evidence=line, **package_info(name))
                if action in ("upgraded", "downgraded") and old.rsplit("-", 1)[0] == new.rsplit("-", 1)[0]:
                    entry["changeKind"] = "Packaging revision — upstream version unchanged"
                else:
                    entry["changeKind"] = {"installed": "Newly installed", "removed": "Removed", "reinstalled": "Same version reinstalled"}.get(action, "Software version changed")
                entry["releaseNote"] = "Version-specific release details unavailable."
                entry["actionNote"] = "Action guidance has not been checked for this update."
                pending["changes"].append(entry)
        elif channel == "ALPM-SCRIPTLET" and current:
            rebuild = re.search(r"dkms install .*?([^ /]+)/([^ ]+) -k ([^ ]+)", message)
            if rebuild:
                driver, version, kernel = rebuild.groups()
                current["rebuilds"].append({"driver": driver, "version": version, "kernel": kernel,
                                            "at": at, "line": number, "evidence": line,
                                            "description": f"{driver.upper()} {version}: driver build/install was invoked for kernel {kernel}. This is not evidence of a driver version upgrade."})
    if pending:
        transactions.append(pending)
    return [tx for tx in reversed(transactions) if tx["changes"] or tx["rebuilds"]]


def mise_inventory():
    """Ask mise for installed versions only, outside the caller's project."""
    executable = shutil.which("mise")
    if not executable:
        raise ValueError("mise is not available on the desktop's PATH")
    result = subprocess.run([executable, "ls", "--installed", "--json"],
                            cwd=Path.home(), capture_output=True, text=True, timeout=10,
                            env=dict(os.environ, MISE_COLOR="0"))
    if result.returncode:
        raise ValueError("mise could not list installed tools; saved observations retained")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected mise inventory format")
    rows = {}
    descriptions = {
        "codex": ("Codex CLI", "OpenAI’s coding agent for the terminal."),
        "node": ("Node.js", "Runs JavaScript tools and applications outside the browser."),
        "gh": ("GitHub CLI", "Works with GitHub repositories and issues from the terminal."),
        "python": ("Python", "Runs Python programs and development tools."),
    }
    for tool, versions in payload.items():
        if not isinstance(versions, list):
            raise ValueError("Unexpected mise version list")
        for item in versions:
            if not isinstance(item, dict):
                raise ValueError("Unexpected mise version record")
            # Configured or merely available versions must never become install events.
            if item.get("installed") is not True:
                continue
            version, path = item.get("version"), item.get("install_path")
            if not isinstance(version, str) or not isinstance(path, str) or not Path(path).is_dir():
                raise ValueError("mise listed an installation whose directory is unavailable; retrying later")
            title, description = descriptions.get(tool, (tool, "A development tool managed by mise."))
            key = json.dumps([tool, version, path])
            rows[key] = {"tool": tool, "version": version, "path": path,
                         "active": item.get("active") is True, "title": title,
                         "description": description}
    return rows


def observe_mise(previous, rows, at):
    """Track observed inventory differences, never reconstruct guessed upgrades."""
    baseline = previous is None
    old = previous["installed"] if previous else {}
    history = list(previous["history"]) if previous else []
    for key, row in rows.items():
        row["firstSeen"] = old.get(key, {}).get("firstSeen", at)
        row["baseline"] = old.get(key, {}).get("baseline", baseline)
        if not baseline and key not in old:
            history.append({"at": at, "title": row["title"], "version": row["version"],
                            "event": "New installed version observed", "since": previous["checkedAt"]})
        elif key in old and row["active"] != old[key]["active"]:
            history.append({"at": at, "title": row["title"], "version": row["version"],
                            "event": "Selected version changed" if row["active"] else "No longer selected",
                            "since": previous["checkedAt"]})
    for key in old.keys() - rows.keys():
        history.append({"at": at, "title": old[key]["title"], "version": old[key]["version"],
                        "event": "Installation no longer listed", "since": previous["checkedAt"]})
    return {"schemaVersion": 1, "checkedAt": at, "installed": rows, "history": history[-200:]}


def mise_status(directory):
    path = directory / "mise.json"
    saved = None
    try:
        with locked(directory):
            saved = read_json(path, None)
            if saved is not None and (not isinstance(saved, dict) or saved.get("schemaVersion") != 1
                                     or not isinstance(saved.get("installed"), dict)
                                     or not isinstance(saved.get("history"), list)
                                     or not timestamp(saved.get("checkedAt"))):
                raise ValueError("Invalid mise observation file; original preserved")
            saved = observe_mise(saved, mise_inventory(), now())
            write_json(path, saved)
        error = None
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as problem:
        error = f"mise tools: {problem}"
    valid = isinstance(saved, dict) and isinstance(saved.get("installed"), dict) and isinstance(saved.get("history"), list)
    return {"installed": sorted(saved["installed"].values(), key=lambda x: (not x["active"], x["tool"], x["version"])) if valid else [],
            "history": list(reversed(saved["history"])) if valid else [],
            "checkedAt": saved.get("checkedAt") if valid else None, "error": error}


def status(directory, log_path):
    news_errors = []
    try:
        settings = load_settings(directory)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        settings = dict(DEFAULTS)
        news_errors.append(f"Cannot read news settings: {error}. Original file preserved.")
    try:
        cache = read_json(directory / "news.json", {})
        if not isinstance(cache, dict):
            raise ValueError("Expected a news cache object")
    except (OSError, ValueError) as error:
        cache = {}
        news_errors.append(f"Cannot read news cache: {error}. Original file preserved.")
    try:
        read = set(read_json(directory / "read.json", []))
    except (OSError, ValueError, TypeError) as error:
        read = set()
        news_errors.append(f"Cannot read saved read status: {error}. Original file preserved.")
    items, seen = [], set()
    for key in settings["enabledSources"]:
        for item in cache.get(key, {}).get("items", []):
            if item["id"] not in seen:
                items.append(dict(item, read=item["id"] in read))
                seen.add(item["id"])
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    log_error = None
    try:
        transactions = parse_log(log_path.read_text(errors="replace"))[:60]
    except OSError as error:
        transactions, log_error = [], f"Cannot read package history: {error.strerror}"
    # Match exact Omarchy release tags only, never latest-release notes for an older update.
    releases = cache.get("releases", {}).get("items", [])
    for tx in transactions:
        for entry in tx["changes"]:
            if entry["package"] in ("omarchy", "omarchy-settings") and entry["newVersion"]:
                tag = "v" + entry["newVersion"].rsplit("-", 1)[0]
                note = next((x for x in releases if x["url"] == "https://github.com/omacom/omarchy/releases/tag/" + tag), None)
                if note:
                    entry["releaseNote"] = "Release announcement for " + tag + ": " + note["excerpt"]
                    entry["releaseUrl"] = note["url"]
                    entry["releaseScope"] = "Destination release only; intermediate releases and packaging changes may be omitted."
    return {"generatedAt": now(), "mise": mise_status(directory), "settings": settings, "sources": [dict(value, id=key, enabled=key in settings["enabledSources"],
            lastSuccess=cache.get(key, {}).get("lastSuccess"), lastAttempt=cache.get(key, {}).get("lastAttempt"),
            error=cache.get(key, {}).get("error")) for key, value in SOURCES.items()],
            "news": items, "newsError": " ".join(news_errors), "unread": sum(not item["read"] for item in items),
            "transactions": transactions, "logError": log_error, "logPath": str(log_path),
            "coverage": "Package history covers pacman and AUR transactions. Installed mise tools and observed changes are shown separately below. Flatpak and shell-plugin updates are not covered."}


def action(directory, log_path, payload):
    command = payload.get("action")
    if command == "refresh":
        refresh(directory, force=bool(payload.get("force", True)))
    elif command == "settings":
        value = payload.get("settings", {})
        validate_settings(value)
        with locked(directory):
            write_json(directory / "settings.json", {"intervalHours": value["intervalHours"], "enabledSources": list(dict.fromkeys(value["enabledSources"]))})
    elif command == "read":
        ids = payload.get("ids", [])
        if not isinstance(ids, list) or any(not isinstance(x, str) or not re.fullmatch(r"[a-f0-9]{24}", x) for x in ids):
            raise ValueError("Invalid story IDs")
        with locked(directory):
            read = set(read_json(directory / "read.json", []))
            if payload.get("read", True):
                read.update(ids)
            else:
                read.difference_update(ids)
            write_json(directory / "read.json", sorted(read))
    else:
        raise ValueError("Unknown action")
    return status(directory, log_path)


def serve(directory, log_path, port):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, body, content_type="application/json"):
            data = json.dumps(body, ensure_ascii=False).encode() if content_type == "application/json" else body
            self.send_response(code)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'none'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, {"error": "Invalid host"})
            try:
                if self.path == "/api/status":
                    return self.respond(200, dict(status(directory, log_path), token=token))
                files = {"/": ("preview.html", "text/html"), "/preview.js": ("preview.js", "text/javascript"), "/preview.css": ("preview.css", "text/css")}
                if self.path in files:
                    filename, mime = files[self.path]
                    return self.respond(200, (ROOT / filename).read_bytes(), mime)
                self.respond(404, {"error": "Not found"})
            except (OSError, ValueError) as error:
                self.respond(500, {"error": str(error)})

        def do_POST(self):
            if not self.allowed() or self.path != "/api/action" or self.headers.get("X-Briefing-Token") != token:
                return self.respond(403, {"error": "Invalid request"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 64000:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(length))
                self.respond(200, dict(action(directory, log_path, payload), token=token))
            except (ValueError, OSError, AttributeError, TypeError) as error:
                self.respond(400, {"error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Preview: http://127.0.0.1:{server.server_port}\nState: {directory}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "omarchy-briefing")
    parser.add_argument("--log", type=Path, default=Path("/var/log/pacman.log"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    refresh_parser = sub.add_parser("refresh")
    refresh_parser.add_argument("--due", action="store_true")
    action_parser = sub.add_parser("action")
    action_parser.add_argument("payload", help="JSON action; no shell expansion")
    preview = sub.add_parser("preview")
    preview.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "preview":
            serve(args.state_dir, args.log, args.port)
            return
        if args.command == "refresh":
            refresh(args.state_dir, force=not args.due)
        result = action(args.state_dir, args.log, json.loads(args.payload)) if args.command == "action" else status(args.state_dir, args.log)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, ET.ParseError) as error:
        print(json.dumps({"error": str(error)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
