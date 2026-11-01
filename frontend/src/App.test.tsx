import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import App from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('backend connectivity shell', () => {
  it('shows real readiness details returned by the API', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', version: '0.1.0' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        status: 'not_ready',
        dependencies: {
          postgres: { status: 'up', detail: null },
          redis: { status: 'down', detail: 'probe failed or timed out' },
          minio: { status: 'up', detail: null },
        },
      }), { status: 503 }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('API connection established')).toBeInTheDocument()
    expect(screen.getByText('Dependencies need attention')).toBeInTheDocument()
    expect(screen.getByText('PostgreSQL')).toBeInTheDocument()
    expect(screen.getByText('probe failed or timed out')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.any(Object))
    expect(fetchMock).toHaveBeenCalledWith('/api/ready', expect.any(Object))
  })

  it('shows an honest disconnected state when the API cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    render(<App />)

    await waitFor(() => expect(screen.getByText('API is not reachable')).toBeInTheDocument())
    expect(screen.getByText(/make dev/i)).toBeInTheDocument()
  })

  it('does not present an unexpected readiness error as a successful API connection', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', version: '0.1.0' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'internal_error' }), { status: 500 })))

    render(<App />)

    await waitFor(() => expect(screen.getByText('API is not reachable')).toBeInTheDocument())
  })
})
