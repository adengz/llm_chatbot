import { useCallback, useRef, type RefObject } from 'react'

type UseChatScrollParams = {
  scrollRef: RefObject<HTMLDivElement | null>
}

const STICKY_BOTTOM_THRESHOLD_PX = 150

type UseChatScrollResult = {
  requestForceScroll: () => void
  observeScrollPosition: () => void
  captureScrollAnchor: () => void
  restoreScrollAnchor: () => void
  syncAfterMessagesChange: () => void
}

export function useChatScroll({ scrollRef }: UseChatScrollParams): UseChatScrollResult {
  const forceScrollRef = useRef(false)
  const anchorRef = useRef<{ top: number; height: number } | null>(null)
  const bottomGapRef = useRef(0)

  const updateBottomGap = useCallback(() => {
    const container = scrollRef.current
    if (!container) {
      return
    }

    bottomGapRef.current = container.scrollHeight - container.scrollTop - container.clientHeight
  }, [scrollRef])

  const syncAfterMessagesChange = useCallback(() => {
    const el = scrollRef.current
    if (!el) return

    if (forceScrollRef.current) {
      forceScrollRef.current = false
      el.scrollTop = el.scrollHeight
      bottomGapRef.current = 0
      return
    }

    // Keep following stream updates while the user remains near the bottom.
    if (bottomGapRef.current <= STICKY_BOTTOM_THRESHOLD_PX) {
      el.scrollTop = el.scrollHeight
      bottomGapRef.current = 0
      return
    }

    updateBottomGap()
  }, [scrollRef, updateBottomGap])

  const requestForceScroll = () => {
    forceScrollRef.current = true
  }

  const observeScrollPosition = () => {
    updateBottomGap()
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
    observeScrollPosition,
    captureScrollAnchor,
    restoreScrollAnchor,
    syncAfterMessagesChange,
  }
}