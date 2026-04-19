import { Bot, User } from 'lucide-react'

import type { ChatMessage } from './chat-types'

type ChatMessageListProps = {
  messages: ChatMessage[]
}

export function ChatMessageList({ messages }: ChatMessageListProps) {
  return (
    <div className="space-y-4 overflow-y-auto py-6">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          {message.role === 'assistant' && (
            <div className="mt-1 rounded-md border border-border/80 bg-muted p-1 text-muted-foreground">
              <Bot className="size-4" />
            </div>
          )}

          <div
            className={`max-w-[70ch] rounded-xl border px-4 py-3 text-sm leading-6 ${
              message.role === 'assistant'
                ? 'border-border bg-card text-card-foreground'
                : 'border-primary/40 bg-primary text-primary-foreground'
            }`}
          >
            <p>{message.content}</p>
            {message.reasoning && (
              <details className="mt-2 rounded-md border border-border/70 bg-background/70 p-2 text-xs text-muted-foreground">
                <summary className="cursor-pointer select-none">Reasoning</summary>
                <p className="mt-2">{message.reasoning}</p>
              </details>
            )}
          </div>

          {message.role === 'user' && (
            <div className="mt-1 rounded-md border border-border/80 bg-muted p-1 text-muted-foreground">
              <User className="size-4" />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
