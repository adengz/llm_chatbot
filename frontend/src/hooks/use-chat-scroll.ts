import { useCallback, useRef, type RefObject } from 'react'

type UseChatScrollParams = {
  scrollRef: RefObject<HTMLDivElement | null>
}

type UseChatScrollResult = {
  requestForceScroll: () => void
  captureScrollAnchor: () => void
  restoreScrollAnchor: () => void
  syncAfterMessagesChange: () => void
}

export function useChatScroll({ scrollRef }: UseChatScrollParams): UseChatScrollResult {
  const forceScrollRef = useRef(false)
  const anchorRef = useRef<{ top: number; height: number } | null>(null)

  const syncAfterMessagesChange = useCallback(() => {
    const el = scrollRef.current
    if (!el) return

    if (forceScrollRef.current) {
      forceScrollRef.current = false
      el.scrollTop = el.scrollHeight
      return
    }

    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150
    if (isNearBottom) {
      el.scrollTop = el.scrollHeight
    }
  }, [scrollRef])

  const requestForceScroll = () => {
    forceScrollRef.current = true
  }

  const captureScrollAnchor = () => {
    const container = scrollRef.current
    if (!container) {
      anchorRef.current = null
      return
    }

    anchorRef.current = {
      top: container.scrollTop,
      height: container.scrollHeight,
    }
  }

  const restoreScrollAnchor = () => {
    const anchor = anchorRef.current
    if (!anchor) {
      return
    }

    requestAnimationFrame(() => {
      const container = scrollRef.current
      if (!container) {
        return
      }

      const currentHeight = container.scrollHeight
      container.scrollTop = currentHeight - anchor.height + anchor.top
      anchorRef.current = null
    })
  }

  return {
    requestForceScroll,
    captureScrollAnchor,
    restoreScrollAnchor,
    syncAfterMessagesChange,
  }
}