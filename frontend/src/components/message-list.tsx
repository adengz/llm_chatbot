import { Bot, User, Code2, Brain, ChevronRight } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useState } from 'react'

import type { ChatMessage } from './chat-types'

type JsonValue = string | number | boolean | null | JsonObject | JsonArray
type JsonObject = { [key: string]: JsonValue }
type JsonArray = JsonValue[]

type MessageListProps = {
  messages: ChatMessage[]
}

function ExpandableStringValue({ value }: { value: string }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const MAX_DISPLAY_LENGTH = 100
  const isLongString = value.length > MAX_DISPLAY_LENGTH

  if (!isLongString) {
    return <span className="text-red-600">"{value}"</span>
  }

  return (
    <div className="inline-block">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="inline-flex items-center gap-1 text-red-600 hover:text-red-700 transition-colors"
      >
        <ChevronRight className={`size-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
        <span className="text-xs">"{value.substring(0, MAX_DISPLAY_LENGTH)}..."</span>
      </button>
      {isExpanded && (
        <div className="ml-4 border-l border-border/30 pl-2 mt-1">
          <span className="text-red-600 break-words whitespace-pre-wrap">"{value}"</span>
        </div>
      )}
    </div>
  )
}

function ExpandableJsonValue({ value, level = 0 }: { value: JsonValue; level?: number }) {
  const [isExpanded, setIsExpanded] = useState(level < 1) // Auto-expand first level

  if (value === null) {
    return <span className="text-amber-600">null</span>
  }

  if (typeof value === 'boolean') {
    return <span className="text-blue-600">{value.toString()}</span>
  }

  if (typeof value === 'number') {
    return <span className="text-green-600">{value}</span>
  }

  if (typeof value === 'string') {
    return <ExpandableStringValue value={value} />
  }

  if (Array.isArray(value)) {
    const isEmptyArray = value.length === 0
    const isSimpleArray = value.every(v => typeof v !== 'object' || v === null)

    if (isEmptyArray) {
      return <span className="text-muted-foreground">[]</span>
    }

    if (isSimpleArray && value.length <= 3) {
      return (
        <span className="text-muted-foreground">
          [
          {value.map((v, i) => (
            <span key={i}>
              <ExpandableJsonValue value={v} level={level + 1} />
              {i < value.length - 1 ? ', ' : ''}
            </span>
          ))}
          ]
        </span>
      )
    }

    return (
      <div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronRight className={`size-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
          <span className="text-xs">[Array({value.length})]</span>
        </button>
        {isExpanded && (
          <div className="ml-4 border-l border-border/30 pl-2 space-y-1">
            {value.map((item, index) => (
              <div key={index} className="text-xs">
                <span className="text-muted-foreground">[{index}]:</span>{' '}
                <ExpandableJsonValue value={item} level={level + 1} />
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (typeof value === 'object') {
    const keys = Object.keys(value)
    const isEmptyObject = keys.length === 0

    if (isEmptyObject) {
      return <span className="text-muted-foreground">{'{}'}</span>
    }

    return (
      <div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronRight className={`size-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
          <span className="text-xs">{'{Object'}</span>
          {!isExpanded && <span className="text-xs text-muted-foreground/60">...{keys.length} keys</span>}
          {!isExpanded && <span className="text-xs">{'}'}</span>}
        </button>
        {isExpanded && (
          <div className="ml-4 border-l border-border/30 pl-2 space-y-1">
            {keys.map((key) => (
              <div key={key} className="text-xs">
                <span className="text-purple-600">"{key}"</span>
                <span className="text-muted-foreground">:</span>{' '}
                <ExpandableJsonValue value={value[key]} level={level + 1} />
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  return <span>{String(value)}</span>
}

function ToolCallDisplay({ content, type, isStreaming }: { content: string; type: string; isStreaming?: boolean }) {
  let parsedData: JsonValue | null = null
  let displayContent = content
  let isValidJson = false

  try {
    const trimmed = content.trim()
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      parsedData = JSON.parse(trimmed)
      displayContent = JSON.stringify(parsedData, null, 2)
      isValidJson = true
    }
  } catch {
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
      <div className="mt-2 overflow-hidden rounded bg-muted/50 p-2">
        {isValidJson && parsedData !== null ? (
          <div className="font-mono text-[11px] leading-relaxed max-h-96 overflow-auto">
            <ExpandableJsonValue value={parsedData} />
          </div>
        ) : (
          <pre className="text-[10px] leading-tight whitespace-pre-wrap break-all overflow-auto max-h-60">
            {displayContent || (isStreaming ? 'Waiting for tool data...' : 'No data')}
          </pre>
        )}
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
                    <div className="mt-1 border-l-2 border-border/40 pl-3 text-xs italic opacity-80 overflow-hidden prose prose-sm max-w-none prose-table:block prose-table:overflow-x-auto prose-table:whitespace-nowrap">
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
                    <div className="prose prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 overflow-hidden prose-table:block prose-table:overflow-x-auto prose-table:whitespace-nowrap">
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

