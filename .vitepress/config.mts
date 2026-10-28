import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig, type DefaultTheme } from 'vitepress'

const hub = 'https://github.com/NaNIsaac/docs'

type SidebarGroup = { text: string; items: { text: string; link: string }[] }

type Project = {
  slug: string
  title: string
  tagline: string
  repo?: string
  ref?: string
  docs_path?: string
  url?: string
  sidebar?: SidebarGroup[]
}

// Written by scripts/sync.py; without it the site still builds, with the home page only.
const generated = fileURLToPath(new URL('./generated/projects.json', import.meta.url))
const projects: Project[] = existsSync(generated) ? JSON.parse(readFileSync(generated, 'utf-8')) : []
const hosted = projects.filter((p) => p.sidebar)

const site = fileURLToPath(new URL('../site/', import.meta.url))

function sidebar(p: Project): DefaultTheme.SidebarItem[] {
  const groups: DefaultTheme.SidebarItem[] = p.sidebar!.map((g) => ({ text: g.text, items: [...g.items] }))
  if (existsSync(`${site}${p.slug}/reference/api.md`)) {
    const api = { text: 'Python API', link: `/${p.slug}/reference/api` }
    const reference = groups.find((g) => g.text === 'Reference')
    if (reference) reference.items!.push(api)
    else groups.push({ text: 'Reference', items: [api] })
  }
  return [{ text: p.title, link: `/${p.slug}/`, items: groups }]
}

// The URL of the file a page was copied from; the theme's pattern below cannot see this module.
function sourceUrl(filePath: string): string {
  const [slug, ...rest] = filePath.split('/')
  const p = hosted.find((q) => q.slug === slug)
  if (!p) return `${hub}/edit/main/site/${filePath}`
  const page = rest.join('/')
  if (page === 'reference/api.md') return `https://github.com/${p.repo}/tree/${p.ref}`
  return `https://github.com/${p.repo}/edit/${p.ref}/${p.docs_path}/${page}`
}

export default defineConfig({
  title: 'NaNIsaac docs',
  description: 'Documentation for NaNIsaac research software, one section per project.',
  lang: 'en',
  base: '/docs/',
  srcDir: 'site',
  cleanUrls: true,
  appearance: 'dark',
  head: [['link', { rel: 'icon', type: 'image/svg+xml', href: '/docs/favicon.svg' }]],
  // $...$ and $$...$$ are rendered to SVG at build time (markdown-it-mathjax3); no math script runs in the browser.
  markdown: { math: true },

  transformPageData(page) {
    page.frontmatter.sourceUrl = sourceUrl(page.relativePath)
  },

  themeConfig: {
    logo: { src: '/favicon.svg', alt: '' },
    siteTitle: 'NaNIsaac docs',
    nav: [
      {
        text: 'Projects',
        items: projects.map((p) => ({ text: p.title, link: p.url ?? `/${p.slug}/` })),
      },
      { text: 'Architecture', link: '/arch/' },
      { text: 'NaNIsaac', link: 'https://github.com/NaNIsaac' },
    ],
    sidebar: Object.fromEntries(hosted.map((p) => [`/${p.slug}/`, sidebar(p)])),
    editLink: { pattern: ({ frontmatter }) => frontmatter.sourceUrl, text: 'Edit this page on GitHub' },
    socialLinks: [{ icon: 'github', link: hub }],
    outline: { level: [2, 3] },
    search: { provider: 'local' },
    footer: {
      message: 'Each project section is built from that project’s docs/ directory.',
      copyright: 'Isaac Yong',
    },
  },
})
