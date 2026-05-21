import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useChatScroll } from './use-chat-scroll'

type ScrollContainer = {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

function makeScrollRef(container: ScrollContainer) {
  return {
    current: container as unknown as HTMLDivElement,
  }
}

describe('useChatScroll', () => {
  it('keeps auto-scrolling when user was near bottom before streamed growth', () => {
    const container: ScrollContainer = {
      scrollTop: 1200,
      scrollHeight: 2000,
      clientHeight: 700,
    }
    // Initial gap is 100px, so chat should stay sticky to bottom.
    const scrollRef = makeScrollRef(container)

    const { result } = renderHook(() => useChatScroll({ scrollRef }))

    result.current.observeScrollPosition()

    // Simulate a large append (tool calls + tool output + content).
    container.scrollHeight = 2800
    result.current.syncAfterMessagesChange()

    expect(container.scrollTop).toBe(2800)
  })

  it('does not auto-scroll when user has scrolled away from bottom', () => {
    const container: ScrollContainer = {
      scrollTop: 400,
      scrollHeight: 2000,
      clientHeight: 700,
    }
    // Initial gap is 900px, so user opted out of sticky bottom.
    const scrollRef = makeScrollRef(container)

    const { result } = renderHook(() => useChatScroll({ scrollRef }))

    result.current.observeScrollPosition()

    container.scrollHeight = 2600
    result.current.syncAfterMessagesChange()

    expect(container.scrollTop).toBe(400)
  })

  it('force-scrolls and keeps sticking until user scrolls away', () => {
    const container: ScrollContainer = {
      scrollTop: 250,
      scrollHeight: 1200,
      clientHeight: 700,
    }
    const scrollRef = makeScrollRef(container)

    const { result } = renderHook(() => useChatScroll({ scrollRef }))

    result.current.requestForceScroll()
    result.current.syncAfterMessagesChange()

    expect(container.scrollTop).toBe(1200)

    // Still sticky right after force scroll.
    container.scrollTop = 300
    container.scrollHeight = 1500
    result.current.syncAfterMessagesChange()

    expect(container.scrollTop).toBe(1500)

    // User scrolls up and we capture the new distance from bottom.
    container.scrollTop = 200
    result.current.observeScrollPosition()

    container.scrollHeight = 1800
    result.current.syncAfterMessagesChange()

    expect(container.scrollTop).toBe(200)
  })
})
