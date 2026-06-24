import { useEffect, useRef, useState } from "react";

interface PollState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** Poll an async fetcher on an interval. Aborts in-flight requests on unmount
 *  and dedupes overlapping ticks. Keeps the last good data when a tick errors. */
export function usePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
): PollState<T> & { refresh: () => void } {
  const [state, setState] = useState<PollState<T>>({
    data: null,
    error: null,
    loading: true,
  });
  // Keep the latest fetcher without re-arming the interval each render.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const run = async () => {
      try {
        const data = await fetcherRef.current(controller.signal);
        if (!cancelled) setState({ data, error: null, loading: false });
      } catch (err) {
        if (cancelled || controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        setState((prev) => ({ ...prev, error: message, loading: false }));
      }
    };

    run();
    const handle = setInterval(run, intervalMs);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(handle);
    };
  }, [intervalMs, tick]);

  return { ...state, refresh: () => setTick((t) => t + 1) };
}
