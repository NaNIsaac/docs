"""
Write site/<slug>/reference/api.md from the docstrings of each project's package.

Runs after sync.py and reads the checkouts it recorded in
.vitepress/generated/projects.json. The package is parsed with ast and never
imported, so its dependencies do not need to be installed. Public means a
top-level function or class whose name has no leading underscore, in a module
whose path has none either; a module's __all__, when it is a literal list, narrows
that further.

The page is a supplement to the written docs: any failure is reported as a warning
and the script still exits 0, so the site builds without it.

    python -I scripts/api_md.py
"""

import ast
import html
import json
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
GENERATED = ROOT / ".vitepress" / "generated" / "projects.json"
WIDTH = 88


def warn(message: str) -> None:
    print(f"::warning::{message}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {message}", file=sys.stderr)


def find_package(checkout: Path, project: dict) -> Path | None:
    if "package" in project:
        return checkout / project["package"]
    pyproject = checkout / "pyproject.toml"
    if not pyproject.is_file():
        return None
    name = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("name")
    if not name:
        return None
    name = re.sub(r"[-.]+", "_", name).lower()
    for candidate in (checkout / "src" / name, checkout / name):
        if (candidate / "__init__.py").is_file():
            return candidate
    return None


def docstring(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module) -> str:
    text = ast.get_docstring(node)
    if not text:
        return ""
    # A <pre> block keeps numpydoc underlines and indentation; v-pre stops Vue from reading {{ }}.
    return f'<pre class="api-doc" v-pre>{html.escape(text, quote=False)}</pre>\n\n'


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    decorators = "".join(f"@{ast.unparse(d)}\n" for d in node.decorator_list if not is_overload_decorator(d))
    line = f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"
    if len(line) > WIDTH:
        params = split_args(node.args)
        line = f"{prefix} {node.name}(\n" + "".join(f"    {p},\n" for p in params) + f"){returns}"
    return decorators + line


def split_args(args: ast.arguments) -> list[str]:
    """One string per parameter, including the / and * markers, for multi-line signatures."""

    def param(arg: ast.arg, default: ast.expr | None, star: str = "") -> str:
        text = star + arg.arg
        if arg.annotation:
            text += f": {ast.unparse(arg.annotation)}"
        if default is not None:
            text += f" = {ast.unparse(default)}" if arg.annotation else f"={ast.unparse(default)}"
        return text

    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    out: list[str] = []
    for i, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        out.append(param(arg, default))
        if args.posonlyargs and i == len(args.posonlyargs) - 1:
            out.append("/")
    if args.vararg:
        out.append(param(args.vararg, None, "*"))
    elif args.kwonlyargs:
        out.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        out.append(param(arg, default))
    if args.kwarg:
        out.append(param(args.kwarg, None, "**"))
    return out


def class_block(node: ast.ClassDef) -> str:
    decorators = "".join(f"@{ast.unparse(d)}\n" for d in node.decorator_list)
    bases = [ast.unparse(b) for b in node.bases] + [ast.unparse(k) for k in node.keywords]
    lines = [f"{decorators}class {node.name}" + (f"({', '.join(bases)})" if bases else "") + ":"]
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and not item.target.id.startswith("_"):
            lines.append(f"    {ast.unparse(item)}")
        elif isinstance(item, ast.FunctionDef) and item.name == "__init__":
            lines.append("    " + signature(item).replace("\n", "\n    "))
    if len(lines) == 1:
        lines.append("    ...")
    return "\n".join(lines)


def public_names(tree: ast.Module) -> set[str] | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            try:
                return set(ast.literal_eval(node.value))
            except ValueError:
                return None
    return None


def is_overload_decorator(decorator: ast.expr) -> bool:
    return ast.unparse(decorator) in ("overload", "typing.overload")


def is_overload(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(map(is_overload_decorator, node.decorator_list))


def function_block(title: str, nodes: list[ast.FunctionDef | ast.AsyncFunctionDef], level: str) -> str:
    """One heading per name: the @overload signatures when there are any, else every definition."""
    shown = [n for n in nodes if is_overload(n)] or nodes
    code = "\n".join(signature(n) for n in shown)
    doc = next((d for n in reversed(nodes) if (d := docstring(n))), "")
    return f"{level} {title}\n\n```python\n{code}\n```\n\n{doc}"


def functions(body: list[ast.stmt]) -> dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]:
    out: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith("_"):
            out.setdefault(node.name, []).append(node)
    return out


def render_module(module: str, tree: ast.Module) -> str:
    wanted = public_names(tree)
    out: list[str] = []
    grouped = functions(tree.body)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if node.name.startswith("_") or (wanted is not None and node.name not in wanted):
            continue
        if isinstance(node, ast.ClassDef):
            out.append(f"### {node.name}\n\n```python\n{class_block(node)}\n```\n\n{docstring(node)}")
            for name, nodes in functions(node.body).items():
                out.append(function_block(f"{node.name}.{name}", nodes, "####"))
        elif grouped.get(node.name, [None])[0] is node:
            out.append(function_block(node.name, grouped[node.name], "###"))
    if not out:
        return ""
    return f"## {module}\n\n{docstring(tree)}" + "".join(out)


def render(project: dict) -> str | None:
    checkout = Path(project["checkout"])
    package = find_package(checkout, project)
    if package is None:
        warn(f"{project['slug']}: no Python package found; skipping the API page")
        return None
    sections: list[str] = []
    root = package.parent
    for path in sorted(package.rglob("*.py")):
        parts = path.relative_to(root).with_suffix("").parts
        if any(p.startswith("_") and p != "__init__" for p in parts):
            continue
        module = ".".join(parts).removesuffix(".__init__")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as error:
            warn(f"{project['slug']}: cannot parse {path.relative_to(checkout)}: {error}")
            continue
        if section := render_module(module, tree):
            sections.append(section)
    if not sections:
        warn(f"{project['slug']}: {package.name} has no public functions or classes")
        return None
    source = f"https://github.com/{project['repo']}/tree/{project['commit']}/{package.relative_to(checkout).as_posix()}"
    head = (
        "# Python API\n\n"
        f"Signatures and docstrings of the public functions and classes in [`{package.name}`]({source}) "
        f"at `{project['ref']}` (`{project['commit'][:7]}`), read from the source without importing it. "
        "The guides on this site say how the pieces fit together; this page is for looking up an argument.\n\n"
    )
    return head + "\n".join(sections)


def main() -> int:
    try:
        projects = json.loads(GENERATED.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        warn(f"cannot read {GENERATED.relative_to(ROOT)} ({error}); run sync.py first")
        return 0
    for project in projects:
        if "checkout" not in project:
            continue
        try:
            page = render(project)
        except Exception as error:  # noqa: BLE001 - a broken API page must not stop the site build
            warn(f"{project['slug']}: API page failed: {type(error).__name__}: {error}")
            continue
        if page is None:
            continue
        dest = SITE / project["slug"] / "reference" / "api.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding="utf-8", newline="\n")
        print(f"{project['slug']}: wrote {dest.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
