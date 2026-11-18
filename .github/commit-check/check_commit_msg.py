#!/usr/bin/env python3
"""Check commit messages against the kleidos-dev message rules.

Rules (rule id, severity):
  subject-empty            error    the message has a subject line
  subject-max-length       error    the subject is at most 72 columns
  subject-soft-length      warning  the subject is at most 50 columns
  subject-trailing-period  error    the subject does not end with a period
  subject-imperative       error    the subject does not start with a past or
                                    third-person verb ("Added", "Fixes", ...)
  body-leading-blank       error    a blank line separates subject and body
  body-max-length          error    body lines are at most 72 columns, except
                                    the trailers at the end ("Key: value"),
                                    lines holding a URL, indented lines, lines
                                    inside a ``` or ~~~ fence, table lines
                                    ("| ..."), and a line that is one word
  attribution              error    no AI attribution (an assistant as
                                    co-author, "Generated with ...", links to
                                    agent sessions)

Merge commits are not checked. "fixup! ", "squash! " and "amend! " prefixes
are ignored when the subject is checked, and a "Revert ..." subject has no
length limit (git writes it).

Modes:
    check_commit_msg.py MSGFILE
        The commit-msg hook: check the message git is about to commit
        (comment lines and everything below the scissors line are dropped,
        as git's default cleanup does).
    check_commit_msg.py --range BASE..HEAD [--json FILE] [--pr N --head-sha SHA]
        CI: check every non-merge commit in a revision range.
    check_commit_msg.py --render RESULT.json
        Print the pull request comment for a --json result.
    check_commit_msg.py --comment RESULT.json --repo OWNER/NAME --head-sha SHA
        Create, update or delete the one sticky pull request comment
        (marker <!-- kleidos-commit-check -->) with the REST API, using
        GITHUB_TOKEN. The pull request number comes from the result and is
        trusted only when that pull request's head is SHA.

Output: one problem per line, "<commit or file>:<line>: <severity>: <rule>:
<what> -- <how to fix>". Exit status 0 when no error was found (warnings
allowed), 1 when one was, 2 when git, the input or the API failed.

Canonical copy: kleidos-dev/agents,
plugins/kleidos-common/skills/git-commits/scripts/check_commit_msg.py.
Repositories carry it at .github/commit-check/check_commit_msg.py; change it
in kleidos-dev/agents and copy it with sync_commit_check.py.
Python 3.9 or newer, standard library only.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

SUBJECT_MAX = 72
SUBJECT_SOFT = 50
BODY_MAX = 72
MARKER = "<!-- kleidos-commit-check -->"
MAX_ROWS = 50
RULES_HINT = "the git-commits skill of kleidos-dev/agents"

ERROR = "error"
WARNING = "warning"

ATTRIBUTION = [
    re.compile(r"^co-authored-by:.*\b(claude|anthropic|copilot|chatgpt|openai|gemini|cursor|assistant|bot)\b", re.I | re.M),
    re.compile(r"generated (with|by) .*\b(claude|copilot|chatgpt|ai|assistant)\b", re.I),
    re.compile("\U0001F916"),
    re.compile(r"https?://(claude\.ai|chatgpt\.com|chat\.openai\.com)/\S*(chat|session|share)", re.I),
]
NOT_IMPERATIVE = re.compile(
    r"^(added|adds|adding|fixed|fixes|fixing|updated|updates|updating|removed|removes|removing|"
    r"changed|changes|changing|implemented|implements|implementing|refactored|refactors|refactoring|"
    r"moved|moves|moving|renamed|renames|renaming|created|creates|creating|deleted|deletes|deleting|"
    r"improved|improves|improving|bumped|bumps|bumping)\b",
    re.I,
)
AUTOSQUASH = re.compile(r"^(?:(?:fixup|squash|amend)! )+")
MERGE_SUBJECT = re.compile(r"^Merge (branch|branches|remote-tracking branch|pull request|tag|commit) ")
REVERT_SUBJECT = re.compile(r'^Revert "')
FENCE = re.compile(r"^\s*(```|~~~)")
URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S")
TRAILER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*: \S")
CHERRY_PICK = re.compile(r"^\(cherry picked from commit [0-9a-f]+\)$")
SCISSORS = re.compile(r"^. -+ >8 -+$")
RULE_ID = re.compile(r"^[a-z][a-z-]{0,40}$")
HEX = re.compile(r"^[0-9a-f]{7,64}$")

HINTS = {
    "subject-empty": "write a one-line summary of the change",
    "subject-max-length": "shorten the subject to 72 columns or fewer",
    "subject-soft-length": "aim for 50 columns or fewer",
    "subject-trailing-period": "drop the final period",
    "subject-imperative": "start with an imperative verb: Add, Fix, Update, Remove",
    "body-leading-blank": "leave line 2 empty",
    "body-max-length": "wrap the body at 72 columns",
    "attribution": "remove the attribution line",
}


def problem(line, rule, severity, message):
    return {"line": line, "rule": rule, "severity": severity, "message": message, "hint": HINTS[rule]}


# --- message rules -----------------------------------------------------------
def clean_message(text, comment_char="#"):
    """The message as git's default cleanup leaves it, for the commit-msg hook."""
    lines = []
    for ln in text.replace("\r\n", "\n").split("\n"):
        if SCISSORS.match(ln) and ln.startswith(comment_char):
            break
        if ln.startswith(comment_char):
            continue
        lines.append(ln.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def trailer_start(lines):
    """Index of the first line of the trailer block at the end, or len(lines)."""
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    start = end
    while start > 0 and lines[start - 1].strip():
        start -= 1
    if start <= 1 or start == end:  # the subject paragraph is never a trailer block
        return len(lines)
    block = lines[start:end]
    seen_trailer = False
    for ln in block:
        if TRAILER.match(ln) or CHERRY_PICK.match(ln.strip()):
            seen_trailer = True
        elif ln[:1] in (" ", "\t") and seen_trailer:
            continue
        else:
            return len(lines)
    return start


def body_line_exempt(ln):
    if ln.startswith("    ") or ln.startswith("\t"):
        return True
    if URL.search(ln):
        return True
    stripped = ln.strip()
    if stripped.startswith("|"):
        return True
    if " " not in stripped and "\t" not in stripped:
        return True
    return False


def check_message(text):
    """Problems in one commit message (already cleaned), as dicts."""
    out = []
    lines = text.replace("\r\n", "\n").split("\n")
    subject = lines[0] if lines else ""
    if not subject.strip():
        return [problem(1, "subject-empty", ERROR, "the subject line is empty")]
    if MERGE_SUBJECT.match(subject):
        return []
    core = AUTOSQUASH.sub("", subject)
    width = len(core)  # autosquash folds a fixup! commit into its target
    if not REVERT_SUBJECT.match(core):
        if width > SUBJECT_MAX:
            out.append(problem(1, "subject-max-length", ERROR, "the subject is %d columns; the limit is %d" % (width, SUBJECT_MAX)))
        elif width > SUBJECT_SOFT:
            out.append(problem(1, "subject-soft-length", WARNING, "the subject is %d columns" % width))
    if core.rstrip().endswith(".") and not core.rstrip().endswith("..."):
        out.append(problem(1, "subject-trailing-period", ERROR, "the subject ends with a period"))
    m = NOT_IMPERATIVE.match(core)
    if m:
        out.append(problem(1, "subject-imperative", ERROR, "the subject starts with %r, not an imperative" % m.group(1)))
    if len(lines) > 1 and lines[1].strip():
        out.append(problem(2, "body-leading-blank", ERROR, "line 2 is not blank"))
    stop = trailer_start(lines)
    in_fence = False
    for idx in range(1, stop):
        ln = lines[idx]
        if FENCE.match(ln):
            in_fence = not in_fence
            continue
        if in_fence or len(ln) <= BODY_MAX or body_line_exempt(ln):
            continue
        out.append(problem(idx + 1, "body-max-length", ERROR, "line is %d columns; the limit is %d" % (len(ln), BODY_MAX)))
    hits = [m.start() for m in (pat.search(text) for pat in ATTRIBUTION) if m]
    if hits:
        num = text.count("\n", 0, min(hits)) + 1
        out.append(problem(num, "attribution", ERROR, "attribution line in the message"))
    return out


def format_problem(ref, p):
    return "%s:%d: %s: %s: %s -- %s" % (ref, p["line"], p["severity"], p["rule"], p["message"], p["hint"])


# --- git ---------------------------------------------------------------------
SEP = "\x1f"
END = "\x1e"


def git(args, cwd=None):
    proc = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git %s failed" % " ".join(args))
    return proc.stdout


def comment_char(cwd=None):
    try:
        value = git(["config", "core.commentChar"], cwd).strip()
    except RuntimeError:
        return "#"
    return value if value and value != "auto" else "#"


def read_range(rev, cwd=None):
    out = git(["log", "--reverse", "--format=%H" + SEP + "%P" + SEP + "%B" + END, rev], cwd)
    commits = []
    for chunk in out.split(END):
        chunk = chunk.lstrip("\n")
        if not chunk:
            continue
        sha, parents, body = chunk.split(SEP, 2)
        commits.append({"sha": sha, "parents": parents.split(), "message": body.rstrip("\n")})
    return commits


def check_range(rev, cwd=None):
    result = {"range": rev, "checked": 0, "skipped_merges": 0, "errors": 0, "warnings": 0, "commits": []}
    for c in read_range(rev, cwd):
        if len(c["parents"]) > 1:
            result["skipped_merges"] += 1
            continue
        result["checked"] += 1
        probs = check_message(c["message"])
        if not probs:
            continue
        result["commits"].append({
            "sha": c["sha"],
            "subject": c["message"].split("\n", 1)[0],
            "problems": probs,
        })
        result["errors"] += sum(1 for p in probs if p["severity"] == ERROR)
        result["warnings"] += sum(1 for p in probs if p["severity"] == WARNING)
    return result


# --- the pull request comment -----------------------------------------------
def plain(text, limit=160):
    """Untrusted text made safe for one Markdown table cell: no HTML, no
    mentions, no links, no table breaks, no line breaks."""
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("\\", "\\\\").replace("|", "\\|").replace("`", "'")
    text = text.replace("[", "\\[").replace("]", "\\]").replace("://", ":\\/\\/")
    text = text.replace("@", "@​")
    return text


def code_cell(text, limit=60):
    """Untrusted text as a code span in a table cell (no mention, no HTML)."""
    text = " ".join(str(text).split()).replace("`", "'")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return "`%s`" % text.replace("|", "\\|") if text else ""


def sentence(text):
    return text[:1].upper() + text[1:]


def valid_result(result):
    """Reject a result that is not the shape the checker writes."""
    if not isinstance(result, dict) or not isinstance(result.get("commits"), list):
        raise ValueError("the result is not a check_commit_msg.py --json result")
    for key in ("errors", "warnings", "checked"):
        if not isinstance(result.get(key, 0), int):
            raise ValueError("%s is not a number" % key)
    for c in result["commits"]:
        if not isinstance(c, dict) or not HEX.match(str(c.get("sha", ""))) or not isinstance(c.get("problems"), list):
            raise ValueError("a commit entry is malformed")
        for p in c["problems"]:
            if not isinstance(p, dict) or not isinstance(p.get("line"), int) or not RULE_ID.match(str(p.get("rule", ""))):
                raise ValueError("a problem entry is malformed")
            if p.get("severity") not in (ERROR, WARNING):
                raise ValueError("a problem entry has an unknown severity")
    return result


def render_failure(result):
    rows = []
    for c in result["commits"]:
        for p in c["problems"]:
            if p["severity"] != ERROR:
                continue  # warnings stay in the job log
            fix = HINTS.get(p["rule"], "see the job log")  # never the artifact's own text
            rows.append("| `%s` | %s | %d | `%s` | %s. %s. |" % (
                c["sha"][:7], code_cell(c.get("subject", "")), p["line"], p["rule"], sentence(plain(p.get("message", ""))), sentence(plain(fix))))
    shown = rows[:MAX_ROWS]
    more = len(rows) - len(shown)
    n_err = result.get("errors", 0)
    n_commits = sum(1 for c in result["commits"] if any(p["severity"] == ERROR for p in c["problems"]))
    parts = [
        MARKER,
        "### Commit messages: %d problem%s in %d commit%s" % (n_err, "" if n_err == 1 else "s", n_commits, "" if n_commits == 1 else "s"),
        "",
        "Some commits in this pull request do not follow the organization's commit-message rules. Each row names the commit, the line of its message (line 1 is the subject), the rule and the fix.",
        "",
        "| Commit | Subject | Line | Rule | Fix |",
        "| --- | --- | --- | --- | --- |",
    ] + shown
    if more:
        parts.append("")
        parts.append("And %d more; the job log of the commit-check workflow lists every one." % more)
    parts += [
        "",
        "**The rules.** Subject at most 72 columns (aim for 50), imperative (`Add`, `Fix`, not `Added` or `Fixes`), no final period, then a blank line. Body lines at most 72 columns, except trailers at the end (`Key: value`), lines with a URL, indented or fenced code, and table lines. No AI attribution lines. Markdown files and the pull request description stay one line per paragraph; only commit messages are wrapped.",
        "",
        "**How to fix.** For the last commit, run `git commit --amend` and edit the message. For older ones, run `git rebase -i <base>`, change `pick` to `reword` on each commit listed above, and edit each message when git opens it. Then update the branch with `git push --force-with-lease`. Force-pushing a pull request branch is normal; only `main` is protected. This comment updates itself on the next run.",
    ]
    return "\n".join(parts) + "\n"


def render_resolved(result):
    head = str(result.get("head_sha", ""))
    at = " (checked at `%s`)" % head[:7] if HEX.match(head) else ""
    return "\n".join([
        MARKER,
        "### Commit messages: all pass",
        "",
        "The problems this check reported earlier are fixed: every commit in this pull request now follows the commit-message rules%s." % at,
    ]) + "\n"


def render(result):
    """The comment body for a result: the failure table, or the resolved note."""
    return render_failure(result) if result.get("errors", 0) else render_resolved(result)


def decide(existing_body, result, resolved="update"):
    """What to do with the sticky comment: ('create'|'update'|'delete'|'none', body)."""
    failed = bool(result.get("errors", 0))
    if failed:
        body = render_failure(result)
        if existing_body is None:
            return "create", body
        return ("none", body) if existing_body == body else ("update", body)
    if existing_body is None:
        return "none", None
    if resolved == "delete":
        return "delete", None
    body = render_resolved(result)
    return ("none", body) if existing_body == body else ("update", body)


class GitHub:
    """The few REST calls the sticky comment needs (standard library only)."""

    def __init__(self, token, api_url="https://api.github.com"):
        self.token = token
        self.api_url = api_url.rstrip("/")

    def request(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.api_url + path, data=data, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "kleidos-commit-check")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8")) if raw else None


def find_comment(api, repo, number, bot_login):
    """(id, body) of the sticky comment the bot wrote, or (None, None)."""
    page = 1
    while True:
        batch = api.request("GET", "/repos/%s/issues/%d/comments?per_page=100&page=%d" % (repo, number, page)) or []
        for c in batch:
            if (c.get("user") or {}).get("login") == bot_login and MARKER in (c.get("body") or ""):
                return c["id"], c["body"]
        if len(batch) < 100:
            return None, None
        page += 1


def sync_comment(api, repo, result, head_sha, resolved="update", bot_login="github-actions[bot]", log=print):
    """Bring the sticky comment in line with result. Returns the action taken."""
    number = result.get("pr")
    if not isinstance(number, int) or number <= 0:
        raise ValueError("the result names no pull request")
    pr = api.request("GET", "/repos/%s/pulls/%d" % (repo, number)) or {}
    if (pr.get("head") or {}).get("sha") != head_sha or result.get("head_sha") != head_sha:
        log("pull request #%d has moved past %s or does not hold it; leaving the comment alone" % (number, head_sha[:12]))
        return "stale"
    comment_id, body = find_comment(api, repo, number, bot_login)
    action, new_body = decide(body, result, resolved)
    if action == "create":
        api.request("POST", "/repos/%s/issues/%d/comments" % (repo, number), {"body": new_body})
    elif action == "update":
        api.request("PATCH", "/repos/%s/issues/comments/%d" % (repo, comment_id), {"body": new_body})
    elif action == "delete":
        api.request("DELETE", "/repos/%s/issues/comments/%d" % (repo, comment_id))
    log("pull request #%d: %s the commit-check comment" % (number, {"create": "created", "update": "updated", "delete": "deleted", "none": "kept"}[action]))
    return action


# --- command line ------------------------------------------------------------
def load_result(path):
    with open(path, encoding="utf-8") as fh:
        return valid_result(json.load(fh))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("msgfile", nargs="?", help="commit message file (commit-msg hook mode)")
    ap.add_argument("--range", dest="rev", help="check every non-merge commit in this revision range")
    ap.add_argument("--json", dest="json_out", help="with --range: also write the result as JSON to this file ('-' for stdout)")
    ap.add_argument("--pr", type=int, help="with --range: the pull request number to record in the JSON")
    ap.add_argument("--head-sha", help="with --range: the head commit to record; with --comment: the head the result must match")
    ap.add_argument("--render", metavar="RESULT", help="print the pull request comment for a --json result")
    ap.add_argument("--comment", metavar="RESULT", help="create, update or delete the sticky comment for a --json result")
    ap.add_argument("--repo", help="with --comment: OWNER/NAME")
    ap.add_argument("--resolved", choices=["update", "delete"], default="update", help="with --comment: what to do with the comment once every commit passes (default: update)")
    ap.add_argument("--bot-login", default="github-actions[bot]", help="with --comment: the login whose comment is the sticky one")
    ap.add_argument("-C", dest="cwd", help="repository (default: current directory)")
    args = ap.parse_args(argv)

    modes = [m for m in (args.msgfile, args.rev, args.render, args.comment) if m]
    if len(modes) != 1:
        ap.error("give exactly one of MSGFILE, --range, --render or --comment")

    if args.render:
        try:
            sys.stdout.write(render(load_result(args.render)))
        except (OSError, ValueError) as exc:
            print("check_commit_msg: %s" % exc, file=sys.stderr)
            return 2
        return 0

    if args.comment:
        token = os.environ.get("GITHUB_TOKEN")
        if not (token and args.repo and args.head_sha):
            ap.error("--comment needs --repo, --head-sha and GITHUB_TOKEN in the environment")
        try:
            result = load_result(args.comment)
            api = GitHub(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))
            sync_comment(api, args.repo, result, args.head_sha, args.resolved, args.bot_login)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            print("check_commit_msg: %s" % exc, file=sys.stderr)
            return 2
        return 0

    if args.msgfile:
        try:
            with open(args.msgfile, encoding="utf-8") as fh:
                text = clean_message(fh.read(), comment_char(args.cwd))
        except OSError as exc:
            print("check_commit_msg: %s" % exc, file=sys.stderr)
            return 2
        if not text:
            return 0  # git aborts an empty message on its own
        probs = check_message(text)
        for p in probs:
            print(format_problem(args.msgfile, p))
        if any(p["severity"] == ERROR for p in probs):
            sys.stdout.flush()
            print("The rules are in %s. Your message is kept; reopen it with: git commit -e -F %s" % (RULES_HINT, args.msgfile), file=sys.stderr)
            return 1
        return 0

    try:
        result = check_range(args.rev, args.cwd)
    except RuntimeError as exc:
        print("git: %s" % exc, file=sys.stderr)
        return 2
    if args.pr is not None:
        result["pr"] = args.pr
    if args.head_sha:
        result["head_sha"] = args.head_sha
    stream = sys.stderr if args.json_out == "-" else sys.stdout
    for c in result["commits"]:
        for p in c["problems"]:
            print(format_problem(c["sha"][:12], p), file=stream)
    print("%d commit(s) checked, %d merge(s) skipped, %d error(s), %d warning(s)" % (
        result["checked"], result["skipped_merges"], result["errors"], result["warnings"]), file=sys.stderr)
    if args.json_out:
        data = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.json_out == "-":
            sys.stdout.write(data)
        else:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                fh.write(data)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
