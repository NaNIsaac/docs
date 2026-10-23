# docs

The documentation site for NaNIsaac projects, published at <https://nanisaac.github.io/docs/>.

This repository holds only the shell: the VitePress config and theme, the home page, the scripts that collect
the docs, and the workflow that builds and deploys them. The pages themselves live in each project's
repository under `docs/`, so code and its documentation change in the same pull request.

## Adding a project

Add an entry to `projects.json`:

```json
{
  "slug": "qoraphase",
  "repo": "NaNIsaac/QoraPhase",
  "ref": "main",
  "docs_path": "docs",
  "title": "QoraPhase",
  "tagline": "One line for the home page card."
}
```

`slug` becomes the URL (`/docs/qoraphase/`), `ref` is the branch, tag or commit that is built, and
`docs_path` is the directory that is copied. An entry with `url` in place of `repo`, `ref` and `docs_path`
is shown on the home page as a link to a separate site. An optional `package` (for example
`"src/qoraphase"`) names the Python package for the API page when it cannot be found from `pyproject.toml`.

In the project, `docs/nav.json` sets the sidebar and decides which pages are published:

```json
{
  "sidebar": [
    { "text": "Getting Started", "items": [{ "text": "Overview", "link": "index.md" }] },
    { "text": "Guides", "items": [{ "text": "Hardware", "link": "hardware.md" }] }
  ]
}
```

Links are paths relative to `docs/`, so they also work when the file is read on GitHub. Only the Markdown
files listed there are published; images and other non-Markdown files in `docs/` are always copied. Without
`nav.json`, every Markdown file is published in one group, ordered by file name. A project without
`docs/index.md` gets a generated index that lists its pages.

Relative links that leave the published pages, such as `../README.md`, `../src/...` or an unlisted page,
are rewritten to the file on GitHub at `ref`.

## What the build does

`.github/workflows/docs.yml` runs on pushes to `main`, on pull requests, by hand, and on a
`repository_dispatch` event of type `docs-changed`, which a project can send when its `docs/` changes.

1. `scripts/sync.py` fetches each project at `ref` (depth 1, into `.cache/repos/`) and copies its docs into
   `site/<slug>/`. It writes the sidebars to `.vitepress/generated/projects.json`.
2. `scripts/api_md.py` writes `site/<slug>/reference/api.md` from the signatures and docstrings of the
   project's public functions and classes. It parses the source with `ast` and never imports the package.
   A failure here is a warning; the site builds without the page.
3. `npm run build` builds the site; `scripts/check_links.py` fails the run on a link, anchor or image that
   does not exist in the output.
4. On `main`, the output is deployed to GitHub Pages. Pull requests stop after the link check.

Everything under `site/` except `index.md` and `public/` is generated and ignored by git.

## Build locally

Needs Node 20 or later, git, and Python 3.14 (the scripts use only the standard library).

```sh
python -I scripts/sync.py
python -I scripts/api_md.py
npm ci
npm run build
python -I scripts/check_links.py
npx vitepress preview
```

To preview a project's docs before they are pushed, point `sync.py` at a local checkout:

```sh
python -I scripts/sync.py --local qoraphase=../QoraPhase
```

`vitepress preview` reads the file list once at start; restart it after rebuilding.

## License

MIT
