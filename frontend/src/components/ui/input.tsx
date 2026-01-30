import * as React from 'react'
import { cn } from '@/lib/utils'

type NativeInputProps = React.ComponentPropsWithoutRef<"input">

interface InputProps extends NativeInputProps {
  error?: string
  invalid?: boolean
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({
    error,
    className,
    invalid,
    ...props
  }, ref) => {
    const baseClasses = 'flex h-10 w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

    const hasError = error || invalid

    return (
      <div className="w-full">
        <input
          ref={ref}
          {...props}
          aria-invalid={hasError ? 'true' : undefined}
          className={cn(
            baseClasses,
            hasError ? 'border-destructive' : 'border-input',
            className
          )}
        />

        {error && (
          <p className="mt-1 text-sm text-destructive">{error}</p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'
