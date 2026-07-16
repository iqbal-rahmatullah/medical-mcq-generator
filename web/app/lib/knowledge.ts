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

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  return parseOrThrow(await fetch(url, init))
}

export async function listKnowledge(): Promise<KnowledgeManifest[]> {
  return request("/api/knowledge", { cache: "no-store" })
}

export async function getKnowledge(kbId: string): Promise<KnowledgeManifest> {
  return request(`/api/knowledge/${kbId}`, { cache: "no-store" })
}

export async function createKnowledge(
  title: string,
  files: File[],
): Promise<KnowledgeManifest> {
  const form = new FormData()
  form.append("title", title)
  files.forEach((file) => form.append("files", file))
  return request("/api/knowledge", { method: "POST", body: form })
}

export async function renameKnowledge(
  kbId: string,
  title: string,
): Promise<KnowledgeManifest> {
  return request(`/api/knowledge/${kbId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  })
}

export async function addKnowledgeFiles(
  kbId: string,
  files: File[],
): Promise<KnowledgeManifest> {
  const form = new FormData()
  files.forEach((file) => form.append("files", file))
  return request(`/api/knowledge/${kbId}/files`, {
    method: "POST",
    body: form,
  })
}

export async function removeKnowledgeFile(
  kbId: string,
  filename: string,
): Promise<KnowledgeManifest> {
  return request(
    `/api/knowledge/${kbId}/files/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  )
}

export async function deleteKnowledge(kbId: string): Promise<void> {
  await request(`/api/knowledge/${kbId}`, { method: "DELETE" })
}

export type KeywordStat = { word: string; count: number }

export async function getKeywordStats(
  kbId: string,
  limit = 20,
): Promise<KeywordStat[]> {
  const data = await request<{ keywords?: KeywordStat[] }>(
    `/api/knowledge/${kbId}/keywords?limit=${limit}`,
    { cache: "no-store" },
  )
  return data.keywords || []
}
