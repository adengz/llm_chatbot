import { Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { listLlmsModelsGet } from '../../client/sdk.gen'
import { streamMessage } from '../../client/stream'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { ChatComposer } from './chat-composer'
import { ChatMessageList } from './chat-message-list'
import type { ChatMessage, ModelSource, ReasoningEffort } from './chat-types'

const mockConversations = [
  { id: 'c1', title: 'MVP scope and API mapping' },
  { id: 'c2', title: 'Streaming event parser plan' },
  { id: 'c3', title: 'Follow-up UX polish backlog' },
]

const STREAMING_MESSAGE_ID = '__streaming__'

export function ChatModule() {
  const [draft, setDraft] = useState('')
  const [modelSource, setModelSource] = useState<ModelSource>('ollama_cloud')
  const [model, setModel] = useState('qwen3:32b')
  const [reasoningEffort, setReasoningEffort] =
    useState<ReasoningEffort>('medium')
  const [modelOptionsBySource, setModelOptionsBySource] =
    useState<Record<ModelSource, string[]>>({})
  const [isModelOptionsLoading, setIsModelOptionsLoading] = useState(false)
  const [modelOptionsError, setModelOptionsError] = useState<string | null>(null)
  const [modelOptionsRefreshKey, setModelOptionsRefreshKey] = useState(0)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (isNearBottom) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages])

  useEffect(() => {
    let isCancelled = false

    const loadModels = async () => {
      setIsModelOptionsLoading(true)

      const { data, error } = await listLlmsModelsGet()

      if (isCancelled) {
        return
      }

      if (error || !data || typeof data !== 'object') {
        setModelOptionsBySource({})
        setModelOptionsError('Failed to load models from backend. Model list is unavailable.')
        setIsModelOptionsLoading(false)
        return
      }

      const normalizedModelOptions = Object.entries(data).reduce<Record<string, string[]>>(
        (acc, [source, models]) => {
          if (!Array.isArray(models)) {
            return acc
          }

          const validModels = models.filter(
            (value): value is string => typeof value === 'string' && value.trim().length > 0,
          )

          if (validModels.length > 0) {
            acc[source] = Array.from(new Set(validModels))
          }

          return acc
        },
        {},
      )

      if (Object.keys(normalizedModelOptions).length > 0) {
        setModelOptionsBySource(normalizedModelOptions)
        setModelOptionsError(null)
      } else {
        setModelOptionsBySource({})
        setModelOptionsError('No models returned from backend.')
      }

      setIsModelOptionsLoading(false)
    }

    void loadModels()

    return () => {
      isCancelled = true
    }
  }, [modelOptionsRefreshKey])

  const handleRefreshModels = () => {
    setModelOptionsRefreshKey((k) => k + 1)
  }

  useEffect(() => {
    const availableSources = Object.keys(modelOptionsBySource)

    if (availableSources.length === 0) {
      return
    }

    if (!availableSources.includes(modelSource)) {
      const nextSource = availableSources[0]
      const nextModels = modelOptionsBySource[nextSource] ?? []
      setModelSource(nextSource)
      setModel(nextModels[0] ?? '')
      return
    }

    const modelsForSource = modelOptionsBySource[modelSource] ?? []
    if (modelsForSource.length > 0 && !modelsForSource.includes(model)) {
      setModel(modelsForSource[0])
    }
  }, [model, modelOptionsBySource, modelSource])

  const handlePromptClick = () => {
    // Placeholder: prompt helper behavior will be implemented with backend integration.
  }

  const handleSendClick = async () => {
    const content = draft.trim()
    if (!content || isStreaming) return

    setDraft('')
    setIsStreaming(true)

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
    }
    setMessages((prev) => [...prev, userMessage])

    const streamingMessage: ChatMessage = {
      id: STREAMING_MESSAGE_ID,
      role: 'assistant',
      content: '',
    }
    setMessages((prev) => [...prev, streamingMessage])

    const abort = new AbortController()
    abortRef.current = abort

    try {
      for await (const event of streamMessage(
        {
          conversation_id: conversationId ?? undefined,
          content,
          model_source: modelSource,
          model,
          reasoning_effort: reasoningEffort,
        },
        abort.signal,
      )) {
        if (event.type === 'metadata') {
          setConversationId(event.conversation_id)
        } else if (event.type === 'content') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === STREAMING_MESSAGE_ID ? { ...m, content: m.content + event.delta } : m,
            ),
          )
        } else if (event.type === 'reasoning') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === STREAMING_MESSAGE_ID
                ? { ...m, reasoning: (m.reasoning ?? '') + event.delta }
                : m,
            ),
          )
        } else if (event.type === 'done') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === STREAMING_MESSAGE_ID ? { ...m, id: `assistant-${Date.now()}` } : m,
            ),
          )
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === STREAMING_MESSAGE_ID
              ? { ...m, id: `assistant-${Date.now()}`, content: m.content || '[Error: stream failed]' }
              : m,
          ),
        )
      } else {
        // Remove placeholder if aborted with no content
        setMessages((prev) =>
          prev.map((m) =>
            m.id === STREAMING_MESSAGE_ID
              ? { ...m, id: `assistant-${Date.now()}` }
              : m,
          ),
        )
      }
    } finally {
      abortRef.current = null
      setIsStreaming(false)
    }
  }

  return (
    <div className="grid h-screen grid-cols-[280px_1fr] gap-4 bg-background p-4 text-foreground">
      <Card className="overflow-hidden">
        <CardHeader className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <CardTitle>Conversations</CardTitle>
            <Button size="icon" variant="outline" aria-label="Start new conversation">
              <Plus className="size-4" />
            </Button>
          </div>
          <CardDescription>MVP chat continuity surface</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 overflow-y-auto">
          {mockConversations.map((conversation, idx) => (
            <button
              key={conversation.id}
              className="w-full rounded-lg border border-border/70 p-3 text-left text-sm transition hover:border-primary/50 hover:bg-muted"
              type="button"
            >
              <p className="line-clamp-1 font-medium text-foreground">{conversation.title}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {idx === 0 ? 'Active conversation' : 'Click to load history'}
              </p>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card className="grid h-full grid-rows-[auto_1fr_auto] overflow-hidden">
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Chat Module Sketch</CardTitle>
            <CardDescription>shadcn + Tailwind MVP composition</CardDescription>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline">source: {modelSource}</Badge>
            <Badge variant="secondary">reasoning: {reasoningEffort}</Badge>
          </div>
        </CardHeader>

        <CardContent className="overflow-y-auto" ref={scrollRef}>
          <ChatMessageList messages={messages} />
        </CardContent>

        <ChatComposer
          draft={draft}
          modelSource={modelSource}
          model={model}
          modelOptionsBySource={modelOptionsBySource}
          isModelOptionsLoading={isModelOptionsLoading}
          modelOptionsError={modelOptionsError}
          reasoningEffort={reasoningEffort}
          isStreaming={isStreaming}
          onDraftChange={setDraft}
          onModelSourceChange={setModelSource}
          onModelChange={setModel}
          onReasoningEffortChange={setReasoningEffort}
          onPromptClick={handlePromptClick}
          onSendClick={() => { void handleSendClick() }}
          onRefreshModels={handleRefreshModels}
        />
      </Card>
    </div>
  )
}
