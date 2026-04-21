import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatModule } from './chat-module'

const sdkMocks = vi.hoisted(() => ({
  deleteConversationConversationsConversationIdDelete: vi.fn(),
  listConversationsConversationsGet: vi.fn(),
  listLlmsModelsGet: vi.fn(),
  listMessagesConversationsConversationIdMessagesGet: vi.fn(),
  renameConversationConversationsConversationIdPatch: vi.fn(),
}))

const streamMessageMock = vi.hoisted(() => vi.fn())

vi.mock('../client/sdk.gen', () => sdkMocks)
vi.mock('../client/stream', () => ({
  streamMessage: streamMessageMock,
}))

type StreamEvent =
  | { type: 'metadata'; conversation_id: string }
  | { type: 'reasoning'; delta: string }
  | { type: 'content'; delta: string }
  | { type: 'error'; exception: string }
  | { type: 'done' }

async function* emit(events: StreamEvent[]) {
  for (const event of events) {
    yield event
  }
}

async function* emitUntilAborted(signal?: AbortSignal) {
  yield { type: 'metadata', conversation_id: 'conv-stop' } as const
  yield { type: 'content', delta: 'Partial output' } as const

  await new Promise<void>((resolve, reject) => {
    if (!signal) {
      resolve()
      return
    }

    const abortError = new Error('Aborted')
    abortError.name = 'AbortError'

    if (signal.aborted) {
      reject(abortError)
      return
    }

    signal.addEventListener('abort', () => reject(abortError), { once: true })
  })

  yield { type: 'done' } as const
}

describe('ChatModule', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    sdkMocks.listConversationsConversationsGet.mockResolvedValue({ data: [], error: undefined })
    sdkMocks.listLlmsModelsGet.mockResolvedValue({
      data: { ollama_cloud: ['qwen3:32b'] },
      error: undefined,
    })
    sdkMocks.listMessagesConversationsConversationIdMessagesGet.mockResolvedValue({
      data: [],
      error: undefined,
    })
    sdkMocks.renameConversationConversationsConversationIdPatch.mockResolvedValue({})
    sdkMocks.deleteConversationConversationsConversationIdDelete.mockResolvedValue({})
    streamMessageMock.mockImplementation(() => emit([{ type: 'done' }]))
  })

  it('shows initial backend load errors for conversations and models', async () => {
    sdkMocks.listConversationsConversationsGet.mockResolvedValueOnce({ data: undefined, error: {} })
    sdkMocks.listLlmsModelsGet.mockResolvedValueOnce({ data: undefined, error: {} })

    render(<ChatModule />)

    expect(await screen.findByText('Failed to load conversations.')).toBeInTheDocument()
    expect(
      await screen.findByText('Failed to load models from backend. Model list is unavailable.'),
    ).toBeInTheDocument()
  })

  it('handles send -> streaming updates -> done with rendered assistant output', async () => {
    const user = userEvent.setup()

    sdkMocks.listConversationsConversationsGet
      .mockResolvedValueOnce({ data: [], error: undefined })
      .mockResolvedValueOnce({
        data: [{ user_id: 1, conversation_id: 'conv-new', title: 'New conversation' }],
        error: undefined,
      })

    streamMessageMock.mockImplementation(() =>
      emit([
        { type: 'metadata', conversation_id: 'conv-new' },
        { type: 'reasoning', delta: 'drafting' },
        { type: 'content', delta: 'Hello' },
        { type: 'content', delta: ' world' },
        { type: 'done' },
      ]),
    )

    render(<ChatModule />)

    await user.type(
      screen.getByPlaceholderText('Send a message'),
      'Hi there',
    )
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    expect(await screen.findByText('Hi there')).toBeInTheDocument()
    expect(await screen.findByText('Hello world')).toBeInTheDocument()
    expect(await screen.findByText('drafting')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Stop streaming response' })).not.toBeInTheDocument()
    })

    expect(sdkMocks.listConversationsConversationsGet).toHaveBeenCalledTimes(2)
  })

  it('surfaces stream error event in message area and error banner', async () => {
    const user = userEvent.setup()

    streamMessageMock.mockImplementation(() =>
      emit([
        { type: 'metadata', conversation_id: 'conv-err' },
        { type: 'error', exception: 'model overloaded' },
      ]),
    )

    render(<ChatModule />)

    await user.type(
      screen.getByPlaceholderText('Send a message'),
      'Trigger error',
    )
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    expect(await screen.findByText('model overloaded')).toBeInTheDocument()
    expect(await screen.findByText('[Error: model overloaded]')).toBeInTheDocument()
  })

  it('aborts in-flight stream when user clicks stop', async () => {
    const user = userEvent.setup()

    streamMessageMock.mockImplementation((_, signal?: AbortSignal) => emitUntilAborted(signal))

    render(<ChatModule />)

    await user.type(
      screen.getByPlaceholderText('Send a message'),
      'Stop this response',
    )
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    expect(await screen.findByText('Partial output')).toBeInTheDocument()

    const stopButton = await screen.findByRole('button', { name: 'Stop streaming response' })
    await user.click(stopButton)

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Stop streaming response' })).not.toBeInTheDocument()
    })

    await waitFor(() => {
      const [, signal] = streamMessageMock.mock.calls[0]
      expect(signal).toBeDefined()
      expect((signal as AbortSignal).aborted).toBe(true)
    })
  })
})
