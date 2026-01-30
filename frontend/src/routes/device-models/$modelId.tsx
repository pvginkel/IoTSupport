import { createFileRoute, Link } from '@tanstack/react-router'
import { DeviceModelEditor } from '@/components/device-models/device-model-editor'
import { useDeviceModel } from '@/hooks/use-device-models'
import { Button } from '@/components/ui/button'

export const Route = createFileRoute('/device-models/$modelId')({
  component: EditDeviceModelRoute,
})

function EditDeviceModelRoute() {
  const { modelId } = Route.useParams()
  const numericId = parseInt(modelId, 10)
  const { deviceModel, isLoading, error } = useDeviceModel(isNaN(numericId) ? undefined : numericId)

  if (isNaN(numericId)) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-destructive">Invalid model ID</p>
        <Link to="/device-models">
          <Button variant="outline">Back to Device Models</Button>
        </Link>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading device model...</p>
      </div>
    )
  }

  if (error || !deviceModel) {
    const errorMessage = error?.message || 'Device model not found'
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-destructive">{errorMessage}</p>
        <Link to="/device-models">
          <Button variant="outline">Back to Device Models</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <DeviceModelEditor
        mode="edit"
        modelId={deviceModel.id}
        initialCode={deviceModel.code}
        initialName={deviceModel.name}
        initialConfigSchema={deviceModel.configSchema}
      />
    </div>
  )
}
