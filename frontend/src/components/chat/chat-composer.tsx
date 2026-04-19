import { Check, ChevronRight, RefreshCw, SendHorizontal, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '../ui/button'
import { Textarea } from '../ui/textarea'
import type { ModelSource, ReasoningEffort } from './chat-types'

type ChatComposerProps = {
  draft: string
  modelSource: ModelSource
  model: string
  modelOptionsBySource: Record<ModelSource, string[]>
  isModelOptionsLoading: boolean
  modelOptionsError: string | null
  reasoningEffort: ReasoningEffort
  onDraftChange: (value: string) => void
  onModelSourceChange: (value: ModelSource) => void
  onModelChange: (value: string) => void
  onReasoningEffortChange: (value: ReasoningEffort) => void
  onPromptClick: () => void
  onSendClick: () => void
  onRefreshModels: () => void
}

export function ChatComposer({
  draft,
  modelSource,
  model,
  modelOptionsBySource,
  isModelOptionsLoading,
  modelOptionsError,
  reasoningEffort,
  onDraftChange,
  onModelSourceChange,
  onModelChange,
  onReasoningEffortChange,
  onPromptClick,
  onSendClick,
  onRefreshModels,
}: ChatComposerProps) {
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false)
  const [pendingSource, setPendingSource] = useState<ModelSource>(modelSource)
  const [modelFilter, setModelFilter] = useState('')
  const pickerRef = useRef<HTMLDivElement>(null)

  const sourceOptions = Object.keys(modelOptionsBySource)
  const allModelOptions = modelOptionsBySource[pendingSource] ?? []
  const modelOptions = modelFilter
    ? allModelOptions.filter((m) => m.toLowerCase().includes(modelFilter.toLowerCase()))
    : allModelOptions

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

  const handleSourceSelected = (source: ModelSource) => {
    setPendingSource(source)
    setModelFilter('')
  }

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

      <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
        <label className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Model</span>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground disabled:opacity-40"
              aria-label="Refresh models"
              disabled={isModelOptionsLoading}
              onClick={onRefreshModels}
            >
              <RefreshCw className="size-3" />
            </button>
          </div>
          <div className="relative" ref={pickerRef}>
            <button
              type="button"
              className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 text-left"
              onClick={openPicker}
              aria-haspopup="menu"
              aria-expanded={isModelPickerOpen}
            >
              <span className="truncate">{model ? `${modelSource} / ${model}` : 'Select model'}</span>
              <ChevronRight className="size-4 text-muted-foreground" />
            </button>

            {isModelPickerOpen && (
              <div className="absolute bottom-full z-20 mb-2 flex rounded-md border border-border bg-popover shadow-lg">
                {/* Source panel */}
                <div className="w-44 border-r border-border/60 p-1" role="menu" aria-label="Model sources">
                  <p className="px-2 py-1 text-xs text-muted-foreground">Source</p>
                  {isModelOptionsLoading && (
                    <p className="px-2 py-2 text-xs text-muted-foreground">Loading…</p>
                  )}
                  {!isModelOptionsLoading && modelOptionsError && (
                    <p className="px-2 py-2 text-xs text-destructive">{modelOptionsError}</p>
                  )}
                  <div className="max-h-52 overflow-y-auto">
                    {sourceOptions.map((source) => (
                      <button
                        key={source}
                        type="button"
                        className={`flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm hover:bg-muted ${pendingSource === source ? 'bg-muted font-medium' : ''}`}
                        disabled={isModelOptionsLoading}
                        onClick={() => handleSourceSelected(source)}
                      >
                        <span>{source}</span>
                        <ChevronRight className="size-4 text-muted-foreground" />
                      </button>
                    ))}
                    {!isModelOptionsLoading && sourceOptions.length === 0 && (
                      <p className="px-2 py-2 text-xs text-muted-foreground">No sources available.</p>
                    )}
                  </div>
                </div>

                {/* Model panel */}
                <div className="w-52 p-1" role="menu" aria-label={`Models under ${pendingSource}`}>
                  <p className="px-2 py-1 text-xs text-muted-foreground">{pendingSource || 'Models'}</p>
                  {pendingSource && (
                    <div className="px-1 pb-1">
                      <input
                        type="text"
                        className="h-7 w-full rounded border border-input bg-background px-2 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                        placeholder="Filter models…"
                        value={modelFilter}
                        onChange={(e) => setModelFilter(e.target.value)}
                        onKeyDown={(e) => e.stopPropagation()}
                        autoFocus
                      />
                    </div>
                  )}
                  <div className="max-h-52 overflow-y-auto">
                    {modelOptions.map((modelName) => (
                      <button
                        key={modelName}
                        type="button"
                        className="flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm hover:bg-muted"
                        disabled={isModelOptionsLoading}
                        onClick={() => handleModelSelected(modelName)}
                      >
                        <span className="truncate">{modelName}</span>
                        {modelSource === pendingSource && model === modelName && (
                          <Check className="ml-2 size-4 shrink-0 text-primary" />
                        )}
                      </button>
                    ))}
                    {!isModelOptionsLoading && modelOptions.length === 0 && (
                      <p className="px-2 py-2 text-xs text-muted-foreground">
                        {!pendingSource
                          ? 'Select a source.'
                          : modelFilter
                          ? 'No models match your filter.'
                          : 'No models for this source.'}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">Reasoning</span>
          <select
            className="h-9 w-full rounded-md border border-input bg-background px-3"
            value={reasoningEffort}
            onChange={(event) => onReasoningEffortChange(event.target.value as ReasoningEffort)}
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </label>
      </div>

      <div className="flex items-end gap-2">
        <Textarea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="Ask anything about your app and API integration..."
          className="min-h-24"
        />
        <Button className="h-10 shrink-0" type="button" onClick={onPromptClick}>
          <Sparkles className="size-4" />
          Prompt
        </Button>
        <Button className="h-10 shrink-0" type="button" onClick={onSendClick}>
          <SendHorizontal className="size-4" />
          Send
        </Button>
      </div>
    </div>
  )
}
