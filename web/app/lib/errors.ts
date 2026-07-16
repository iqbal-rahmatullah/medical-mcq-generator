export const errorMessage = (err: unknown, fallback: string) =>
  err instanceof Error ? err.message : fallback
