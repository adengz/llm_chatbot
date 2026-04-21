import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { MessageComposer } from './message-composer'
import type { ModelSource, ReasoningEffort } from './chat-types'

type ComposerOverrides = Partial<Parameters<typeof MessageComposer>[0]>

function renderComposer(overrides: ComposerOverrides = {}) {
  const onDraftChange = vi.fn()
  const onModelSourceChange = vi.fn()
  const onModelChange = vi.fn()
  const onReasoningEffortChange = vi.fn()
  const onSendClick = vi.fn()
  const onStopClick = vi.fn()
  const onRefreshModels = vi.fn()

  const props = {
    draft: '',
    modelSource: 'ollama_cloud' as ModelSource,
    model: 'qwen3:32b',
    modelOptionsBySource: {
      ollama_cloud: ['qwen3:32b', 'llama3.2:3b'],
      local_ollama: ['deepseek-r1:8b'],
    },
    isModelOptionsLoading: false,
    modelOptionsError: null,
    reasoningEffort: 'medium' as ReasoningEffort,
    onDraftChange,
    onModelSourceChange,
    onModelChange,
    onReasoningEffortChange,
    onSendClick,
    onStopClick,
    onRefreshModels,
    isStreaming: false,
    ...overrides,
  }

  const utils = render(<MessageComposer {...props} />)
  return {
    ...utils,
    props,
    onDraftChange,
    onModelSourceChange,
    onModelChange,
    onReasoningEffortChange,
    onSendClick,
    onStopClick,
    onRefreshModels,
  }
}

describe('MessageComposer', () => {
  it('disables send when draft is empty and enables when draft has text', () => {
    const { rerender, props } = renderComposer({ draft: '' })

    const sendButton = screen.getByRole('button', { name: 'Send message' })
    expect(sendButton).toBeDisabled()

    rerender(<MessageComposer {...props} draft={'hello'} />)
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled()
  })

  it('submits on Enter (without Shift) when send is allowed', () => {
    const { onSendClick } = renderComposer({ draft: 'Question?' })

    const input = screen.getByPlaceholderText('Send a message')
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false })

    expect(onSendClick).toHaveBeenCalledTimes(1)
  })

  it('does not submit on Enter with Shift or while streaming', () => {
    const nonStreaming = renderComposer({ draft: 'Question?' })
    const input1 = screen.getByPlaceholderText('Send a message')
    fireEvent.keyDown(input1, { key: 'Enter', shiftKey: true })
    expect(nonStreaming.onSendClick).not.toHaveBeenCalled()

    nonStreaming.unmount()

    const streaming = renderComposer({ draft: 'Question?', isStreaming: true })
    const input2 = screen.getByPlaceholderText('Send a message')
    fireEvent.keyDown(input2, { key: 'Enter', shiftKey: false })
    expect(streaming.onSendClick).not.toHaveBeenCalled()
  })

  it('switches primary action to stop while streaming', async () => {
    const user = userEvent.setup()
    const { onStopClick, onSendClick } = renderComposer({
      draft: 'Question?',
      isStreaming: true,
    })

    const stopButton = screen.getByRole('button', { name: 'Stop streaming response' })
    expect(stopButton).toBeEnabled()

    await user.click(stopButton)

    expect(onStopClick).toHaveBeenCalledTimes(1)
    expect(onSendClick).not.toHaveBeenCalled()
  })

  it('supports source + model selection flow in model picker', async () => {
    const user = userEvent.setup()
    const { onModelSourceChange, onModelChange } = renderComposer()

    await user.click(screen.getByRole('button', { name: /ollama_cloud \/ qwen3:32b/i }))

    await user.click(screen.getByRole('button', { name: 'local_ollama' }))
    await user.click(screen.getByRole('button', { name: 'deepseek-r1:8b' }))

    expect(onModelSourceChange).toHaveBeenCalledWith('local_ollama')
    expect(onModelChange).toHaveBeenCalledWith('deepseek-r1:8b')
    expect(screen.queryByRole('menu', { name: 'Model sources' })).not.toBeInTheDocument()
  })

  it('filters models and shows empty-state message for unmatched filter', async () => {
    const user = userEvent.setup()
    renderComposer()

    await user.click(screen.getByRole('button', { name: /ollama_cloud \/ qwen3:32b/i }))

    const filterInput = screen.getByPlaceholderText('Filter models…')
    await user.type(filterInput, 'not-found')

    expect(screen.getByText('No models match your filter.')).toBeInTheDocument()
  })

  it('refresh control is disabled while loading and active otherwise', async () => {
    const user = userEvent.setup()

    const loadingView = renderComposer({ isModelOptionsLoading: true })
    await user.click(screen.getByRole('button', { name: /ollama_cloud \/ qwen3:32b/i }))
    const loadingRefresh = screen.getByRole('button', { name: 'Refresh models' })
    expect(loadingRefresh).toBeDisabled()
    loadingView.unmount()

    const readyView = renderComposer({ isModelOptionsLoading: false })
    await user.click(screen.getByRole('button', { name: /ollama_cloud \/ qwen3:32b/i }))
    const readyRefresh = screen.getByRole('button', { name: 'Refresh models' })
    expect(readyRefresh).toBeEnabled()
    await user.click(readyRefresh)

    expect(readyView.onRefreshModels).toHaveBeenCalledTimes(1)
  })
})
