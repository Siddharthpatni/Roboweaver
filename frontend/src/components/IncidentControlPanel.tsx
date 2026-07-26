'use client';

import React, { useState } from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  AlertTriangle, 
  RefreshCw, 
  Send, 
  X, 
  ChevronRight,
  ShieldAlert,
  Loader2,
  FileCode2
} from 'lucide-react';
import { Incident } from '../types';
import { DiffViewer } from './DiffViewer';
import { WorkflowStepper } from './WorkflowStepper';

interface IncidentControlPanelProps {
  incidents: Incident[];
  selectedId: string;
  onSelectIncident: (id: string) => void;
  onUpdateStatus: (id: string, status: 'approved' | 'rejected' | 'escalated', note?: string) => void;
  onResetDemo: () => void;
  onClose?: () => void;
}

export const IncidentControlPanel: React.FC<IncidentControlPanelProps> = ({
  incidents,
  selectedId,
  onSelectIncident,
  onUpdateStatus,
  onResetDemo,
  onClose
}) => {
  const current = incidents.find((inc) => inc.id === selectedId) || incidents[0];
  const [isDeploying, setIsDeploying] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectionNote, setRejectionNote] = useState('');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4500);
  };

  const handleApprove = () => {
    setIsDeploying(true);
    setTimeout(() => {
      setIsDeploying(false);
      onUpdateStatus(current.id, 'approved', 'Approved by John Smith (Lead SRE)');
      showToast('✓ Fix successfully dispatched to automated deployment & robotics CI/CD pipeline.');
    }, 1200);
  };

  const handleRejectSubmit = () => {
    onUpdateStatus(current.id, 'escalated', rejectionNote || 'Escalated to Human On-Call for manual override');
    setShowRejectModal(false);
    setRejectionNote('');
    showToast('⚠️ Fix rejected & escalated. Paged Robotics On-Call team with incident trace.');
  };

  const isAlreadyResolved = current.status === 'approved' || current.status === 'escalated' || current.status === 'rejected';

  return (
    <div className="flex flex-col h-full w-full bg-robotic-grid text-slate-100 overflow-hidden relative font-mono">
      {/* Toast Alert Banner */}
      {toastMessage && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 bg-[#060b17] border border-emerald-400 text-emerald-300 px-5 py-2.5 rounded-xl shadow-2xl flex items-center gap-3 animate-fade-in font-mono">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          <span className="text-xs font-bold">{toastMessage}</span>
          <button onClick={() => setToastMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Mecha HUD Header Tabs for Selectable Incidents */}
      <div className="px-6 py-3 bg-[#060b17] border-b border-emerald-500/30 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 overflow-x-auto">
          <span className="text-xs font-bold text-emerald-400 uppercase tracking-widest pr-2">
            [ INCIDENT HUD ]
          </span>
          {incidents.map((inc) => {
            const isSelected = inc.id === selectedId;
            return (
              <button
                key={inc.id}
                onClick={() => onSelectIncident(inc.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold uppercase transition-all shrink-0 ${
                  isSelected
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-400 shadow-md shadow-emerald-500/20'
                    : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    inc.status === 'approved'
                      ? 'bg-emerald-400'
                      : inc.status === 'escalated'
                      ? 'bg-rose-400'
                      : 'bg-amber-400 animate-pulse'
                  }`}
                />
                <span>{inc.id}</span>
                <span className="text-[10px] text-slate-400 font-normal truncate max-w-[150px]">
                  — {inc.title}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onResetDemo}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-900 border border-emerald-500/30 text-xs text-emerald-400 font-bold uppercase transition-colors shadow-sm"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>[ RESET DEMO STATE ]</span>
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-950 hover:bg-slate-900 border border-emerald-500/30 text-slate-400 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Main 2-Column Grid: Left Diff Viewer (70%) + Right Stepper & Metrics (30%) */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0">
        {/* Center/Left: Live Diff Viewer Component */}
        <div className="lg:col-span-8 xl:col-span-9 p-6 overflow-hidden flex flex-col">
          <DiffViewer
            filePath={current.filePath}
            baseCode={current.baseCode}
            proposedCode={current.proposedCode}
            rootCause={current.rootCause}
          />
        </div>

        {/* Right: Agent Workflow Stepper & Operational Metrics */}
        <div className="lg:col-span-4 xl:col-span-3 min-h-0 overflow-y-auto">
          <WorkflowStepper
            steps={current.steps}
            tokenCount={current.tokenCount}
            processingTime={current.processingTime}
            riskScore={current.riskScore}
            riskLevel={current.riskLevel}
            incidentStatus={current.status}
          />
        </div>
      </div>

      {/* Bottom Action Bar (Approve & Deploy Fix vs Reject & Escalate) */}
      <div className="h-20 bg-[#060b17] border-t border-emerald-500/30 px-6 flex items-center justify-between shrink-0 font-mono">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-5 h-5 text-emerald-400 animate-pulse" />
          <div>
            <div className="text-xs font-bold text-white uppercase tracking-wider">
              [ HITL_INTERLOCK_REQUIRED ] : {current.title}
            </div>
            <div className="text-[11px] text-slate-400">
              ROBOT_TARGET: <span className="font-mono text-emerald-400 font-bold">{current.service}</span> • STATUS:{' '}
              <span className="uppercase font-bold text-amber-400">{current.status}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Reject & Escalation Button */}
          <button
            onClick={() => setShowRejectModal(true)}
            disabled={isAlreadyResolved}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold shadow-lg transition-all ${
              isAlreadyResolved
                ? 'bg-slate-900 text-slate-600 border border-slate-800 cursor-not-allowed'
                : 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/30'
            }`}
          >
            <XCircle className="w-4 h-4" />
            <span>Reject Fix & Escalate</span>
          </button>

          {/* Approve & Deploy Fix Button */}
          <button
            onClick={handleApprove}
            disabled={isAlreadyResolved || isDeploying}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold shadow-lg transition-all ${
              isAlreadyResolved
                ? 'bg-slate-900 text-slate-600 border border-slate-800 cursor-not-allowed'
                : 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/30'
            }`}
          >
            {isDeploying ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Deploying Fix...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4" />
                <span>Approve & Deploy Fix</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Interactive Reject / Escalation Modal */}
      {showRejectModal && (
        <div className="absolute inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-700 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-rose-400">
                <AlertTriangle className="w-5 h-5" />
                <h3 className="text-sm font-bold">Reject & Escalate Incident</h3>
              </div>
              <button
                onClick={() => setShowRejectModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-slate-300">
              Provide feedback or escalation notes for the Robotics On-Call team. Why was the AI generated fix rejected?
            </p>
            <textarea
              value={rejectionNote}
              onChange={(e) => setRejectionNote(e.target.value)}
              placeholder="e.g., Modbus RTU requires 15ms frame delay on Inspire Hand before TX flush..."
              rows={4}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500"
            />
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowRejectModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectSubmit}
                className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white shadow-lg shadow-rose-600/30 flex items-center gap-2"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Confirm & Page On-Call</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
