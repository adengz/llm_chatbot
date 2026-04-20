import { Plus } from 'lucide-react'

import type { Conversation as ApiConversation } from '../../client/types.gen'
import { Button } from '../ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'

type ConversationSidebarProps = {
  conversations: ApiConversation[]
  activeConversationId: string | null
  isLoading: boolean
  error: string | null
  isStreaming: boolean
  onSelectConversation: (conversationId: string) => void
  onStartNewConversation: () => void
}

export function ConversationSidebar({
  conversations,
  activeConversationId,
  isLoading,
  error,
  isStreaming,
  onSelectConversation,
  onStartNewConversation,
}: ConversationSidebarProps) {
  return (
    <Card className="overflow-hidden">
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
        <CardDescription>MVP chat continuity surface</CardDescription>
      </CardHeader>

      <CardContent className="space-y-2 overflow-y-auto">
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

          return (
            <button
              key={conversation.conversation_id}
              className={`w-full rounded-lg border p-3 text-left text-sm transition ${
                isActive
                  ? 'border-primary/60 bg-muted'
                  : 'border-border/70 hover:border-primary/50 hover:bg-muted'
              }`}
              disabled={isStreaming}
              type="button"
              onClick={() => onSelectConversation(conversation.conversation_id)}
            >
              <p className="line-clamp-1 font-medium text-foreground">{conversation.title}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {isActive ? 'Active conversation' : 'Click to load history'}
              </p>
            </button>
          )
        })}
      </CardContent>
    </Card>
  )
}