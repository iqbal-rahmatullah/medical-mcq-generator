const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE_URL || API_BASE.replace(/^http/, 'ws')

export function getWsUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${WS_BASE.replace(/\/$/, '')}${normalizedPath}`
}
