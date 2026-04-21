import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MessageList } from './message-list'
import type { ChatMessage } from './chat-types'

function makeMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: 'default content',
    ...overrides,
  }
}

describe('MessageList', () => {
  it('renders messages in the same order they are provided', () => {
    const messages: ChatMessage[] = [
      makeMessage({ id: '1', role: 'user', content: 'first' }),
      makeMessage({ id: '2', role: 'assistant', content: 'second' }),
      makeMessage({ id: '3', role: 'user', content: 'third' }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    const firstNode = screen.getByText('first')
    const secondNode = screen.getByText('second')
    const thirdNode = screen.getByText('third')

    expect(firstNode.compareDocumentPosition(secondNode)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(secondNode.compareDocumentPosition(thirdNode)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)

    expect(container.querySelectorAll('.flex.gap-3')).toHaveLength(3)
  })

  it('renders user content as plain text and assistant content as markdown', () => {
    const messages: ChatMessage[] = [
      makeMessage({
        id: 'u-1',
        role: 'user',
        content: '**user text should stay literal**',
      }),
      makeMessage({
        id: 'a-1',
        role: 'assistant',
        content: '**assistant text should be bold**',
      }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    expect(screen.getByText('**user text should stay literal**')).toBeInTheDocument()
    expect(screen.getByText('assistant text should be bold').tagName).toBe('STRONG')

    const wrappers = container.querySelectorAll('.flex.gap-3')
    expect(wrappers[0]).toHaveClass('justify-end')
    expect(wrappers[1]).toHaveClass('justify-start')
  })

  it('supports GFM markdown for assistant messages', () => {
    const messages: ChatMessage[] = [
      makeMessage({
        id: 'a-2',
        role: 'assistant',
        content: '- alpha\n- beta\n\n[repo](https://example.com)',
      }),
    ]

    render(<MessageList messages={messages} />)

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('alpha')
    expect(items[1]).toHaveTextContent('beta')

    const link = screen.getByRole('link', { name: 'repo' })
    expect(link).toHaveAttribute('href', 'https://example.com')
  })

  it('shows reasoning details and auto-opens for streaming assistant message', () => {
    const messages: ChatMessage[] = [
      makeMessage({
        id: '__streaming__',
        role: 'assistant',
        content: 'partial answer',
        reasoning: 'thinking...',
      }),
      makeMessage({
        id: 'a-closed',
        role: 'assistant',
        content: 'complete answer',
        reasoning: 'done thinking',
      }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    const detailsElements = container.querySelectorAll('details')
    expect(detailsElements).toHaveLength(2)
    expect(detailsElements[0]).toHaveAttribute('open')
    expect(detailsElements[1]).not.toHaveAttribute('open')

    expect(screen.getByText('thinking...')).toBeInTheDocument()
    expect(screen.getByText('done thinking')).toBeInTheDocument()
  })

  it('renders an empty list without message bubbles', () => {
    const { container } = render(<MessageList messages={[]} />)

    expect(container.querySelectorAll('.flex.gap-3')).toHaveLength(0)
    expect(container.firstElementChild).toHaveClass('space-y-4', 'py-6')
  })
})
