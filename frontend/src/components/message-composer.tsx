import { Check, ChevronRight, RefreshCw, SendHorizontal, Square, Globe } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from './ui/button'
import { Textarea } from './ui/textarea'
import type { ModelSource } from './chat-types'

type MessageComposerProps = {
  draft: string
  modelSource: ModelSource
  model: string
  modelOptionsBySource: Record<ModelSource, string[]>
  isModelOptionsLoading: boolean
  modelOptionsError: string | null
  webAccess: boolean
  onDraftChange: (value: string) => void
  onModelSourceChange: (value: ModelSource) => void
  onModelChange: (value: string) => void
  onWebAccessChange: (value: boolean) => void
  onSendClick: () => void
  onStopClick: () => void
  onRefreshModels: () => void
  isStreaming: boolean
}

export function MessageComposer({
  draft,
  modelSource,
  model,
  modelOptionsBySource,
  isModelOptionsLoading,
  modelOptionsError,
  webAccess,
  onDraftChange,
  onModelSourceChange,
  onModelChange,
  onWebAccessChange,
  onSendClick,
  onStopClick,
  onRefreshModels,
  isStreaming,
}: MessageComposerProps) {
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false)
  const [pendingSource, setPendingSource] = useState<ModelSource>(modelSource)
  const [modelFilter, setModelFilter] = useState('')
  const pickerRef = useRef<HTMLDivElement>(null)

  const allModelOptions = modelOptionsBySource[pendingSource] ?? []
  const modelOptions = modelFilter
    ? allModelOptions.filter((m) => m.toLowerCase().includes(modelFilter.toLowerCase()))
    : allModelOptions
  const canSend = draft.trim().length > 0

  const openPicker = () => {
    setIsModelPickerOpen(true)
    setPendingSource(modelSource)
    setModelFilter('')
  }

  const closePicker = () => {
    setIsModelPickerOpen(false)
    setModelFilter('')
  }

  useEffect(() => {
    if (!isModelPickerOpen) return

    const handleMouseDown = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        closePicker()
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closePicker()
    }

    document.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isModelPickerOpen])

  const handleModelSelected = (selectedModel: string) => {
    onModelSourceChange(pendingSource)
    onModelChange(selectedModel)
    closePicker()
  }

  return (
    <div className="border-t border-border/60 bg-card p-4">
      {modelOptionsError && (
        <p className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {modelOptionsError}
        </p>
      )}

      <div className="mb-3">
        <Textarea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              if (!isStreaming && canSend) {
                onSendClick()
              }
            }
          }}
          placeholder="Send a message"
          className="min-h-24"
        />
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <div className="relative w-60 max-w-full" ref={pickerRef}>
          <button
            type="button"
            className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 text-left"
            onClick={openPicker}
            aria-haspopup="menu"
            aria-expanded={isModelPickerOpen}
          >
            <span className="truncate text-sm">{model || 'Select model'}</span>
            <ChevronRight className={`size-4 text-muted-foreground transition-transform ${isModelPickerOpen ? 'rotate-90' : ''}`} />
          </button>

          {isModelPickerOpen && (
            <div className="absolute bottom-full left-0 z-20 mb-2 flex w-full flex-col rounded-md border border-border bg-popover p-1 shadow-lg">
              <div className="flex items-center justify-between px-2 py-1">
                <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
                  Select Model
                </p>
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground disabled:opacity-40"
                  aria-label="Refresh models"
                  disabled={isModelOptionsLoading}
                  onClick={onRefreshModels}
                >
                  <RefreshCw className={`size-3 ${isModelOptionsLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>

              <div className="px-1 pb-1">
                <input
                  type="text"
                  className="h-8 w-full rounded border border-input bg-background px-2 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  placeholder="Filter models…"
                  value={modelFilter}
                  onChange={(e) => setModelFilter(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') {
                      closePicker()
                      return
                    }
                    e.stopPropagation()
                  }}
                  autoFocus
                />
              </div>

              <div className="max-h-60 overflow-y-auto overflow-x-hidden">
                {isModelOptionsLoading && (
                  <p className="px-2 py-4 text-center text-xs text-muted-foreground">Loading models...</p>
                )}
                {!isModelOptionsLoading && modelOptions.length === 0 && (
                  <p className="px-2 py-4 text-center text-xs text-muted-foreground">
                    {modelFilter ? 'No models match filter' : 'No models available'}
                  </p>
                )}
                {modelOptions.map((modelName) => (
                  <button
                    key={modelName}
                    type="button"
                    className={`group flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm transition-colors hover:bg-muted ${
                      model === modelName ? 'bg-primary/5 font-medium' : ''
                    }`}
                    onClick={() => handleModelSelected(modelName)}
                  >
                    <span className="truncate">{modelName}</span>
                    {model === modelName && <Check className="size-4 shrink-0 text-primary" />}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <Button
          className={`h-9 w-9 shrink-0 items-center justify-center p-0 ${
            webAccess
              ? 'bg-primary/10 text-primary border-primary/30'
              : 'bg-transparent text-muted-foreground border-input'
          }`}
          variant="outline"
          type="button"
          onClick={() => onWebAccessChange(!webAccess)}
          title="Web Access"
        >
          <Globe className={`size-4 ${webAccess ? 'text-primary' : 'text-muted-foreground'}`} />
        </Button>

        <Button
          className="h-9 w-9 shrink-0"
          size="icon"
          type="button"
          aria-label={isStreaming ? 'Stop streaming response' : 'Send message'}
          title={isStreaming ? 'Stop streaming response' : 'Send message'}
          onClick={isStreaming ? onStopClick : onSendClick}
          disabled={!isStreaming && !canSend}
        >
          {isStreaming ? <Square className="size-4" /> : <SendHorizontal className="size-4" />}
        </Button>
      </div>
    </div>
  )
}
