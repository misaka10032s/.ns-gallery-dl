// Real regression coverage for HistoryView.vue's error-reason rendering (the fix for the
// defect where `history_entries.meta.error` was written by the wnacg backfill but never read
// by any view — see JobsView.spec.js for the sibling coverage of the `jobs.error` rendering
// this mirrors). Scope: the `.table-error` slot added next to `history-item__meta` — a failed
// entry with `meta.error` shows it, an old entry with no such field renders cleanly (no blank
// slot, no crash), and a successful entry never shows an error slot even if `meta.error`
// happens to be present.
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// apiRequest is mocked so mounting never performs a real network fetch (onMounted() calls
// store.fetchHistory()). The store's `historyMap` is populated directly per-test instead —
// that is the same state `fetchHistory()` would have produced from a real API response.
vi.mock('../api/client', () => ({
  apiRequest: vi.fn().mockResolvedValue({}),
}))

import HistoryView from './HistoryView.vue'
import { useHubStore } from '../stores/hub'

function makeEntry(overrides = {}) {
  return {
    url: 'https://www.wnacg.com/photos-index-aid-1.html',
    result: 'success',
    domain: 'wnacg.com',
    provider: 'gallery-dl',
    source: 'manual',
    download_path: '',
    meta: {},
    ...overrides,
  }
}

// History groups render collapsed by default (`<details>` closed) — the item list only
// exists in the DOM once its date group is expanded, same as clicking the summary in the app.
async function expandFirstGroup(wrapper) {
  await wrapper.find('.history-group summary').trigger('click')
  await wrapper.vm.$nextTick()
}

describe('HistoryView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // jsdom does not implement matchMedia — HistoryView mounts CompactPanelCard, which calls
    // it in onMounted() for its responsive compact/expanded behaviour (unrelated to what this
    // spec covers). Stub it so mounting doesn't throw; same technique any jsdom+matchMedia
    // consumer needs, not a workaround for the code under test.
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  })

  it('renders the wnacg failure reason for a failed history entry', async () => {
    const wrapper = mount(HistoryView)
    await flushPromises() // let the onMounted fetchHistory() (mocked, resolves to {}) settle first
    const store = useHubStore()
    store.historyMap = {
      '2026-09-01': [
        makeEntry({
          result: 'failed',
          meta: { error: 'CONFIG API（主線路）取得下載連結失敗: 403 Client Error' },
        }),
      ],
    }
    await wrapper.vm.$nextTick()
    await expandFirstGroup(wrapper)

    expect(wrapper.text()).toContain('CONFIG API（主線路）取得下載連結失敗: 403 Client Error')
    expect(wrapper.find('.table-error').exists()).toBe(true)
  })

  it('renders an old failed entry with no meta.error cleanly, without crashing or showing a blank slot', async () => {
    const wrapper = mount(HistoryView)
    await flushPromises()
    const store = useHubStore()
    store.historyMap = {
      '2026-01-01': [
        // meta present but empty — what history_repo.list_grouped() produces for a row
        // written before the wnacg error-reason backfill (meta_json defaults to "{}").
        makeEntry({ url: 'https://example.com/legacy-failed', result: 'failed', meta: {} }),
      ],
    }
    await wrapper.vm.$nextTick()
    await expandFirstGroup(wrapper)

    expect(wrapper.find('.table-error').exists()).toBe(false)
  })

  it('renders an old failed entry with no meta key at all cleanly (defensive, no crash)', async () => {
    const entryWithoutMeta = makeEntry({ url: 'https://example.com/no-meta-key', result: 'failed' })
    delete entryWithoutMeta.meta

    const wrapper = mount(HistoryView)
    await flushPromises()
    const store = useHubStore()
    store.historyMap = { '2026-01-01': [entryWithoutMeta] }
    await wrapper.vm.$nextTick()
    await expandFirstGroup(wrapper)

    expect(wrapper.find('.table-error').exists()).toBe(false)
  })

  it('does not render an error slot for a successful entry, even if meta.error is present', async () => {
    const wrapper = mount(HistoryView)
    await flushPromises()
    const store = useHubStore()
    store.historyMap = {
      '2026-09-01': [
        makeEntry({
          url: 'https://example.com/ok',
          result: 'success',
          meta: { error: 'should never be shown for a success entry' },
        }),
      ],
    }
    await wrapper.vm.$nextTick()
    await expandFirstGroup(wrapper)

    expect(wrapper.find('.table-error').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('should never be shown for a success entry')
  })
})
