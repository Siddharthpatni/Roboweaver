'use client';

import React, { useEffect, useRef, useState } from 'react';
import { AlertOctagon, RefreshCw } from 'lucide-react';

const MAX_AUTO_RETRIES = 3;
const BASE_BACKOFF_MS = 1000;

/**
 * Next.js's route-segment error boundary -- the outer safety net.
 *
 * The inner <ErrorBoundary> in page.tsx contains a crash to just the active
 * tab's content; this one catches anything that escapes that (a crash in
 * Sidebar/TopBar, or in page.tsx's own top-level logic), so the whole app
 * still doesn't require a manual reload to recover. Same self-healing
 * contract as the inner boundary and the backend's supervisor: auto-retry
 * with backoff first, a manual button only after retries are exhausted.
 */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const [attempt, setAttempt] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    console.error('Root error boundary caught:', error);
    if (attempt < MAX_AUTO_RETRIES) {
      timerRef.current = setTimeout(() => {
        setAttempt((a) => a + 1);
        reset();
      }, BASE_BACKOFF_MS * 2 ** attempt);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // Deliberately only re-runs when `error` changes (a fresh crash) or the
    // retry count advances -- not on every `reset` identity change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error, attempt]);

  const willAutoRetry = attempt < MAX_AUTO_RETRIES;

  return (
    <div className="h-screen w-screen bg-app-surface flex items-center justify-center p-8">
      <div className="app-card p-7 max-w-md w-full space-y-3.5 text-center">
        <AlertOctagon className="w-7 h-7 text-rose-400 mx-auto" />
        <h2 className="text-[15px] font-semibold text-slate-200">RoboWeaver hit an unexpected error</h2>
        <p className="text-[12px] text-slate-500 leading-relaxed">{error.message || 'Unknown error'}</p>
        {willAutoRetry ? (
          <p className="text-[11.5px] text-cyan-400 flex items-center justify-center gap-1.5">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            Recovering automatically… (attempt {attempt + 1}/{MAX_AUTO_RETRIES})
          </p>
        ) : (
          <button
            onClick={() => {
              setAttempt(0);
              reset();
            }}
            className="inline-flex items-center gap-1.5 px-4 py-2 btn-neon text-[13px] mx-auto"
          >
            <RefreshCw className="w-4 h-4" />
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
