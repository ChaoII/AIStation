"""把 `git diff <file>` 里**含指定关键字的 hunk** 单独 stage（不动同文件里的其它 WIP）。

用法::

    python scripts/stage_hunks.py <file> <keyword> [<keyword> ...]

原理：解析 `git diff -- <file>`，只保留正文含关键字的 hunk（连同文件头），
再用 `git apply --cached --recount` 应用到索引——**工作区不动**。
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile

HUNK_RE = re.compile(r"^@@ ")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    path, keywords = sys.argv[1], sys.argv[2:]

    diff = subprocess.run(
        ["git", "diff", "--", path], capture_output=True, text=True, encoding="utf-8"
    ).stdout
    if not diff.strip():
        print(f"no diff for {path}")
        return 1

    lines = diff.splitlines(keepends=True)
    header: list[str] = []
    hunks: list[list[str]] = []
    cur: list[str] | None = None
    for ln in lines:
        if HUNK_RE.match(ln):
            cur = [ln]
            hunks.append(cur)
        elif cur is None:
            header.append(ln)
        else:
            cur.append(ln)

    kept = [h for h in hunks if any(k in "".join(h) for k in keywords)]
    if not kept:
        print("no matching hunk")
        return 1
    print(f"{len(hunks)} hunk(s) total, keeping {len(kept)}")

    patch = "".join(header) + "".join("".join(h) for h in kept)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".patch", delete=False, encoding="utf-8", newline=""
    ) as f:
        f.write(patch)
        tmp = f.name

    r = subprocess.run(
        ["git", "apply", "--cached", "--recount", tmp],
        capture_output=True, text=True, encoding="utf-8",
    )
    print(r.stdout.strip() or r.stderr.strip() or "apply ok")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
