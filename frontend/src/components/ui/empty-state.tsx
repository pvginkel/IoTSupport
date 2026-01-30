import * as React from 'react'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
  'data-testid'?: string
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  'data-testid': testId
}: EmptyStateProps) {
  return (
    <div
      className={cn('flex flex-col items-center justify-center p-8 text-center', className)}
      data-testid={testId}
    >
      {icon && <div className="mb-4 text-muted-foreground">{icon}</div>}
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      {description && <p className="mt-2 text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
