import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
  type UIEvent,
} from 'react'

import { listMessagesConversationsConversationIdMessagesGet } from '../client/sdk.gen'
import type { Message as ApiMessage } from '../client/types.gen'
import type { ChatMessage } from '../components/chat-types'

const HISTORY_PAGE_SIZE = 100

function toChatMessage(message: ApiMessage, index: number): ChatMessage {
  return {
    id: `${message.created_at ?? 'message'}-${message.role}-${index}`,
    role: message.role,
    content: message.content,
  }
}

type UseConversationHistoryParams = {
  conversationId: string | null
  scrollRef: RefObject<HTMLDivElement | null>
  captureScrollAnchor?: () => void
  restoreScrollAnchor?: () => void
}

type UseConversationHistoryResult = {
  messages: ChatMessage[]
  messagesError: string | null
  isLoadingOlderHistory: boolean
  hasMoreHistory: boolean
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>
  setMessagesError: Dispatch<SetStateAction<string | null>>
  clearHistory: () => void
  markSkipNextHistoryLoad: () => void
  handleHistoryScroll: (event: UIEvent<HTMLDivElement>) => void
}

export function useConversationHistory({
  conversationId,
  scrollRef,
  captureScrollAnchor,
  restoreScrollAnchor,
}: UseConversationHistoryParams): UseConversationHistoryResult {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [messagesError, setMessagesError] = useState<string | null>(null)
  const [historyCursor, setHistoryCursor] = useState<string | null>(null)
  const [hasMoreHistory, setHasMoreHistory] = useState(false)
  const [isLoadingOlderHistory, setIsLoadingOlderHistory] = useState(false)

  const skipNextHistoryLoadRef = useRef(false)
  const activeConversationIdRef = useRef<string | null>(null)

  useEffect(() => {
    activeConversationIdRef.current = conversationId
  }, [conversationId])

  useEffect(() => {
    if (!conversationId) {
      return
    }

    if (skipNextHistoryLoadRef.current) {
      skipNextHistoryLoadRef.current = false
      return
    }

    let isCancelled = false

    const loadHistory = async () => {
      setMessagesError(null)

      const response: { data?: ApiMessage[]; error?: unknown } =
        await listMessagesConversationsConversationIdMessagesGet({
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

  const loadOlderHistory = useCallback(async () => {
    if (!conversationId || !hasMoreHistory || isLoadingOlderHistory || !historyCursor) {
      return
    }

    const targetConversationId = conversationId
    captureScrollAnchor?.()

    setIsLoadingOlderHistory(true)

    const response: { data?: ApiMessage[]; error?: unknown } =
      await listMessagesConversationsConversationIdMessagesGet({
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
    restoreScrollAnchor?.()
  }, [
    captureScrollAnchor,
    conversationId,
    hasMoreHistory,
    historyCursor,
    isLoadingOlderHistory,
    restoreScrollAnchor,
  ])

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
  }, [conversationId, hasMoreHistory, isLoadingOlderHistory, loadOlderHistory, messages.length, scrollRef])

  const clearHistory = () => {
    setMessages([])
    setMessagesError(null)
    setHistoryCursor(null)
    setHasMoreHistory(false)
    setIsLoadingOlderHistory(false)
  }

  const markSkipNextHistoryLoad = () => {
    skipNextHistoryLoadRef.current = true
  }

  return {
    messages,
    messagesError,
    isLoadingOlderHistory,
    hasMoreHistory,
    setMessages,
    setMessagesError,
    clearHistory,
    markSkipNextHistoryLoad,
    handleHistoryScroll,
  }
}
