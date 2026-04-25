import { useEffect, useMemo, useState } from 'react'

import { listModelsModelsGet } from '../client/sdk.gen'
import type { ModelSource } from '../components/chat-types'

type UseModelCatalogResult = {
  modelSource: ModelSource
  model: string
  modelOptionsBySource: Record<ModelSource, string[]>
  isModelOptionsLoading: boolean
  modelOptionsError: string | null
  setModelSource: (value: ModelSource) => void
  setModel: (value: string) => void
  refreshModels: () => void
}

export function useModelCatalog(
  initialModelSource: ModelSource,
  initialModel: string,
): UseModelCatalogResult {
  const [selectedModelSource, setSelectedModelSource] = useState<ModelSource>(initialModelSource)
  const [selectedModel, setSelectedModel] = useState(initialModel)
  const [modelOptionsBySource, setModelOptionsBySource] = useState<Record<ModelSource, string[]>>({})
  const [isModelOptionsLoading, setIsModelOptionsLoading] = useState(false)
  const [modelOptionsError, setModelOptionsError] = useState<string | null>(null)
  const [modelOptionsRefreshKey, setModelOptionsRefreshKey] = useState(0)

  useEffect(() => {
    let isCancelled = false

    const loadModels = async () => {
      setIsModelOptionsLoading(true)

      const { data, error } = await listModelsModelsGet()

      if (isCancelled) {
        return
      }

      if (error || !data) {
        setModelOptionsBySource({})
        setModelOptionsError('Failed to load models from backend. Model list is unavailable.')
        setIsModelOptionsLoading(false)
        return
      }

      let normalizedModelOptions: Record<string, string[]> = {}

      if (Array.isArray(data)) {
        // Handle list format: map to a default 'ollama_cloud' source
        normalizedModelOptions = {
          ollama_cloud: data.filter(
            (value): value is string => typeof value === 'string' && value.trim().length > 0,
          ),
        }
      } else if (typeof data === 'object') {
        // Handle dictionary format: { source: [models] }
        normalizedModelOptions = Object.entries(data).reduce<Record<string, string[]>>(
          (acc, [source, models]) => {
            if (!Array.isArray(models)) {
              return acc
            }

            const validModels = models.filter(
              (value): value is string => typeof value === 'string' && value.trim().length > 0,
            )

            if (validModels.length > 0) {
              acc[source] = Array.from(new Set(validModels))
            }

            return acc
          },
          {},
        )
      }

      if (Object.keys(normalizedModelOptions).length > 0) {
        setModelOptionsBySource(normalizedModelOptions)
        setModelOptionsError(null)
      } else {
        setModelOptionsBySource({})
        setModelOptionsError('No models returned from backend.')
      }

      setIsModelOptionsLoading(false)
    }

    void loadModels()

    return () => {
      isCancelled = true
    }
  }, [modelOptionsRefreshKey])

  const { modelSource, model } = useMemo(() => {
    const availableSources = Object.keys(modelOptionsBySource)

    if (availableSources.length === 0) {
      return {
        modelSource: selectedModelSource,
        model: selectedModel,
      }
    }

    const resolvedSource = availableSources.includes(selectedModelSource)
      ? selectedModelSource
      : availableSources[0]
    const modelsForSource = modelOptionsBySource[resolvedSource] ?? []
    const resolvedModel = modelsForSource.includes(selectedModel)
      ? selectedModel
      : (modelsForSource[0] ?? '')

    return {
      modelSource: resolvedSource,
      model: resolvedModel,
    }
  }, [modelOptionsBySource, selectedModel, selectedModelSource])

  const refreshModels = () => {
    setModelOptionsRefreshKey((k) => k + 1)
  }

  return {
    modelSource,
    model,
    modelOptionsBySource,
    isModelOptionsLoading,
    modelOptionsError,
    setModelSource: setSelectedModelSource,
    setModel: setSelectedModel,
    refreshModels,
  }
}
