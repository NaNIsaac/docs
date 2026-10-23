<script setup lang="ts">
import { withBase } from 'vitepress'
import projects from '../../projects.json'

const cards = projects.map((p) => ({
  title: p.title,
  tagline: p.tagline,
  href: 'url' in p && p.url ? p.url : withBase(`/${p.slug}/`),
  external: 'url' in p && Boolean(p.url),
  source: 'repo' in p ? p.repo : undefined,
}))
</script>

<template>
  <ul class="project-cards">
    <li v-for="card in cards" :key="card.title">
      <a class="project-card" :href="card.href" :target="card.external ? '_blank' : undefined"
        :rel="card.external ? 'noreferrer' : undefined">
        <span class="title">{{ card.title }}</span>
        <span class="tagline">{{ card.tagline }}</span>
        <span class="meta">{{ card.external ? 'Separate site' : card.source }}</span>
      </a>
    </li>
  </ul>
</template>
