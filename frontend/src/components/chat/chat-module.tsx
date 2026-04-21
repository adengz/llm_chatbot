import { useEffect, useRef, useState, type UIEvent } from 'react'

import {
  deleteConversationConversationsConversationIdDelete,
  listConversationsConversationsGet,
  listLlmsModelsGet,
  listMessagesConversationsConversationIdMessagesGet,
  renameConversationConversationsConversationIdPatch,
} from '../../client/sdk.gen'
import type { Conversation as ApiConversation, Message as ApiMessage } from '../../client/types.gen'
import { streamMessage } from '../../client/stream'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { ChatComposer } from './chat-composer'
import { ChatMessageList } from './chat-message-list'
import type { ChatMessage, ModelSource, ReasoningEffort } from './chat-types'
import { ConversationSidebar } from './conversation-sidebar'

const STREAMING_MESSAGE_ID = '__streaming__'
const HISTORY_PAGE_SIZE = 100

function toChatMessage(message: ApiMessage, index: number): ChatMessage {
  return {
    id: `${message.created_at ?? 'message'}-${message.role}-${index}`,
    role: message.role,
    content: message.content,
  }
}

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
  const [conversations, setConversations] = useState<ApiConversation[]>([])
  const [isConversationsLoading, setIsConversationsLoading] = useState(false)
  const [conversationsError, setConversationsError] = useState<string | null>(null)
  const [messagesError, setMessagesError] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [historyCursor, setHistoryCursor] = useState<string | null>(null)
  const [hasMoreHistory, setHasMoreHistory] = useState(false)
  const [isLoadingOlderHistory, setIsLoadingOlderHistory] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const skipNextHistoryLoadRef = useRef(false)
  const activeConversationIdRef = useRef<string | null>(null)
  const forceScrollRef = useRef(false)

  const activeConversationTitle = conversations.find(
    (conversation) => conversation.conversation_id === conversationId,
  )?.title

  useEffect(() => {
    activeConversationIdRef.current = conversationId
  }, [conversationId])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    if (forceScrollRef.current) {
      forceScrollRef.current = false
      el.scrollTop = el.scrollHeight
      return
    }
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (isNearBottom) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages])

  useEffect(() => {
    let isCancelled = false

    const loadConversations = async () => {
      setIsConversationsLoading(true)

      const { data, error } = await listConversationsConversationsGet()

      if (isCancelled) {
        return
      }

      if (error || !Array.isArray(data)) {
        setConversations([])
        setConversationsError('Failed to load conversations.')
        setIsConversationsLoading(false)
        return
      }

      setConversations(data)
      setConversationsError(null)
      setIsConversationsLoading(false)
    }

    void loadConversations()

    return () => {
      isCancelled = true
    }
  }, [])

  const refreshConversations = async (failureMessage: string) => {
    const response = await listConversationsConversationsGet()

    if (response.error || !Array.isArray(response.data)) {
      setConversationsError(failureMessage)
      return
    }

    setConversations(response.data)
    setConversationsError(null)
  }

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
    if (!conversationId) {
      setMessages([])
      setMessagesError(null)
      setHistoryCursor(null)
      setHasMoreHistory(false)
      setIsLoadingOlderHistory(false)
      return
    }

    if (skipNextHistoryLoadRef.current) {
      skipNextHistoryLoadRef.current = false
      return
    }

    let isCancelled = false

    const loadHistory = async () => {
      setMessagesError(null)

      const response: { data?: ApiMessage[]; error?: unknown } = await listMessagesConversationsConversationIdMessagesGet({
        path: { conversation_id: conversationId },
        query: { limit: HISTORY_PAGE_SIZE },
      })

      if (isCancelled) {
        return
      }

      if (response.error || !Array.isArray(response.data)) {
        setMessages([])
        setMessagesError('Failed to load conversation history.')
        setHistoryCursor(null)
        setHasMoreHistory(false)
        return
      }

      const nextCursor = response.data[response.data.length - 1]?.created_at ?? null
      const chronological = [...response.data].reverse().map(toChatMessage)

      setMessages(chronological)
      setHistoryCursor(nextCursor)
      setHasMoreHistory(response.data.length === HISTORY_PAGE_SIZE && Boolean(nextCursor))
    }

    void loadHistory()

    return () => {
      isCancelled = true
    }
  }, [conversationId])

  const loadOlderHistory = async () => {
    if (!conversationId || !hasMoreHistory || isLoadingOlderHistory || !historyCursor) {
      return
    }

    const targetConversationId = conversationId
    const container = scrollRef.current
    const previousScrollTop = container?.scrollTop ?? 0
    const previousScrollHeight = container?.scrollHeight ?? 0

    setIsLoadingOlderHistory(true)

    const response: { data?: ApiMessage[]; error?: unknown } = await listMessagesConversationsConversationIdMessagesGet({
      path: { conversation_id: targetConversationId },
      query: { cursor: historyCursor, limit: HISTORY_PAGE_SIZE },
    })

    if (activeConversationIdRef.current !== targetConversationId) {
      setIsLoadingOlderHistory(false)
      return
    }

    if (response.error || !Array.isArray(response.data)) {
      setMessagesError('Failed to load older messages.')
      setIsLoadingOlderHistory(false)
      return
    }

    if (response.data.length === 0) {
      setHasMoreHistory(false)
      setHistoryCursor(null)
      setIsLoadingOlderHistory(false)
      return
    }

    const nextCursor = response.data[response.data.length - 1]?.created_at ?? null
    const olderMessages = [...response.data].reverse().map(toChatMessage)

    setMessages((prev) => [...olderMessages, ...prev])
    setHistoryCursor(nextCursor)
    setHasMoreHistory(response.data.length === HISTORY_PAGE_SIZE && Boolean(nextCursor))
    setIsLoadingOlderHistory(false)

    requestAnimationFrame(() => {
      const currentContainer = scrollRef.current
      if (!currentContainer) {
        return
      }
      const currentScrollHeight = currentContainer.scrollHeight
      currentContainer.scrollTop = currentScrollHeight - previousScrollHeight + previousScrollTop
    })
  }

  const handleHistoryScroll = (event: UIEvent<HTMLDivElement>) => {
    if (!hasMoreHistory || isLoadingOlderHistory) {
      return
    }

    if (event.currentTarget.scrollTop <= 80) {
      void loadOlderHistory()
    }
  }

  useEffect(() => {
    const container = scrollRef.current
    if (!container || !conversationId || !hasMoreHistory || isLoadingOlderHistory) {
      return
    }

    // If content does not overflow yet, prefetch older pages so users can scroll history.
    if (container.scrollHeight <= container.clientHeight + 8) {
      void loadOlderHistory()
    }
  }, [conversationId, hasMoreHistory, isLoadingOlderHistory, messages.length])

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

  const handleSelectConversation = (nextConversationId: string) => {
    if (isStreaming || nextConversationId === conversationId) {
      return
    }

    setConversationId(nextConversationId)
  }

  const handleStartNewConversation = () => {
    if (isStreaming) {
      return
    }

    setConversationId(null)
    setMessages([])
    setMessagesError(null)
  }

  const handleStopStreaming = () => {
    abortRef.current?.abort()
  }

  const handleRenameConversation = async (conversationId: string, newTitle: string) => {
    await renameConversationConversationsConversationIdPatch({
      path: { conversation_id: conversationId },
      body: { title: newTitle },
    })
    setConversations((prev) =>
      prev.map((c) => (c.conversation_id === conversationId ? { ...c, title: newTitle } : c)),
    )
  }

  const handleDeleteConversation = async (targetId: string) => {
    await deleteConversationConversationsConversationIdDelete({
      path: { conversation_id: targetId },
    })
    setConversations((prev) => prev.filter((c) => c.conversation_id !== targetId))
    if (conversationId === targetId) {
      setConversationId(null)
      setMessages([])
      setMessagesError(null)
    }
  }

  const handleSendClick = async () => {
    const content = draft.trim()
    if (!content || isStreaming) return

    setDraft('')
    setIsStreaming(true)
    setMessagesError(null)
    forceScrollRef.current = true

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
          if (!conversationId) {
            skipNextHistoryLoadRef.current = true
            void refreshConversations('Failed to refresh conversations.')
          }
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
        } else if (event.type === 'error') {
          setMessagesError(event.exception)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === STREAMING_MESSAGE_ID
                ? { ...m, id: `assistant-${Date.now()}`, content: m.content || `[Error: ${event.exception}]` }
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
        setMessagesError((err as Error).message)
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
    <div className="box-border grid h-dvh grid-cols-[280px_minmax(0,1fr)] grid-rows-[minmax(0,1fr)] gap-4 overflow-hidden bg-background p-4 text-foreground">
      <ConversationSidebar
        conversations={conversations}
        activeConversationId={conversationId}
        isLoading={isConversationsLoading}
        error={conversationsError}
        isStreaming={isStreaming}
        onSelectConversation={handleSelectConversation}
        onStartNewConversation={handleStartNewConversation}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
      />

      <Card className="grid h-full min-h-0 grid-rows-[auto_1fr_auto] overflow-hidden">
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>{activeConversationTitle ?? 'New conversation'}</CardTitle>
          </div>
        </CardHeader>

        <CardContent className="overflow-y-auto" ref={scrollRef} onScroll={handleHistoryScroll}>
          {isLoadingOlderHistory && (
            <p className="mb-3 text-center text-xs text-muted-foreground">Loading older messages...</p>
          )}
          {messagesError && (
            <p className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {messagesError}
            </p>
          )}
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
          onSendClick={() => { void handleSendClick() }}
          onStopClick={handleStopStreaming}
          onRefreshModels={handleRefreshModels}
        />
      </Card>
    </div>
  )
}
