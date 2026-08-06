'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Brain, Send, Sparkles, AlertTriangle, Loader2, Zap, X, MessageSquare, PanelLeft, PanelRight } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import type { AIChatResult, AIStatusResult, ViewType } from '../types';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  model?: string;
  latency_s?: number;
  error?: boolean;
  timestamp: number;
}

/**
 * AICopilotPanel — A persistent, dockable AI assistant panel for the RoboWeaver
 * dashboard. Chat-style interface for asking questions about compiled skills,
 * the pipeline, and the platform.
 *
 * Features:
 *   * Real-time Ollama status indicator
 *   * Chat history with terminal-style rendering
 *   * Contextual quick actions
 *   * Response metadata (model, latency)
 */
export const AICopilotPanel: React.FC<{ defaultOpen?: boolean; activeView?: ViewType }> = ({
  defaultOpen = false,
  activeView = 'overview',
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [aiStatus, setAiStatus] = useState<AIStatusResult | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [dock, setDock] = useState<'left' | 'right'>('right');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Probe Ollama status on mount and periodically
  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      try {
        const status = await RoboWeaverAPI.aiStatus();
        if (!cancelled) setAiStatus(status);
      } catch {
        if (!cancelled) setAiStatus(null);
      } finally {
        if (!cancelled) setStatusLoading(false);
      }
    };
    probe();
    const interval = setInterval(probe, 30_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: ChatMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    const assistantId = `msg_${Date.now()}_ai`;
    const pendingMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    };
    setMessages(prev => [...prev, userMsg, pendingMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const result: AIChatResult = await RoboWeaverAPI.aiChatStream(text, (token) => {
        setMessages(prev => prev.map((msg) => (
          msg.id === assistantId ? { ...msg, content: msg.content + token } : msg
        )));
      });
      setMessages(prev => prev.map((msg) => msg.id === assistantId ? {
        ...msg,
        content: result.response ?? result.error ?? 'No response from AI.',
        model: result.model,
        latency_s: result.latency_s,
        error: !result.response,
      } : msg));
    } catch (err) {
      setMessages(prev => prev.map((msg) => msg.id === assistantId ? {
        ...msg,
        content: err instanceof Error ? err.message : 'Failed to reach the AI service.',
        error: true,
      } : msg));
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const baseActions = [
    { label: 'What is RoboIR?', prompt: 'Explain what RoboIR is and how it works in the compilation pipeline' },
    { label: 'Explain passes', prompt: 'What are the compiler passes in the RoboWeaver pipeline?' },
    { label: 'Robot comparison', prompt: 'How does the robot comparison and ranking system work?' },
    { label: 'Safety checks', prompt: 'What safety verification does RoboWeaver perform during compilation?' },
  ];
  const contextualAction = activeView === 'compile'
    ? { label: 'Improve this skill', prompt: 'What should I inspect when optimizing the skill currently shown in the Compiler view?' }
    : activeView === 'workcell'
      ? { label: 'Plan a workcell', prompt: 'How should I decompose and verify the multi-robot workcell currently being designed?' }
      : activeView === 'graph'
        ? { label: 'Read this graph', prompt: 'How should I validate AI-suggested SUITABLE_FOR edges in the knowledge graph?' }
        : null;
  const quickActions = contextualAction ? [contextualAction, ...baseActions.slice(0, 3)] : baseActions;

  const ollamaAvailable = aiStatus?.available ?? false;

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        id="ai-copilot-toggle"
        className={`fixed bottom-4 ${dock === 'right' ? 'right-4 sm:right-6' : 'left-4 sm:left-6 lg:left-[17.5rem]'} z-50 flex h-12 w-12 items-center justify-center rounded-xl bg-[#162131] text-cyan-300 shadow-2xl ring-1 ring-inset ring-white/[0.1] transition-colors hover:bg-[#1b2a3d] sm:h-13 sm:w-13`}
        style={{
          border: '1px solid rgba(103,232,249,0.16)',
        }}
        title="Open AI Co-Pilot"
      >
        <Brain className="h-5 w-5" />
        {ollamaAvailable && (
          <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 rounded-full bg-emerald-400" style={{ boxShadow: '0 0 6px rgba(52,211,153,0.6)' }} />
        )}
      </button>
    );
  }

  return (
    <div
      id="ai-copilot-panel"
      className={`fixed bottom-4 ${dock === 'right' ? 'right-4 sm:right-6' : 'left-4 sm:left-6 lg:left-[17.5rem]'} z-50 flex flex-col`}
      style={{
        width: 'min(420px, calc(100vw - 32px))',
        height: 'min(580px, calc(100dvh - 88px))',
        background: 'linear-gradient(180deg, rgba(22,33,49,0.98), rgba(11,17,27,0.99))',
        border: '1px solid rgba(148,163,184,0.16)',
        borderRadius: 16,
        backdropFilter: 'blur(18px)',
        boxShadow: '0 24px 64px rgba(0,0,0,0.48)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-cyan-400/[0.08]">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <Brain className="w-5 h-5 text-cyan-300" />
            <span
              className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full ${ollamaAvailable ? 'bg-emerald-400' : 'bg-rose-400'}`}
              style={{ boxShadow: ollamaAvailable ? '0 0 6px rgba(52,211,153,0.6)' : '0 0 6px rgba(251,113,133,0.6)' }}
            />
          </div>
          <div>
            <div className="text-[13px] font-semibold text-slate-100">RoboWeaver AI</div>
            <div className="text-[10px] text-slate-500">
              {statusLoading ? 'Connecting...' : ollamaAvailable
                ? `${aiStatus?.default_model ?? 'ready'} · ${aiStatus?.version ?? ''}`
                : 'Ollama offline'}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {aiStatus && (
            <span className="text-[10px] text-slate-600 mr-2">
              {aiStatus.total_calls} calls
              {aiStatus.avg_latency_s != null && ` · ${(aiStatus.avg_latency_s * 1000).toFixed(0)}ms avg`}
            </span>
          )}
          <button
            onClick={() => setDock((current) => current === 'right' ? 'left' : 'right')}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/[0.05] transition-colors"
            title={`Dock panel to the ${dock === 'right' ? 'left' : 'right'}`}
          >
            {dock === 'right' ? <PanelLeft className="w-4 h-4" /> : <PanelRight className="w-4 h-4" />}
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/[0.05] transition-colors"
            aria-label="Close AI copilot"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3" style={{ scrollbarWidth: 'thin' }}>
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
              style={{
                background: 'linear-gradient(135deg, rgba(34,211,238,0.1) 0%, rgba(139,92,246,0.1) 100%)',
                border: '1px solid rgba(34,211,238,0.15)',
              }}
            >
              <Sparkles className="w-6 h-6 text-cyan-400/60" />
            </div>
            <div className="text-[13px] text-slate-400 mb-1">Ask anything about RoboWeaver</div>
            <div className="text-[11px] text-slate-600 mb-5">Compilation, motion planning, RoboIR, behavior trees...</div>

            <div className="grid grid-cols-2 gap-2 w-full">
              {quickActions.map((qa) => (
                <button
                  key={qa.label}
                  onClick={() => { setInput(qa.prompt); inputRef.current?.focus(); }}
                  className="text-left px-3 py-2 rounded-xl text-[11px] text-slate-400 hover:text-cyan-300 transition-all"
                  style={{
                    background: 'rgba(34,211,238,0.04)',
                    border: '1px solid rgba(34,211,238,0.08)',
                  }}
                >
                  <Zap className="w-3 h-3 text-cyan-500/40 mb-1" />
                  {qa.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.filter((msg) => msg.content).map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[12.5px] leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-cyan-500/[0.12] text-cyan-100 border border-cyan-400/[0.12]'
                  : msg.error
                    ? 'bg-rose-500/[0.08] text-rose-200 border border-rose-500/[0.12]'
                    : 'bg-white/[0.03] text-slate-300 border border-white/[0.06]'
              }`}
              style={{ borderRadius: msg.role === 'user' ? '20px 20px 6px 20px' : '20px 20px 20px 6px' }}
            >
              {msg.error && <AlertTriangle className="w-3.5 h-3.5 text-rose-400 mb-1 inline-block mr-1" />}
              <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
              {msg.model && (
                <div className="mt-1.5 text-[9.5px] text-slate-600 flex items-center gap-2">
                  <span>{msg.model}</span>
                  {msg.latency_s != null && <span>· {(msg.latency_s * 1000).toFixed(0)}ms</span>}
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div
              className="rounded-2xl px-4 py-3 flex items-center gap-2 text-[12px] text-slate-500"
              style={{
                background: 'rgba(34,211,238,0.04)',
                border: '1px solid rgba(34,211,238,0.08)',
                borderRadius: '20px 20px 20px 6px',
              }}
            >
              <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400/50" />
              Thinking...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-3 pb-3 pt-1">
        <div
          className="flex items-center gap-2 rounded-xl px-3 py-2"
          style={{
            background: 'rgba(34,211,238,0.04)',
            border: '1px solid rgba(34,211,238,0.1)',
          }}
        >
          <MessageSquare className="w-4 h-4 text-slate-600 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={ollamaAvailable ? 'Ask RoboWeaver AI...' : 'Ollama offline — start with: ollama serve'}
            disabled={isLoading}
            className="flex-1 bg-transparent text-[12.5px] text-slate-200 placeholder:text-slate-600 outline-none"
            id="ai-copilot-input"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            className="p-1.5 rounded-lg text-cyan-400/60 hover:text-cyan-300 hover:bg-cyan-500/[0.1] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="text-[9px] text-slate-600 text-center mt-1.5">
          Local Ollama runtime · prompts stay on the configured host
        </div>
      </div>
    </div>
  );
};
