/**
 * useConversion — wraps polling, status, download for a single conversion.
 *
 * Usage:
 *   const { conversion, isPolling, download } = useConversion(conversionId);
 */

import { useEffect, useCallback } from "react";
import { useConversionStore } from "@/store/conversion-store";
import type { Conversion } from "@/types";

interface UseConversionReturn {
  conversion: Conversion | undefined;
  isPolling: boolean;
  startPolling: () => void;
  stopPolling: () => void;
  refresh: () => Promise<void>;
}

export function useConversion(id: string | null): UseConversionReturn {
  const conversions = useConversionStore((s) => s.conversions);
  const pollingId = useConversionStore((s) => s.pollingId);
  const pollConversion = useConversionStore((s) => s.pollConversion);
  const stopPolling = useConversionStore((s) => s.stopPolling);
  const refreshConversion = useConversionStore((s) => s.refreshConversion);

  const conversion = id ? conversions.find((c) => c.id === id) : undefined;
  const isPolling = pollingId !== null;

  const startPolling = useCallback(() => {
    if (id) pollConversion(id);
  }, [id, pollConversion]);

  const refresh = useCallback(async () => {
    if (id) await refreshConversion(id);
  }, [id, refreshConversion]);

  // Auto-stop polling when conversion reaches terminal state
  useEffect(() => {
    if (
      conversion?.status === "completed" ||
      conversion?.status === "failed" ||
      conversion?.status === "partial"
    ) {
      stopPolling();
    }
  }, [conversion?.status, stopPolling]);

  return { conversion, isPolling, startPolling, stopPolling, refresh };
}
