export type Role = 'user' | 'assistant'
export type MessageType = 'tool_call_req' | 'tool_call_resp' | 'thinking' | 'content'

export type ChatMessage = {
  id: string
  role: Role
  type?: MessageType
  content: string
  reasoning?: string
}

export type ModelSource = string
