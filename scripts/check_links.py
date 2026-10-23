"""
Fail when a page of the built site links to a page, anchor or file that does not exist.

Reads the HTML that `npm run build` writes to .vitepress/dist, so it sees links,
image sources and heading ids exactly as they are published under the /docs/ base.

    npm run build && python -I scripts/check_links.py
"""

import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

DIST = Path(__file__).resolve().parent.parent / ".vitepress" / "dist"
BASE = "/docs/"

HREF = re.compile(r'<a\b[^>]*?\shref="([^"]*)"')
SRC = re.compile(r'<img\b[^>]*?\ssrc="([^"]*)"')
ID = re.compile(r'\sid="([^"]*)"')


def resolve(path: str) -> Path | None:
    rel = path.removeprefix(BASE)
    for candidate in (DIST / rel, DIST / f"{rel}.html", DIST / rel / "index.html"):
        if candidate.is_file():
            return candidate
    return None


def url_of(page: Path) -> str:
    """The URL a built page is served at, for resolving its relative links."""
    rel = page.relative_to(DIST).as_posix()
    if rel == "index.html" or rel.endswith("/index.html"):
        return BASE + rel.removesuffix("index.html")
    return BASE + rel.removesuffix(".html")


def main() -> int:
    ids: dict[Path, set[str]] = {}
    problems: list[str] = []
    pages = sorted(DIST.rglob("*.html"))
    for page in pages:
        html = page.read_text(encoding="utf-8")
        where = page.relative_to(DIST).as_posix()
        here = url_of(page)
        for src in map(unescape, SRC.findall(html)):
            if src.startswith(("http://", "https://", "data:")):
                continue
            src = urljoin(here, src)
            if not src.startswith(BASE) or resolve(src) is None:
                problems.append(f"{where}: image {src} has no file")
        for href in map(unescape, HREF.findall(html)):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, fragment = href.partition("#")
            path = urljoin(here, path) if path else path
            if not path:
                target = page
            elif not path.startswith(BASE):
                problems.append(f"{where}: {href} is outside {BASE}")
                continue
            elif (target := resolve(path)) is None:
                problems.append(f"{where}: {href} has no page")
                continue
            if fragment:
                if target not in ids:
                    ids[target] = set(ID.findall(target.read_text(encoding="utf-8")))
                if fragment not in ids[target]:
                    problems.append(f"{where}: {href} has no such anchor")

    if not pages:
        problems.append(f"no HTML under {DIST}; run npm run build first")
    for problem in problems:
        print(problem)
    print(f"{len(pages)} pages, {len(problems)} broken links")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
