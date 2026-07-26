'use client';

import React, { useState } from 'react';
import { Columns, FileCode, AlertCircle, Sparkles, Copy, Check } from 'lucide-react';

interface DiffViewerProps {
  filePath: string;
  baseCode: string;
  proposedCode: string;
  rootCause: string;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  filePath,
  baseCode,
  proposedCode,
  rootCause
}) => {
  const [viewMode, setViewMode] = useState<'split' | 'unified'>('split');
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(proposedCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const baseLines = baseCode.split('\n');
  const proposedLines = proposedCode.split('\n');

  // Simple unified line generator for visual demo
  const getUnifiedLines = () => {
    const maxLen = Math.max(baseLines.length, proposedLines.length);
    const unified: Array<{ type: 'same' | 'added' | 'deleted'; line: string; oldNo?: number; newNo?: number }> = [];

    for (let i = 0; i < maxLen; i++) {
      const oldL = baseLines[i];
      const newL = proposedLines[i];

      if (oldL === newL && oldL !== undefined) {
        unified.push({ type: 'same', line: oldL, oldNo: i + 1, newNo: i + 1 });
      } else {
        if (oldL !== undefined) {
          unified.push({ type: 'deleted', line: oldL, oldNo: i + 1 });
        }
        if (newL !== undefined) {
          unified.push({ type: 'added', line: newL, newNo: i + 1 });
        }
      }
    }
    return unified;
  };

  const unifiedLines = getUnifiedLines();

  return (
    <div className="flex flex-col h-full bg-slate-950/90 border border-slate-800/80 rounded-2xl overflow-hidden shadow-2xl">
      {/* Root Cause Banner */}
      <div className="px-5 py-3 bg-gradient-to-r from-slate-900 via-slate-900/90 to-slate-950 border-b border-slate-800/80 flex items-start gap-3">
        <div className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 shrink-0 mt-0.5">
          <Sparkles className="w-4 h-4 text-emerald-400" />
        </div>
        <div className="flex-1">
          <div className="text-xs font-semibold text-slate-200">Root Cause Analysis & AI Fix</div>
          <p className="text-xs text-slate-400 leading-relaxed mt-0.5">{rootCause}</p>
        </div>
      </div>

      {/* Diff Toolbar */}
      <div className="px-5 py-2.5 bg-slate-900/50 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileCode className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-mono font-semibold text-slate-200">{filePath}</span>
        </div>

        <div className="flex items-center gap-3">
          {/* View Mode Switcher */}
          <div className="flex items-center p-0.5 rounded-lg bg-slate-950 border border-slate-800">
            <button
              onClick={() => setViewMode('split')}
              className={`px-3 py-1 rounded-md text-[11px] font-semibold transition-all ${
                viewMode === 'split'
                  ? 'bg-slate-800 text-slate-100 shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Split View
            </button>
            <button
              onClick={() => setViewMode('unified')}
              className={`px-3 py-1 rounded-md text-[11px] font-semibold transition-all ${
                viewMode === 'unified'
                  ? 'bg-slate-800 text-slate-100 shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Unified View
            </button>
          </div>

          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] text-slate-300 transition-colors"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? 'Copied!' : 'Copy Fix'}</span>
          </button>
        </div>
      </div>

      {/* Code Display Area */}
      <div className="flex-1 overflow-auto font-mono text-xs bg-[#090d16]">
        {viewMode === 'split' ? (
          <div className="grid grid-cols-2 divide-x divide-slate-800/80 min-h-full">
            {/* Left: Base Version */}
            <div>
              <div className="sticky top-0 bg-slate-900/90 border-b border-slate-800 px-4 py-1.5 text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                <span>Base Version (Production Code)</span>
                <span className="text-rose-400">- Deletions</span>
              </div>
              <div className="py-2">
                {baseLines.map((line, idx) => {
                  const isModified = proposedLines[idx] !== line;
                  return (
                    <div
                      key={idx}
                      className={`flex px-3 py-0.5 leading-5 ${
                        isModified
                          ? 'bg-rose-950/40 text-rose-300 border-l-2 border-rose-500'
                          : 'text-slate-400 hover:bg-slate-900/40'
                      }`}
                    >
                      <span className="w-8 shrink-0 text-slate-600 select-none text-right pr-3">
                        {idx + 1}
                      </span>
                      <pre className="whitespace-pre-wrap break-all flex-1">{line || ' '}</pre>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Right: Proposed Fix */}
            <div>
              <div className="sticky top-0 bg-slate-900/90 border-b border-slate-800 px-4 py-1.5 text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                <span>Proposed Fix (Agent Generated)</span>
                <span className="text-emerald-400">+ Additions</span>
              </div>
              <div className="py-2">
                {proposedLines.map((line, idx) => {
                  const isModified = baseLines[idx] !== line;
                  return (
                    <div
                      key={idx}
                      className={`flex px-3 py-0.5 leading-5 ${
                        isModified
                          ? 'bg-emerald-950/40 text-emerald-300 border-l-2 border-emerald-500'
                          : 'text-slate-400 hover:bg-slate-900/40'
                      }`}
                    >
                      <span className="w-8 shrink-0 text-slate-600 select-none text-right pr-3">
                        {idx + 1}
                      </span>
                      <pre className="whitespace-pre-wrap break-all flex-1">{line || ' '}</pre>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          /* Unified View */
          <div className="py-2">
            {unifiedLines.map((item, idx) => (
              <div
                key={idx}
                className={`flex px-4 py-0.5 leading-5 ${
                  item.type === 'added'
                    ? 'bg-emerald-950/40 text-emerald-300 border-l-2 border-emerald-500'
                    : item.type === 'deleted'
                    ? 'bg-rose-950/40 text-rose-300 border-l-2 border-rose-500'
                    : 'text-slate-400 hover:bg-slate-900/40'
                }`}
              >
                <span className="w-8 shrink-0 text-slate-600 select-none text-right pr-2">
                  {item.oldNo || ''}
                </span>
                <span className="w-8 shrink-0 text-slate-600 select-none text-right pr-3">
                  {item.newNo || ''}
                </span>
                <span className="w-4 shrink-0 select-none font-bold">
                  {item.type === 'added' ? '+' : item.type === 'deleted' ? '-' : ' '}
                </span>
                <pre className="whitespace-pre-wrap break-all flex-1">{item.line || ' '}</pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
