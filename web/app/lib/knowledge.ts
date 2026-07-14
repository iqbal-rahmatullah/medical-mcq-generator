export type KnowledgeStatus = "processing" | "ready" | "failed"

export type KnowledgeManifest = {
  id: string
  title: string
  files: string[]
  n_chunks: number
  embed_model: string
  status: KnowledgeStatus
  progress: number
  error: string | null
  created_at: string
  updated_at?: string
}

async function parseOrThrow(res: Response): Promise<any> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      // ignore
    }
    throw new Error(detail || `request_failed_${res.status}`)
  }
  return res.json()
}

export async function listKnowledge(): Promise<KnowledgeManifest[]> {
  const res = await fetch("/api/knowledge", { cache: "no-store" })
  return parseOrThrow(res)
}

export async function getKnowledge(kbId: string): Promise<KnowledgeManifest> {
  const res = await fetch(`/api/knowledge/${kbId}`, { cache: "no-store" })
  return parseOrThrow(res)
}

export async function createKnowledge(
  title: string,
  files: File[],
): Promise<KnowledgeManifest> {
  const form = new FormData()
  form.append("title", title)
  files.forEach((file) => form.append("files", file))
  const res = await fetch("/api/knowledge", { method: "POST", body: form })
  return parseOrThrow(res)
}

export async function renameKnowledge(
  kbId: string,
  title: string,
): Promise<KnowledgeManifest> {
  const res = await fetch(`/api/knowledge/${kbId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  })
  return parseOrThrow(res)
}

export async function addKnowledgeFiles(
  kbId: string,
  files: File[],
): Promise<KnowledgeManifest> {
  const form = new FormData()
  files.forEach((file) => form.append("files", file))
  const res = await fetch(`/api/knowledge/${kbId}/files`, {
    method: "POST",
    body: form,
  })
  return parseOrThrow(res)
}

export async function removeKnowledgeFile(
  kbId: string,
  filename: string,
): Promise<KnowledgeManifest> {
  const res = await fetch(
    `/api/knowledge/${kbId}/files/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  )
  return parseOrThrow(res)
}

export async function deleteKnowledge(kbId: string): Promise<void> {
  const res = await fetch(`/api/knowledge/${kbId}`, { method: "DELETE" })
  await parseOrThrow(res)
}

export type KeywordStat = { word: string; count: number }

export async function getKeywordStats(
  kbId: string,
  limit = 20,
): Promise<KeywordStat[]> {
  const res = await fetch(`/api/knowledge/${kbId}/keywords?limit=${limit}`, {
    cache: "no-store",
  })
  const data = await parseOrThrow(res)
  return data.keywords || []
}
