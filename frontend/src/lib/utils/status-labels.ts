import type { DeviceFlashImages } from '@/hooks/use-devices'

/**
 * What Flash device says about a device's model's current firmware, for each
 * flash status.
 */
export function flashStatusLabel(images: DeviceFlashImages): string {
  switch (images.status) {
    case 'flashable':
      return `Firmware ${images.firmwareVersion} is ready to flash.`
    case 'no_firmware':
      return "This device's model has no firmware. Upload a firmware build for the model before flashing it."
    case 'no_flash_images':
      return `Firmware ${images.firmwareVersion} was stored without flash images, so it cannot be flashed in full. The model's next firmware build brings them.`
    default: {
      const unknownStatus: never = images
      throw new Error(`Unknown flash status: ${String(unknownStatus)}`)
    }
  }
}
