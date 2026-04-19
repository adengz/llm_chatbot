export type Role = 'user' | 'assistant'

export type ChatMessage = {
  id: string
  role: Role
  content: string
  reasoning?: string
}

export type ReasoningEffort = 'low' | 'medium' | 'high'

export type ModelSource = string
