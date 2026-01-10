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

    const baseClasses = 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-zinc-400 disabled:pointer-events-none disabled:opacity-50 cursor-pointer'

    const variantClasses = {
      default: 'bg-zinc-800 text-zinc-50 hover:bg-zinc-700 border border-zinc-700',
      primary: 'bg-blue-600 text-zinc-50 hover:bg-blue-700',
      secondary: 'bg-zinc-700 text-zinc-50 hover:bg-zinc-600',
      outline: 'border border-zinc-700 bg-transparent hover:bg-zinc-800 text-zinc-50',
      ghost: 'hover:bg-zinc-800 text-zinc-50',
      destructive: 'bg-red-600 text-zinc-50 hover:bg-red-700'
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
