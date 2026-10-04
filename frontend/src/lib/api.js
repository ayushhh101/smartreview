// Thin fetch wrapper. Surfaces the backend's structured errors as readable messages.
export async function api(path, options = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, options)
  } catch {
    throw new Error('Cannot reach the backend. Start it with: uvicorn backend.main:app --reload --port 8000')
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(body.message || `Request failed (${res.status})`)
    err.code = body.error; err.hint = body.hint
    throw err
  }
  return body
}
