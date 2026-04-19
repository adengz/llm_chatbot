import { Check, ChevronLeft, ChevronRight, SendHorizontal, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '../ui/button'
import { Textarea } from '../ui/textarea'
import type { ModelSource, ReasoningEffort } from './chat-types'

type ChatComposerProps = {
  draft: string
  modelSource: ModelSource
  model: string
  reasoningEffort: ReasoningEffort
  onDraftChange: (value: string) => void
  onModelSourceChange: (value: ModelSource) => void
  onModelChange: (value: string) => void
  onReasoningEffortChange: (value: ReasoningEffort) => void
  onPromptClick: () => void
  onSendClick: () => void
}

export function ChatComposer({
  draft,
  modelSource,
  model,
  reasoningEffort,
  onDraftChange,
  onModelSourceChange,
  onModelChange,
  onReasoningEffortChange,
  onPromptClick,
  onSendClick,
}: ChatComposerProps) {
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false)
  const [pickerStep, setPickerStep] = useState<'source' | 'model'>('source')
  const [pendingSource, setPendingSource] = useState<ModelSource>(modelSource)

  const modelOptionsBySource = useMemo<Record<ModelSource, string[]>>(
    () => ({
      ollama_cloud: ['qwen3:32b', 'llama3.1:8b'],
      ollama_local: ['llama3.1:8b'],
    }),
    [],
  )

  const modelOptions = modelOptionsBySource[pendingSource] ?? []

  const openPicker = () => {
    setIsModelPickerOpen(true)
    setPickerStep('source')
    setPendingSource(modelSource)
  }

  const closePicker = () => {
    setIsModelPickerOpen(false)
    setPickerStep('source')
  }

  const handleSourceSelected = (source: ModelSource) => {
    setPendingSource(source)
    setPickerStep('model')
  }

  const handleModelSelected = (selectedModel: string) => {
    onModelSourceChange(pendingSource)
    onModelChange(selectedModel)
    closePicker()
  }

  return (
    <div className="border-t border-border/60 bg-card p-4">
      <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">Model</span>
          <div className="relative"
          >
            <button
              type="button"
              className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 text-left"
              onClick={openPicker}
              aria-haspopup="menu"
              aria-expanded={isModelPickerOpen}
            >
              <span className="truncate">{`${modelSource} / ${model}`}</span>
              <ChevronRight className="size-4 text-muted-foreground" />
            </button>

            {isModelPickerOpen && (
              <div className="absolute z-20 mt-2 w-full rounded-md border border-border bg-popover p-1 shadow-lg">
                {pickerStep === 'source' ? (
                  <div className="space-y-1" role="menu" aria-label="Model sources">
                    <p className="px-2 py-1 text-xs text-muted-foreground">
                      Select model source
                    </p>
                    {(Object.keys(modelOptionsBySource) as ModelSource[]).map((source) => (
                      <button
                        key={source}
                        type="button"
                        className="flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm hover:bg-muted"
                        onClick={() => handleSourceSelected(source)}
                      >
                        <span>{source}</span>
                        <ChevronRight className="size-4 text-muted-foreground" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-1" role="menu" aria-label={`Models under ${pendingSource}`}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-xs text-muted-foreground hover:bg-muted"
                      onClick={() => setPickerStep('source')}
                    >
                      <ChevronLeft className="size-3" />
                      Back to sources
                    </button>
                    {modelOptions.map((modelName) => (
                      <button
                        key={modelName}
                        type="button"
                        className="flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm hover:bg-muted"
                        onClick={() => handleModelSelected(modelName)}
                      >
                        <span>{modelName}</span>
                        {modelSource === pendingSource && model === modelName && (
                          <Check className="size-4 text-primary" />
                        )}
                      </button>
                    ))}
                  </div>
                )}

                <button
                  type="button"
                  className="mt-1 w-full rounded-sm px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                  onClick={closePicker}
                >
                  Close
                </button>
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
