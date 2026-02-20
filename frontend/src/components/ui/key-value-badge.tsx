import * as React from 'react';
import { Badge } from './badge';

// Subtle color palette for metric and attribute badges
const COLOR_CLASSES = {
  neutral: 'bg-slate-100 text-slate-700',
  info: 'bg-blue-100 text-blue-800',
  warning: 'bg-amber-100 text-amber-800',
  success: 'bg-emerald-100 text-emerald-800',
  danger: 'bg-rose-100 text-rose-800',
} as const;

export interface KeyValueBadgeProps {
  /** Badge label (appears before colon) */
  label: string;
  /** Badge value (appears after colon) */
  value: string | number;
  /** Semantic color (defaults to neutral) */
  color?: keyof typeof COLOR_CLASSES;
  /** Test ID for Playwright selectors */
  testId: string;
}

/**
 * KeyValueBadge — Standardized badge for displaying metrics and attributes
 *
 * Renders badges in `<key>: <value>` format with consistent semantic colors.
 * Intentionally does not support custom className prop to enforce visual consistency.
 *
 * @example
 * <KeyValueBadge label="Total lines" value={42} color="neutral" testId="pick-lists.detail.badge.total-lines" />
 * <KeyValueBadge label="Shortfall" value={10} color="danger" testId="kits.detail.badge.shortfall" />
 */
export const KeyValueBadge = React.forwardRef<HTMLSpanElement, KeyValueBadgeProps>(
  ({ label, value, color = 'neutral', testId }, ref) => {
    const colorClasses = COLOR_CLASSES[color];

    return (
      <Badge
        ref={ref}
        variant="outline"
        className={colorClasses}
        data-testid={testId}
      >
        {label}: {value}
      </Badge>
    );
  }
);

KeyValueBadge.displayName = 'KeyValueBadge';
