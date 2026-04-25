import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { MessageComposer } from './message-composer'
import type { ModelSource } from './chat-types'

type ComposerOverrides = Partial<Parameters<typeof MessageComposer>[0]>

function renderComposer(overrides: ComposerOverrides = {}) {
  const onDraftChange = vi.fn()
  const onModelSourceChange = vi.fn()
  const onModelChange = vi.fn()
  const onSendClick = vi.fn()
  const onStopClick = vi.fn()
  const onRefreshModels = vi.fn()
  const onWebAccessChange = vi.fn()

  const props = {
    draft: '',
    modelSource: 'ollama_cloud' as ModelSource,
    model: 'qwen3:32b',
    modelOptionsBySource: {
      ollama_cloud: ['qwen3:32b', 'llama3.2:3b'],
    },
    isModelOptionsLoading: false,
    modelOptionsError: null,
    webAccess: false,
    onDraftChange,
    onModelSourceChange,
    onModelChange,
    onSendClick,
    onStopClick,
    onRefreshModels,
    onWebAccessChange,
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
    onSendClick,
    onStopClick,
    onRefreshModels,
    onWebAccessChange,
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

  it('switches to single-level model picker and filters list', async () => {
    const user = userEvent.setup()
    const { onModelChange } = renderComposer()

    const pickerButton = screen.getByRole('button', { name: /qwen3:32b/i })
    await user.click(pickerButton)

    const filterInput = screen.getByPlaceholderText('Filter models…')
    expect(filterInput).toBeInTheDocument()

    await user.type(filterInput, 'llama')
    
    // The dropdown list should only contain llama
    const modelOptions = screen.getAllByRole('button').filter(b => 
      b.className.includes('group') && b.className.includes('w-full')
    )
    expect(modelOptions.every(opt => opt.textContent?.includes('llama'))).toBe(true)
    expect(modelOptions.find(opt => opt.textContent === 'qwen3:32b')).toBeUndefined()

    const llamaOption = screen.getByText('llama3.2:3b')
    await user.click(llamaOption)

    expect(onModelChange).toHaveBeenCalledWith('llama3.2:3b')
  })

  it('toggles web access', async () => {
    const user = userEvent.setup()
    const { onWebAccessChange } = renderComposer({ webAccess: false })

    const webAccessBtn = screen.getByTitle(/Web Access/i)
    await user.click(webAccessBtn)

    expect(onWebAccessChange).toHaveBeenCalledWith(true)
  })

  it('switches primary action to stop while streaming', async () => {
    const user = userEvent.setup()
    const { onStopClick } = renderComposer({
      draft: 'Question?',
      isStreaming: true,
    })

    const stopButton = screen.getByRole('button', { name: 'Stop streaming response' })
    expect(stopButton).toBeEnabled()

    await user.click(stopButton)
    expect(onStopClick).toHaveBeenCalledTimes(1)
  })
})
