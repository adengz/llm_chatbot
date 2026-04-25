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

  it('shows thinking details and auto-opens for streaming assistant message', () => {
    const messages: ChatMessage[] = [
      makeMessage({
        id: '__streaming__-thinking-1',
        role: 'assistant',
        type: 'thinking',
        content: 'thinking details...',
      }),
      makeMessage({
        id: 'thinking-done',
        role: 'assistant',
        type: 'thinking',
        content: 'complete reasoning',
      }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    const detailsElements = container.querySelectorAll('details')
    expect(detailsElements).toHaveLength(2)
    // First should be open because it starts with __streaming__
    expect(detailsElements[0]).toHaveAttribute('open')
    // Second should be closed because it's finalized
    expect(detailsElements[1]).not.toHaveAttribute('open')
    
    expect(screen.getAllByText('Thinking')).toHaveLength(2)
    expect(screen.getByText('thinking details...')).toBeInTheDocument()
  })

  it('renders tool call requests and responses', () => {
    const toolCall = JSON.stringify({ name: 'get_weather', args: { city: 'London' } })
    const messages: ChatMessage[] = [
      makeMessage({
        id: 'tool-1',
        role: 'assistant',
        type: 'tool_call_req',
        content: toolCall,
      }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    expect(screen.getByText('Tool Call Request')).toBeInTheDocument()
    // Check for JSON components are rendered with key "name" and value "get_weather"
    expect(screen.getByText('"name"')).toBeInTheDocument()
    expect(screen.getByText('"get_weather"')).toBeInTheDocument()
    // Verify the structure is rendered
    expect(container.querySelector('div.font-mono')).toBeInTheDocument()
  })

  it('renders an empty list without message bubbles', () => {
    const { container } = render(<MessageList messages={[]} />)

    expect(container.querySelectorAll('.flex.gap-3')).toHaveLength(0)
    expect(container.firstElementChild).toHaveClass('space-y-4', 'py-6')
  })

  it('expands and collapses nested JSON objects', () => {
    const nestedJson = JSON.stringify({
      user: { name: 'Alice', age: 30 },
      status: 'active',
    })
    const messages: ChatMessage[] = [
      makeMessage({
        id: 'tool-1',
        role: 'assistant',
        type: 'tool_call_resp',
        content: nestedJson,
      }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    // Top level object is expanded, showing keys
    expect(screen.getByText('"user"')).toBeInTheDocument()
    expect(screen.getByText('"status"')).toBeInTheDocument()
    
    // "status" value should be visible (it's a simple string)
    expect(screen.getByText('"active"')).toBeInTheDocument()
    
    // "user" value is a nested object, should show as expandable
    const objectButtons = container.querySelectorAll('button')
    let hasUserObject = false
    for (const btn of objectButtons) {
      if (btn.textContent?.includes('Object') && btn.textContent?.includes('keys')) {
        hasUserObject = true
      }
    }
    expect(hasUserObject).toBe(true)
  })

  it('handles long string values with expand/collapse', () => {
    const longString = 'a'.repeat(150) // 150 characters, exceeds 100 char limit
    const json = JSON.stringify({ description: longString })
    const messages: ChatMessage[] = [
      makeMessage({
        id: 'tool-1',
        role: 'assistant',
        type: 'tool_call_resp',
        content: json,
      }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    // Should show preview of long string
    expect(screen.getByText('"description"')).toBeInTheDocument()

    // Should have a truncated view initially (first 100 chars + ...)
    const expandButtons = container.querySelectorAll('button')
    let stringExpandButton: HTMLElement | null = null
    for (const btn of expandButtons) {
      if (btn.textContent?.includes('...')) {
        stringExpandButton = btn
        break
      }
    }
    expect(stringExpandButton).toBeInTheDocument()
  })

  it('renders arrays with expand/collapse for complex items', () => {
    const json = JSON.stringify({
      items: [
        { id: 1, name: 'Item 1' },
        { id: 2, name: 'Item 2' },
      ],
    })
    const messages: ChatMessage[] = [
      makeMessage({
        id: 'tool-1',
        role: 'assistant',
        type: 'tool_call_resp',
        content: json,
      }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    // Top level object is expanded
    expect(screen.getByText('"items"')).toBeInTheDocument()
    
    // Array should show as expandable button since it's nested
    expect(screen.getByText(/(Array\(2\))/)).toBeInTheDocument()
    
    // The items are not shown initially since the array isn't expanded
    expect(screen.queryByText('"Item 1"')).not.toBeInTheDocument()
  })

  it('renders JSON with null, boolean, and number values', () => {
    const json = JSON.stringify({
      isActive: true,
      count: 42,
      metadata: null,
    })
    const messages: ChatMessage[] = [
      makeMessage({
        id: 'tool-1',
        role: 'assistant',
        type: 'tool_call_resp',
        content: json,
      }),
    ]

    render(<MessageList messages={messages} />)

    // Check for proper rendering of different types
    expect(screen.getByText('true')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('null')).toBeInTheDocument()
  })

  it('handles arrays with simple values compactly', () => {
    const json = JSON.stringify({
      tags: ['tag1', 'tag2', 'tag3'],
    })
    const messages: ChatMessage[] = [
      makeMessage({
        id: 'tool-1',
        role: 'assistant',
        type: 'tool_call_resp',
        content: json,
      }),
    ]

    const { container } = render(<MessageList messages={messages} />)

    // Simple arrays with 3 or fewer items should display inline without expand button
    expect(screen.getByText('"tags"')).toBeInTheDocument()
    // Should see the values inline
    expect(screen.getByText('"tag1"')).toBeInTheDocument()
    expect(screen.getByText('"tag2"')).toBeInTheDocument()
    expect(screen.getByText('"tag3"')).toBeInTheDocument()
  })
})

