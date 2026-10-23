"""
Copy each registered project's docs into site/<slug>/ and build its sidebar.

Reads projects.json. For every entry with a docs_path it fetches the repository at
`ref` (shallow, into .cache/repos/<slug>), copies the published pages and every
non-Markdown file of docs_path into site/<slug>/, and writes the sidebars to
.vitepress/generated/projects.json for the VitePress config. Entries with a `url`
instead of a docs_path are external links and are only passed through.

Which pages are published comes from the project's docs/nav.json when it has one;
otherwise every Markdown file is, ordered by file name. Relative links that leave
the published set (../README.md, ../src/..., an unlisted page) are rewritten to the
file on GitHub at `ref`, so they work on the site and in the repository alike.

    python -I scripts/sync.py
    python -I scripts/sync.py --local qoraphase=../QoraPhase   # preview a working tree
"""

import argparse
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CACHE = ROOT / ".cache" / "repos"
GENERATED = ROOT / ".vitepress" / "generated" / "projects.json"

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_LINK = re.compile(r"(!?\[(?:[^\]\\]|\\.)*\]\()(<[^>]*>|[^)\s]+)((?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\))")
REFERENCE_LINK = re.compile(r"^( {0,3}\[[^\]]+\]:\s*)(<[^>]*>|\S+)(.*)$")
HTML_LINK = re.compile(r"(\s(?:href|src)=\")([^\"]+)(\")")
HEADING = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def warn(message: str) -> None:
    print(f"::warning::{message}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {message}", file=sys.stderr)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def remove(path: Path) -> None:
    # Git marks pack files read-only, which stops rmtree on Windows.
    def writable(func, target, _):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=writable)


def fetch(project: dict) -> Path:
    """Check out project["ref"] (branch, tag or commit) with depth 1."""
    dest = CACHE / project["slug"]
    remove(dest)
    dest.mkdir(parents=True)
    git(dest, "init", "-q")
    git(dest, "remote", "add", "origin", f"https://github.com/{project['repo']}.git")
    git(dest, "fetch", "-q", "--depth", "1", "origin", project["ref"])
    git(dest, "checkout", "-q", "FETCH_HEAD")
    return dest


def page_title(path: Path) -> str:
    match = HEADING.search(path.read_text(encoding="utf-8"))
    return match[1].strip() if match else path.stem.replace("-", " ").replace("_", " ")


def link_path(page: str) -> str:
    """docs-relative page path -> the part of the URL after /<slug>/."""
    stem = page.removesuffix(".md")
    if stem == "index":
        return ""
    return stem.removesuffix("/index") + "/" if stem.endswith("/index") else stem


def read_nav(docs: Path) -> list[dict] | None:
    nav = docs / "nav.json"
    if not nav.is_file():
        return None
    groups = json.loads(nav.read_text(encoding="utf-8"))["sidebar"]
    for group in groups:
        for item in group["items"]:
            page = item["link"].partition("#")[0]
            if not page.endswith(".md") or not (docs / page).is_file():
                raise SystemExit(f"{nav}: {item['link']} is not a Markdown file in {docs.name}/")
    return groups


def default_nav(docs: Path) -> list[dict]:
    pages = sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*.md"))
    pages.sort(key=lambda p: p != "index.md")
    return [{"text": "Pages", "items": [{"text": page_title(docs / p), "link": p} for p in pages]}]


class Rewriter:
    """Point relative links that leave the published pages at the file on GitHub."""

    def __init__(self, project: dict, checkout: Path, published: set[str]):
        self.project = project
        self.checkout = checkout
        self.docs_path = project["docs_path"].strip("/")
        self.published = published

    def github(self, repo_path: str, is_dir: bool) -> str:
        kind = "tree" if is_dir else "blob"
        return f"https://github.com/{self.project['repo']}/{kind}/{self.project['ref']}/{repo_path}"

    def target(self, page: str, raw: str) -> str:
        bracketed = raw.startswith("<") and raw.endswith(">")
        href = raw[1:-1] if bracketed else raw
        if not href or href.startswith(("#", "/")) or SCHEME.match(href):
            return raw
        path, sep, fragment = href.partition("#")
        repo_path = posixpath.normpath(posixpath.join(self.docs_path, posixpath.dirname(page), path))
        if repo_path.startswith("../"):
            warn(f"{self.project['slug']}/{page}: {href} points outside the repository")
            return raw
        local = self.checkout / repo_path
        if not local.exists():
            warn(f"{self.project['slug']}/{page}: {href} does not exist")
            return raw
        inside = repo_path.startswith(self.docs_path + "/")
        docs_rel = repo_path.removeprefix(self.docs_path + "/")
        if inside and (not docs_rel.endswith(".md") or docs_rel in self.published) and local.is_file():
            return raw
        url = self.github(repo_path, local.is_dir()) + sep + fragment
        return f"<{url}>" if bracketed else url

    def __call__(self, page: str, text: str) -> str:
        out: list[str] = []
        fence = ""
        for line in text.splitlines(keepends=True):
            if match := FENCE.match(line):
                marker = match[1]
                if not fence:
                    fence = marker
                elif marker[0] == fence[0] and len(marker) >= len(fence):
                    fence = ""
                out.append(line)
                continue
            if fence:
                out.append(line)
                continue
            line = INLINE_LINK.sub(lambda m: m[1] + self.target(page, m[2]) + m[3], line)
            line = REFERENCE_LINK.sub(lambda m: m[1] + self.target(page, m[2]) + m[3], line)
            line = HTML_LINK.sub(lambda m: m[1] + self.target(page, m[2]) + m[3], line)
            out.append(line)
        return "".join(out)


def generated_index(project: dict, groups: list[dict]) -> str:
    lines = [f"# {project['title']}", "", project["tagline"], ""]
    lines.append(
        f"Source: [{project['repo']}](https://github.com/{project['repo']}/tree/{project['ref']}/{project['docs_path']})"
    )
    lines.append("")
    for group in groups:
        for item in group["items"]:
            lines.append(f"- [{item['text']}]({item['link']})")
    return "\n".join(lines) + "\n"


def sync(project: dict, checkout: Path) -> dict:
    slug = project["slug"]
    docs = checkout / project["docs_path"]
    if not docs.is_dir():
        raise SystemExit(f"{project['repo']}@{project['ref']} has no {project['docs_path']}/")

    groups = read_nav(docs) or default_nav(docs)
    published = {item["link"].partition("#")[0] for group in groups for item in group["items"]}

    dest = SITE / slug
    remove(dest)
    dest.mkdir(parents=True)
    rewrite = Rewriter(project, checkout, published)
    for path in sorted(docs.rglob("*")):
        rel = path.relative_to(docs).as_posix()
        if (
            not path.is_file()
            or rel == "nav.json"
            or any(part.startswith(".") for part in path.parts[len(docs.parts) :])
        ):
            continue
        if rel.endswith(".md"):
            if rel not in published:
                continue
            text = rewrite(rel, path.read_text(encoding="utf-8"))
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_text(text, encoding="utf-8", newline="\n")
        else:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest / rel)

    if "index.md" not in published:
        (dest / "index.md").write_text(generated_index(project, groups), encoding="utf-8", newline="\n")

    sidebar = [
        {
            "text": group["text"],
            "items": [
                {"text": item["text"], "link": f"/{slug}/{link_path(page)}" + (f"#{anchor}" if anchor else "")}
                for item in group["items"]
                for page, _, anchor in [item["link"].partition("#")]
            ],
        }
        for group in groups
    ]
    commit = git(checkout, "rev-parse", "HEAD")
    print(f"{slug}: {len(published)} pages from {project['repo']}@{project['ref']} ({commit[:7]})")
    return {**project, "commit": commit, "checkout": checkout.as_posix(), "sidebar": sidebar}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Copy registered project docs into site/.")
    parser.add_argument(
        "--local",
        action="append",
        default=[],
        metavar="SLUG=PATH",
        help="use a local working tree instead of fetching the repository",
    )
    args = parser.parse_args(argv)
    local = {slug: Path(path).resolve() for slug, _, path in (item.partition("=") for item in args.local)}

    projects = json.loads((ROOT / "projects.json").read_text(encoding="utf-8"))
    slugs = {p["slug"] for p in projects}
    if unknown := set(local) - slugs:
        raise SystemExit(f"--local names unknown projects: {', '.join(sorted(unknown))}")

    # Every directory under site/ other than public/ is generated by this script.
    for path in SITE.iterdir():
        if path.is_dir() and path.name != "public":
            remove(path)

    out = []
    for project in projects:
        if "url" in project:
            out.append(project)
            continue
        checkout = local.get(project["slug"]) or fetch(project)
        out.append(sync(project, checkout))

    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
