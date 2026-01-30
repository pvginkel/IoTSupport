import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cn } from '@/lib/utils'

type NativeButtonProps = React.ComponentPropsWithoutRef<"button">

interface ButtonProps extends NativeButtonProps {
  variant?: 'default' | 'primary' | 'secondary' | 'outline' | 'ghost' | 'destructive'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: React.ReactNode
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({
    variant = 'default',
    size = 'md',
    loading = false,
    icon,
    className,
    onClick,
    disabled,
    type = 'button',
    asChild = false,
    children,
    ...props
  }, ref) => {
    const Comp = asChild ? Slot : 'button'

    const baseClasses = 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 cursor-pointer'

    const variantClasses = {
      default: 'bg-secondary text-secondary-foreground hover:bg-secondary/80 border border-border',
      primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
      secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
      outline: 'border border-border bg-transparent hover:bg-secondary text-foreground',
      ghost: 'hover:bg-secondary text-foreground',
      destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
    }

    const sizeClasses = {
      sm: 'h-8 px-3 text-sm',
      md: 'h-10 px-4',
      lg: 'h-11 px-8'
    }

    const prefix = loading ? (
      <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
    ) : icon ? (
      <span className="mr-2">{icon}</span>
    ) : null

    return (
      <Comp
        ref={ref}
        {...props}
        type={type}
        onClick={onClick}
        disabled={disabled || loading}
        className={cn(
          baseClasses,
          variantClasses[variant],
          sizeClasses[size],
          className
        )}
      >
        {!asChild ? prefix : null}
        {children}
      </Comp>
    )
  }
)

Button.displayName = 'Button'
