"""Summarize Claude Code session logs: time span, model, tokens, human turns.

Usage: uv run python -I scripts/session_stats.py [excerpt_width] [out_file]
Reads ~/.claude/projects/*dev-digging*. Feeds docs/agent-log.md.
Prints only short prompt excerpts so pasted secrets are not echoed in full.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_-]+|OC=[^&\s]+")


def human_text(entry):
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return None
    content = entry.get("message", {}).get("content")
    if isinstance(content, list):
        if any(part.get("type") == "tool_result" for part in content if isinstance(part, dict)):
            return None
        content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text or text.startswith(("<local-command", "<command-", "<task-notification", "Caveat:")) or "[SYSTEM NOTIFICATION" in text:
        return None
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S).strip()
    return SECRET.sub("<redacted>", text) or None


SEEN_RESPONSES: set = set()
SEEN_PROMPTS: set = set()


def summarize(path):
    # Forked and resumed sessions copy earlier entries; count each response and prompt once, in the oldest file.
    first = last = None
    cwds, branches, models = Counter(), Counter(), Counter()
    usage = Counter()
    seen = SEEN_RESPONSES
    prompts = []
    sidechain_out = 0
    for line in path.open(encoding="utf-8"):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = entry.get("timestamp")
        if ts:
            first = first or ts
            last = ts
        if entry.get("cwd"):
            cwds[entry["cwd"]] += 1
        if entry.get("gitBranch"):
            branches[entry["gitBranch"]] += 1
        msg = entry.get("message") or {}
        if entry.get("type") == "assistant" and msg.get("usage"):
            # One API response is split across several entries sharing an id.
            key = msg.get("id") or entry.get("requestId")
            if key in seen:
                continue
            seen.add(key)
            models[msg.get("model")] += 1
            u = msg["usage"]
            for field in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                usage[field] += u.get(field) or 0
            if entry.get("isSidechain"):
                sidechain_out += u.get("output_tokens") or 0
        text = human_text(entry)
        if text and entry.get("uuid") not in SEEN_PROMPTS:
            SEEN_PROMPTS.add(entry.get("uuid"))
            prompts.append((ts, text))
    return {
        "file": path.parent.name.replace("C--Users-PC-Documents-Claude-", "") + "/" + path.stem[:8],
        "first": first, "last": last,
        "cwd": cwds.most_common(1)[0][0] if cwds else None,
        "branch": branches.most_common(1)[0][0] if branches else None,
        "models": dict(models), "usage": dict(usage), "sidechain_out": sidechain_out,
        "prompts": prompts,
    }


if __name__ == "__main__":
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    out = open(sys.argv[2], "w", encoding="utf-8") if len(sys.argv) > 2 else sys.stdout

    # Oldest last-entry first, so the original session keeps its entries and forks keep only what they added.
    paths = [p for d in ROOT.iterdir() if "dev-digging" in d.name for p in d.glob("*.jsonl")]
    rows = [summarize(p) for p in sorted(paths, key=lambda p: p.stat().st_mtime)]
    for r in sorted(rows, key=lambda r: r["first"] or ""):
        u = r["usage"]
        print(f"### {r['file']} {r['first']} -> {r['last']} branch={r['branch']}", file=out)
        print(f"    cwd={r['cwd']} models={r['models']}", file=out)
        print(f"    in={u.get('input_tokens',0)} out={u.get('output_tokens',0)} cache_read={u.get('cache_read_input_tokens',0)} cache_write={u.get('cache_creation_input_tokens',0)} subagent_out={r['sidechain_out']} human_turns={len(r['prompts'])}", file=out)
        for ts, text in r["prompts"]:
            print(f"    - {ts[5:16]} {text[:width].replace(chr(10), ' ')}", file=out)
