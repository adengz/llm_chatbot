import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Conversation as ApiConversation } from '../client/types.gen'
import { ConversationSidebar } from './conversation-sidebar'

type SidebarOverrides = Partial<Parameters<typeof ConversationSidebar>[0]>

function makeConversation(overrides: Partial<ApiConversation>): ApiConversation {
  return {
    user_id: 1,
    conversation_id: 'conv-1',
    title: 'Default conversation',
    ...overrides,
  }
}

function renderSidebar(overrides: SidebarOverrides = {}) {
  const onSelectConversation = vi.fn()
  const onStartNewConversation = vi.fn()
  const onRenameConversation = vi.fn().mockResolvedValue(undefined)
  const onDeleteConversation = vi.fn().mockResolvedValue(undefined)

  const props = {
    conversations: [makeConversation({ conversation_id: 'conv-1', title: 'Alpha' })],
    activeConversationId: 'conv-1',
    isLoading: false,
    error: null,
    isStreaming: false,
    onSelectConversation,
    onStartNewConversation,
    onRenameConversation,
    onDeleteConversation,
    ...overrides,
  }

  const utils = render(<ConversationSidebar {...props} />)
  return {
    ...utils,
    props,
    onSelectConversation: props.onSelectConversation,
    onStartNewConversation: props.onStartNewConversation,
    onRenameConversation: props.onRenameConversation,
    onDeleteConversation: props.onDeleteConversation,
  }
}

describe('ConversationSidebar', () => {
  it('allows selecting a conversation when not streaming', async () => {
    const user = userEvent.setup()
    const { onSelectConversation } = renderSidebar()

    await user.click(screen.getByRole('button', { name: /alpha/i }))

    expect(onSelectConversation).toHaveBeenCalledWith('conv-1')
  })

  it('disables new and select actions while streaming', async () => {
    const user = userEvent.setup()
    const { onStartNewConversation, onSelectConversation } = renderSidebar({
      isStreaming: true,
    })

    const newButton = screen.getByRole('button', { name: 'Start new conversation' })
    const selectButton = screen.getByRole('button', { name: /alpha/i })

    expect(newButton).toBeDisabled()
    expect(selectButton).toBeDisabled()

    await user.click(newButton)
    await user.click(selectButton)

    expect(onStartNewConversation).not.toHaveBeenCalled()
    expect(onSelectConversation).not.toHaveBeenCalled()
  })

  it('supports rename via double click and Enter commit', async () => {
    const user = userEvent.setup()
    const { onRenameConversation } = renderSidebar()

    await user.dblClick(screen.getByText('Alpha'))

    const input = screen.getByDisplayValue('Alpha')
    await user.clear(input)
    await user.type(input, 'Renamed thread')
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(onRenameConversation).toHaveBeenCalledWith('conv-1', 'Renamed thread')
    })
    expect(screen.queryByDisplayValue('Renamed thread')).not.toBeInTheDocument()
  })

  it('does not rename when Escape is pressed', async () => {
    const user = userEvent.setup()
    const { onRenameConversation } = renderSidebar()

    await user.dblClick(screen.getByText('Alpha'))

    const input = screen.getByDisplayValue('Alpha')
    await user.type(input, ' updated')
    fireEvent.keyDown(input, { key: 'Escape' })

    expect(onRenameConversation).not.toHaveBeenCalled()
    expect(screen.queryByDisplayValue(/Alpha updated/i)).not.toBeInTheDocument()
  })

  it('does not call rename when trimmed title is unchanged', async () => {
    const user = userEvent.setup()
    const { onRenameConversation } = renderSidebar()

    await user.dblClick(screen.getByText('Alpha'))

    const input = screen.getByDisplayValue('Alpha')
    await user.clear(input)
    await user.type(input, '  Alpha   ')
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(screen.queryByDisplayValue('  Alpha   ')).not.toBeInTheDocument()
    })
    expect(onRenameConversation).not.toHaveBeenCalled()
  })

  it('shows pending delete state until async delete resolves', async () => {
    const user = userEvent.setup()

    let resolveDelete: (() => void) | null = null
    const deletePromise = new Promise<void>((resolve) => {
      resolveDelete = resolve
    })

    const { onDeleteConversation } = renderSidebar({
      onDeleteConversation: vi.fn().mockImplementation(() => deletePromise),
    })

    await user.click(screen.getByRole('button', { name: 'Delete conversation' }))

    const row = screen.getByText('Alpha').closest('div.group')
    expect(row).toHaveClass('opacity-40', 'pointer-events-none')
    expect(onDeleteConversation).toHaveBeenCalledWith('conv-1')

    resolveDelete?.()
    await waitFor(() => {
      expect(row).not.toHaveClass('opacity-40')
    })
  })

  it('renders loading, empty, and error states', () => {
    const { rerender, props } = renderSidebar({ conversations: [], isLoading: true })

    expect(screen.getByText('Loading conversations...')).toBeInTheDocument()

    rerender(
      <ConversationSidebar
        {...props}
        conversations={[]}
        isLoading={false}
        error={null}
      />,
    )
    expect(screen.getByText('No conversations yet.')).toBeInTheDocument()

    rerender(
      <ConversationSidebar
        {...props}
        conversations={[]}
        isLoading={false}
        error={'Failed to load conversations.'}
      />,
    )
    expect(screen.getByText('Failed to load conversations.')).toBeInTheDocument()
  })
})
