/**
 * SseGate component.
 * Blocks rendering of children until the SSE connection is established.
 * SSE runs as a Kubernetes sidecar, so if it's down the pod is down —
 * no error/retry UI is needed.
 */

import type { ReactNode } from 'react';
import { useSseContext } from '@/contexts/sse-context';

interface SseGateProps {
  children: ReactNode;
}

export function SseGate({ children }: SseGateProps) {
  const { isConnected } = useSseContext();

  if (!isConnected) {
    return (
      <div
        className="h-screen w-full bg-background"
        data-testid="sse.gate.loading"
      />
    );
  }

  return <>{children}</>;
}
