export type Role = 'user' | 'assistant' | 'tool'

export type ToolCall = {
  id: string
  function: {
    name: string
    arguments: unknown
  }
}

export type ChatMessage =
  | {
      id: string
      role: 'user'
      content: string
    }
  | {
      id: string
      role: 'assistant'
      content: string
      reasoning?: string
      toolCalls?: ToolCall[]
    }
  | {
      id: string
      role: 'tool'
      content: unknown
      toolCallId: string
    }

export type ModelSource = string
