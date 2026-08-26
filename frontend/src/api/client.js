export async function apiRequest(path, options = {}) {
  const { body, headers, ...rest } = options
  const response = await fetch(path, {
    ...rest,
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(headers ?? {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })

  const raw = await response.text()
  let payload = null
  if (raw) {
    try {
      payload = JSON.parse(raw)
    } catch {
      payload = raw
    }
  }

  if (!response.ok) {
    const message =
      (payload && typeof payload === 'object' && (payload.error || payload.message)) ||
      `Request failed (${response.status})`
    const error = new Error(message)
    // Additive — existing callers only ever read `.message`. Callers that
    // need the structured body (e.g. the series near-duplicate 409, which
    // carries `candidates`) can read `.status` / `.payload` instead of
    // re-parsing the message string.
    error.status = response.status
    error.payload = payload
    throw error
  }

  return payload
}
