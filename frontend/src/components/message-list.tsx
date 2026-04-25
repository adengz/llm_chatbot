import { Bot, User, Code2, Brain } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { ChatMessage } from './chat-types'

type MessageListProps = {
  messages: ChatMessage[]
}

function ToolCallDisplay({ content, type, isStreaming }: { content: string; type: string; isStreaming?: boolean }) {
  let displayContent = content
  let isValidJson = false

  try {
    const trimmed = content.trim()
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      const parsed = JSON.parse(trimmed)
      displayContent = JSON.stringify(parsed, null, 2)
      isValidJson = true
    }
  } catch (e) {
    // Partial JSON or not JSON
  }

  return (
    <details 
      className="mb-2 rounded-md border border-border/70 bg-background/70 p-2 text-xs text-muted-foreground group" 
      open={isStreaming}
    >
      <summary className="flex cursor-pointer select-none items-center gap-2">
        <Code2 className="size-3" />
        <span className="font-medium">
          {type === 'tool_call_req' ? 'Tool Call Request' : 'Tool Call Response'}
        </span>
      </summary>
      <div className="mt-2 overflow-hidden rounded bg-muted/50">
        <pre className="max-h-60 overflow-auto p-2 text-[10px] leading-tight whitespace-pre-wrap break-all font-mono">
          {displayContent || (isStreaming ? 'Waiting for tool data...' : 'No data')}
        </pre>
      </div>
    </details>
  )
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="space-y-4 py-6">
      {messages.map((message) => {
        const isAssistant = message.role === 'assistant'
        const isTool = message.type === 'tool_call_req' || message.type === 'tool_call_resp'
        const isThinking = message.type === 'thinking'
        const isStreaming = message.id.startsWith('__streaming__')

        return (
          <div
            key={message.id}
            className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {isAssistant && (
              <div className="mt-1 flex-shrink-0 rounded-md border border-border/80 bg-muted p-1 text-muted-foreground self-start">
                <Bot className="size-4" />
              </div>
            )}

            <div
              className={`max-w-[70ch] rounded-xl border px-4 py-3 text-sm leading-6 ${
                isAssistant
                  ? isThinking || isTool
                    ? 'border-border/50 bg-muted/30 text-muted-foreground'
                    : 'border-border bg-card text-card-foreground'
                  : 'border-primary/40 bg-primary text-primary-foreground'
              }`}
            >
              {isThinking && (
                <details className="group" open={isStreaming}>
                  <summary className="flex cursor-pointer select-none items-center gap-2 italic text-xs">
                    <Brain className={`size-3 ${isStreaming ? 'animate-pulse' : ''}`} />
                    <span className="opacity-70">Thinking</span>
                  </summary>
                  {message.content && (
                    <div className="mt-1 border-l-2 border-border/40 pl-3 text-xs italic opacity-80 overflow-hidden prose prose-sm dark:prose-invert max-w-none prose-table:block prose-table:overflow-x-auto prose-table:whitespace-nowrap">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                    </div>
                  )}
                </details>
              )}

              {isTool && (
                <ToolCallDisplay 
                  content={message.content} 
                  type={message.type!} 
                  isStreaming={isStreaming} 
                />
              )}

              {!isTool && !isThinking && (
                <>
                  {isAssistant ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 overflow-hidden prose-table:block prose-table:overflow-x-auto prose-table:whitespace-nowrap">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <p>{message.content}</p>
                  )}
                </>
              )}
            </div>

            {message.role === 'user' && (
              <div className="mt-1 flex-shrink-0 rounded-md border border-border/80 bg-muted p-1 text-muted-foreground self-start">
                <User className="size-4" />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

