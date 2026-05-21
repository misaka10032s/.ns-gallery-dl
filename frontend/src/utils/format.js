export function formatDate(dateValue) {
  if (!dateValue) return '—'
  return new Date(`${dateValue}T00:00:00`).toLocaleDateString('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

export function formatDateTime(dateValue) {
  if (!dateValue) return '—'
  const date = new Date(dateValue)
  if (Number.isNaN(date.getTime())) return String(dateValue)
  return date.toLocaleString('zh-TW', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatNumber(value) {
  return new Intl.NumberFormat('zh-TW').format(Number(value ?? 0))
}

export function hostnameFromUrl(value) {
  if (!value) return 'unknown'
  try {
    const url = value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`
    return new URL(url).hostname
  } catch {
    return 'unknown'
  }
}

export function parseLinksInput(input) {
  return Array.from(
    new Set(
      String(input ?? '')
        .split(/[\s,]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  )
}

export async function copyText(value) {
  if (!value) return
  await navigator.clipboard.writeText(value)
}
