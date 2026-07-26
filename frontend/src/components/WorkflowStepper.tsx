'use client';

import React from 'react';
import { 
  CheckCircle2, 
  Clock, 
  Loader2, 
  AlertCircle, 
  ShieldCheck, 
  Cpu, 
  Zap, 
  Lock,
  UserCheck
} from 'lucide-react';
import { WorkflowStep } from '../types';

interface WorkflowStepperProps {
  steps: WorkflowStep[];
  tokenCount: number;
  processingTime: string;
  riskScore: string;
  riskLevel: 'Low' | 'Medium' | 'High';
  incidentStatus: 'pending_review' | 'approved' | 'rejected' | 'escalated';
}

export const WorkflowStepper: React.FC<WorkflowStepperProps> = ({
  steps,
  tokenCount,
  processingTime,
  riskScore,
  riskLevel,
  incidentStatus
}) => {
  return (
    <div className="flex flex-col h-full bg-slate-950 border-l border-slate-800/80 p-5 space-y-6 overflow-y-auto">
      {/* Section 1: Agent Pipeline Status Stepper */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              Agent Workflow Pipeline
            </h3>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            6/6 Nodes
          </span>
        </div>

        <div className="space-y-3.5 relative before:absolute before:left-3.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
          {steps.map((step) => {
            const isCompleted = step.status === 'completed';
            const isRunning = step.status === 'running';
            const isApproved = step.status === 'approved';
            const isRejected = step.status === 'rejected';

            return (
              <div key={step.id} className="relative flex items-start gap-3 pl-1">
                {/* Step Indicator Icon */}
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center z-10 shrink-0 border ${
                    isCompleted || isApproved
                      ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400'
                      : isRejected
                      ? 'bg-rose-500/20 border-rose-500/50 text-rose-400'
                      : isRunning
                      ? 'bg-amber-500/20 border-amber-500/50 text-amber-400'
                      : 'bg-slate-900 border-slate-700 text-slate-500'
                  }`}
                >
                  {isCompleted || isApproved ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : isRejected ? (
                    <AlertCircle className="w-3.5 h-3.5" />
                  ) : isRunning ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <span className="text-[10px] font-bold">{step.id}</span>
                  )}
                </div>

                {/* Step Text & Metadata */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-xs font-semibold ${
                        isCompleted || isApproved
                          ? 'text-slate-200'
                          : isRejected
                          ? 'text-rose-400'
                          : isRunning
                          ? 'text-amber-400'
                          : 'text-slate-400'
                      }`}
                    >
                      {step.id}. {step.label}
                    </span>
                    {step.timestamp && (
                      <span className="text-[10px] font-mono text-slate-500">
                        {step.timestamp}
                      </span>
                    )}
                  </div>

                  {/* Pulsing Badge for Human Approval when running */}
                  {step.id === 6 && isRunning && (
                    <div className="mt-1.5 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-300 font-medium">
                      <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                      <span>Waiting for input — Animated Pulse Badge</span>
                    </div>
                  )}

                  {step.id === 6 && isApproved && (
                    <div className="mt-1.5 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-[11px] text-emerald-300 font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Human Approval Sign-Off Recorded</span>
                    </div>
                  )}

                  {step.detail && step.id !== 6 && (
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
                      {step.detail}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Section 2: Agent Insights & Operational Metrics Card */}
      <div className="pt-4 border-t border-slate-800/80">
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-4 h-4 text-emerald-400" />
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
            Agent Insights & Metrics
          </h3>
        </div>

        <div className="grid grid-cols-1 gap-3">
          {/* Tokens Used */}
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800/80 flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-400 text-xs">
              <Cpu className="w-3.5 h-3.5 text-slate-500" />
              <span>Tokens Used</span>
            </div>
            <span className="text-sm font-mono font-bold text-slate-100">
              {tokenCount.toLocaleString()}
            </span>
          </div>

          {/* Processing Time */}
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800/80 flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-400 text-xs">
              <Clock className="w-3.5 h-3.5 text-slate-500" />
              <span>Processing Time</span>
            </div>
            <span className="text-sm font-mono font-bold text-emerald-400">
              {processingTime}
            </span>
          </div>

          {/* Security Risk Score */}
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800/80 flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-400 text-xs">
              <Lock className="w-3.5 h-3.5 text-slate-500" />
              <span>Security Risk Score</span>
            </div>
            <span
              className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                riskLevel === 'Low'
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
              }`}
            >
              {riskScore}
            </span>
          </div>
        </div>
      </div>

      {/* Section 3: Human-in-the-Loop Governance Notice */}
      <div className="p-3.5 rounded-xl bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-slate-900 border border-indigo-500/20">
        <div className="flex items-center gap-2 mb-1.5">
          <UserCheck className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-xs font-semibold text-indigo-300">HITL Governance Policy</span>
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed">
          Autonomous agents require explicit human sign-off for code modifications affecting database connection pools or robotics hardware drivers.
        </p>
      </div>
    </div>
  );
};
