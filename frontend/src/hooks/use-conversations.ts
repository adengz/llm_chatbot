import { useEffect, useMemo, useState } from 'react'

import {
  deleteConversationConversationsConversationIdDelete,
  listConversationsConversationsGet,
  renameConversationConversationsConversationIdPatch,
} from '../client/sdk.gen'
import type { Conversation as ApiConversation } from '../client/types.gen'

type UseConversationsResult = {
  conversations: ApiConversation[]
  activeConversationId: string | null
  activeConversationTitle: string | null
  isConversationsLoading: boolean
  conversationsError: string | null
  setActiveConversationId: (value: string | null) => void
  refreshConversations: (failureMessage: string) => Promise<void>
  renameConversation: (conversationId: string, newTitle: string) => Promise<void>
  deleteConversation: (conversationId: string) => Promise<void>
}

export function useConversations(): UseConversationsResult {
  const [conversations, setConversations] = useState<ApiConversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [isConversationsLoading, setIsConversationsLoading] = useState(false)
  const [conversationsError, setConversationsError] = useState<string | null>(null)

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

  const activeConversationTitle = useMemo(() => {
    return conversations.find((conversation) => conversation.conversation_id === activeConversationId)?.title ?? null
  }, [activeConversationId, conversations])

  const refreshConversations = async (failureMessage: string) => {
    const response = await listConversationsConversationsGet()

    if (response.error || !Array.isArray(response.data)) {
      setConversationsError(failureMessage)
      return
    }

    setConversations(response.data)
    setConversationsError(null)
  }

  const renameConversation = async (conversationId: string, newTitle: string) => {
    await renameConversationConversationsConversationIdPatch({
      path: { conversation_id: conversationId },
      body: { title: newTitle },
    })
    setConversations((prev) =>
      prev.map((c) => (c.conversation_id === conversationId ? { ...c, title: newTitle } : c)),
    )
  }

  const deleteConversation = async (conversationId: string) => {
    await deleteConversationConversationsConversationIdDelete({
      path: { conversation_id: conversationId },
    })

    setConversations((prev) => prev.filter((c) => c.conversation_id !== conversationId))
    setActiveConversationId((prev) => (prev === conversationId ? null : prev))
  }

  return {
    conversations,
    activeConversationId,
    activeConversationTitle,
    isConversationsLoading,
    conversationsError,
    setActiveConversationId,
    refreshConversations,
    renameConversation,
    deleteConversation,
  }
}
