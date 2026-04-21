import { Plus, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'

import type { Conversation as ApiConversation } from '../../client/types.gen'
import { Button } from '../ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'

type ConversationSidebarProps = {
  conversations: ApiConversation[]
  activeConversationId: string | null
  isLoading: boolean
  error: string | null
  isStreaming: boolean
  onSelectConversation: (conversationId: string) => void
  onStartNewConversation: () => void
  onRenameConversation: (conversationId: string, newTitle: string) => Promise<void>
  onDeleteConversation: (conversationId: string) => Promise<void>
}

export function ConversationSidebar({
  conversations,
  activeConversationId,
  isLoading,
  error,
  isStreaming,
  onSelectConversation,
  onStartNewConversation,
  onRenameConversation,
  onDeleteConversation,
}: ConversationSidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const startRename = (conversation: ApiConversation) => {
    setEditingId(conversation.conversation_id)
    setEditValue(conversation.title)
    setTimeout(() => inputRef.current?.select(), 0)
  }

  const commitRename = async (conversationId: string) => {
    const trimmed = editValue.trim()
    setEditingId(null)
    if (trimmed && trimmed !== conversations.find((c) => c.conversation_id === conversationId)?.title) {
      await onRenameConversation(conversationId, trimmed)
    }
  }

  const handleDelete = async (conversationId: string) => {
    setPendingDeleteId(conversationId)
    await onDeleteConversation(conversationId)
    setPendingDeleteId(null)
  }

  return (
    <Card className="grid h-full min-h-0 grid-rows-[auto_1fr] overflow-hidden">
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Conversations</CardTitle>
          <Button
            size="icon"
            variant="outline"
            aria-label="Start new conversation"
            disabled={isStreaming}
            onClick={onStartNewConversation}
          >
            <Plus className="size-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="min-h-0 space-y-2 overflow-y-auto">
        {error && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}

        {isLoading && conversations.length === 0 && (
          <p className="text-sm text-muted-foreground">Loading conversations...</p>
        )}

        {!isLoading && conversations.length === 0 && !error && (
          <p className="text-sm text-muted-foreground">No conversations yet.</p>
        )}

        {conversations.map((conversation) => {
          const isActive = conversation.conversation_id === activeConversationId
          const isEditing = editingId === conversation.conversation_id
          const isDeleting = pendingDeleteId === conversation.conversation_id

          return (
            <div
              key={conversation.conversation_id}
              className={`group relative rounded-lg border text-sm transition ${
                isActive
                  ? 'border-primary/60 bg-muted'
                  : 'border-border/70 hover:border-primary/50 hover:bg-muted'
              } ${isDeleting ? 'opacity-40 pointer-events-none' : ''}`}
            >
              {isEditing ? (
                <div className="p-3">
                  <input
                    ref={inputRef}
                    className="w-full rounded border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void commitRename(conversation.conversation_id)
                      if (e.key === 'Escape') setEditingId(null)
                    }}
                    onBlur={() => void commitRename(conversation.conversation_id)}
                    autoFocus
                  />
                  <p className="mt-1 text-xs text-muted-foreground">Enter to save · Esc to cancel</p>
                </div>
              ) : (
                <button
                  className="w-full p-3 text-left"
                  disabled={isStreaming}
                  type="button"
                  onClick={() => onSelectConversation(conversation.conversation_id)}
                >
                  <p
                    className="line-clamp-1 pr-8 font-medium text-foreground"
                    title="Double-click to rename"
                    onDoubleClick={(e) => { e.stopPropagation(); startRename(conversation) }}
                  >
                    {conversation.title}
                  </p>
                </button>
              )}

              {!isEditing && (
                <div className="absolute right-2 top-2 hidden gap-1 group-hover:flex">
                  <button
                    type="button"
                    className="rounded p-1 text-muted-foreground hover:bg-background hover:text-destructive"
                    aria-label="Delete conversation"
                    disabled={isDeleting}
                    onClick={(e) => { e.stopPropagation(); void handleDelete(conversation.conversation_id) }}
                  >
                    <Trash2 className="size-3" />
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}