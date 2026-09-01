// Real regression coverage for JobsView.vue — this is the first frontend test file in this
// repo, added to close G3's vacuous-pass defect (see .claude/CLAUDE.md `## Code quality gates`).
//
// Scope: `jobs.error` rendering + the search filter that matches against it. This is genuine
// user-facing logic (JobsView.vue's `filteredJobs` computed + the error <div> in the table),
// not a smoke test — each assertion below fails if the behaviour it names actually breaks.
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// apiRequest is mocked so mounting never performs a real network fetch (onMounted() calls
// store.fetchJobs()). The store's `jobs` array is populated directly per-test instead — that
// is the same state `fetchJobs()` would have produced from a real API response.
vi.mock('../api/client', () => ({
  apiRequest: vi.fn().mockResolvedValue([]),
}))

import JobsView from './JobsView.vue'
import { useHubStore } from '../stores/hub'

function makeJob(overrides = {}) {
  return {
    id: 1,
    status: 'success',
    provider: 'gallery-dl',
    source: 'manual',
    domain: 'example.com',
    url: 'https://example.com/a',
    download_path: '',
    error: '',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('JobsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders the job error message when a job failed', async () => {
    const wrapper = mount(JobsView)
    await flushPromises() // let the onMounted fetchJobs() (mocked, resolves to []) settle first
    const store = useHubStore()
    store.jobs = [makeJob({ id: 42, status: 'failed', error: 'HTTP 403: cookie expired' })]
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('HTTP 403: cookie expired')
    expect(wrapper.find('.table-error').exists()).toBe(true)
  })

  it('does not render an error row for a job without an error', async () => {
    const wrapper = mount(JobsView)
    await flushPromises()
    const store = useHubStore()
    store.jobs = [makeJob({ id: 7, status: 'success', error: '' })]
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.table-error').exists()).toBe(false)
  })

  it('search filters jobs by matching error text', async () => {
    const wrapper = mount(JobsView)
    await flushPromises()
    const store = useHubStore()
    store.jobs = [
      makeJob({ id: 1, url: 'https://example.com/ok', status: 'success', error: '' }),
      makeJob({ id: 2, url: 'https://example.com/bad', status: 'failed', error: 'stale extractor: yt-dlp' }),
    ]
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)

    await wrapper.find('input[type="search"]').setValue('stale extractor')
    await wrapper.vm.$nextTick()

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('stale extractor: yt-dlp')
  })

  it('search with no match shows the empty state, not a stale row', async () => {
    const wrapper = mount(JobsView)
    await flushPromises()
    const store = useHubStore()
    store.jobs = [makeJob({ id: 1, url: 'https://example.com/ok', status: 'success', error: '' })]
    await wrapper.vm.$nextTick()

    await wrapper.find('input[type="search"]').setValue('no-such-term')
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.findAll('tbody tr')).toHaveLength(0)
  })
})
