import { useEffect, useRef, useState } from 'react'

import { ConversationSidebar } from './conversation-sidebar'
import { MessageComposer } from './message-composer'
import { MessageList } from './message-list'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'
import { useChatStreaming } from '../hooks/use-chat-streaming'
import { useChatScroll } from '../hooks/use-chat-scroll'
import { useConversationHistory } from '../hooks/use-conversation-history'
import { useConversations } from '../hooks/use-conversations'
import { useModelCatalog } from '../hooks/use-model-catalog'

export function ChatModule() {
  const [draft, setDraft] = useState('')
  const [webAccess, setWebAccess] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const {
    requestForceScroll,
    captureScrollAnchor,
    restoreScrollAnchor,
    syncAfterMessagesChange,
  } = useChatScroll({
    scrollRef,
  })

  const {
    conversations,
    activeConversationId,
    activeConversationTitle,
    isConversationsLoading,
    conversationsError,
    setActiveConversationId,
    refreshConversations,
    renameConversation,
    deleteConversation,
  } = useConversations()

  const {
    modelSource,
    model,
    modelOptionsBySource,
    isModelOptionsLoading,
    modelOptionsError,
    setModelSource,
    setModel,
    refreshModels,
  } = useModelCatalog('ollama_cloud', 'qwen3:32b')

  const {
    messages,
    messagesError,
    isLoadingOlderHistory,
    setMessages,
    setMessagesError,
    clearHistory,
    markSkipNextHistoryLoad,
    handleHistoryScroll,
  } = useConversationHistory({
    conversationId: activeConversationId,
    scrollRef,
    captureScrollAnchor,
    restoreScrollAnchor,
  })

  const { isStreaming, sendMessage, stopStreaming } = useChatStreaming({
    setMessages,
    setMessagesError,
    onMetadata: (nextConversationId, startedFromNewConversation) => {
      if (startedFromNewConversation) {
        markSkipNextHistoryLoad()
        void refreshConversations('Failed to refresh conversations.')
      }
      setActiveConversationId(nextConversationId)
    },
  })

  useEffect(() => {
    syncAfterMessagesChange()
  }, [messages, syncAfterMessagesChange])

  const handleSelectConversation = (nextConversationId: string) => {
    if (isStreaming || nextConversationId === activeConversationId) {
      return
    }

    setActiveConversationId(nextConversationId)
  }

  const handleStartNewConversation = () => {
    if (isStreaming) {
      return
    }

    setActiveConversationId(null)
    clearHistory()
  }

  const handleDeleteConversation = async (targetId: string) => {
    const wasActive = activeConversationId === targetId
    await deleteConversation(targetId)

    if (wasActive) {
      clearHistory()
    }
  }

  const handleSendClick = () => {
    const content = draft.trim()
    if (!content) {
      return
    }

    requestForceScroll()
    const started = sendMessage({
      content,
      conversationId: activeConversationId,
      modelSource,
      model,
      webAccess,
    })

    if (started) {
      setDraft('')
    }
  }

  return (
    <div className="box-border grid h-dvh grid-cols-[280px_minmax(0,1fr)] grid-rows-[minmax(0,1fr)] gap-4 overflow-hidden bg-background p-4 text-foreground">
      <ConversationSidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        isLoading={isConversationsLoading}
        error={conversationsError}
        isStreaming={isStreaming}
        onSelectConversation={handleSelectConversation}
        onStartNewConversation={handleStartNewConversation}
        onRenameConversation={renameConversation}
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
          <MessageList messages={messages} />
        </CardContent>

        <MessageComposer
          draft={draft}
          modelSource={modelSource}
          model={model}
          modelOptionsBySource={modelOptionsBySource}
          isModelOptionsLoading={isModelOptionsLoading}
          modelOptionsError={modelOptionsError}
          webAccess={webAccess}
          isStreaming={isStreaming}
          onDraftChange={setDraft}
          onModelSourceChange={setModelSource}
          onModelChange={setModel}
          onWebAccessChange={setWebAccess}
          onSendClick={handleSendClick}
          onStopClick={stopStreaming}
          onRefreshModels={refreshModels}
        />
      </Card>
    </div>
  )
}
