'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Boxes,
  Brain,
  Check,
  CheckCircle2,
  ChevronRight,
  Code2,
  Copy,
  Download,
  Gauge,
  GitBranch,
  Layers3,
  Loader2,
  Network,
  Play,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Workflow,
} from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import {
  CompilationFailedError,
  CompiledSkillResult,
  CompilerDiagnostic,
  PipelineTraceResult,
  RobotComparisonResult,
  RobotProfile,
  UniversalCompileMatrix,
} from '../types';
import { PipelineTraceView } from './PipelineTraceView';

const EXAMPLES = [
  'Pick the red cube and place it into the blue bin',
  'Tighten the M8 bolt',
  'Inspect the machine panel for surface defects',
];

type TargetMode = 'universal' | 'profile';
type StageId = 'overview' | 'frontend' | 'tasks' | 'ir' | 'passes' | 'backend' | 'artifact';

const STAGES: Array<{
  id: StageId;
  number: string;
  label: string;
  detail: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { id: 'frontend', number: '01', label: 'Understand request', detail: 'Action, objects, and limits', icon: ScanSearch },
  { id: 'tasks', number: '02', label: 'Build task plan', detail: 'Ordered robot actions', icon: Workflow },
  { id: 'ir', number: '03', label: 'Create portable program', detail: 'Robot-independent meaning', icon: GitBranch },
  { id: 'passes', number: '04', label: 'Check and optimize', detail: 'Compiler validation passes', icon: Layers3 },
  { id: 'backend', number: '05', label: 'Adapt to robot', detail: 'Joints, motion, and limits', icon: Boxes },
  { id: 'artifact', number: '06', label: 'Prepare download', detail: 'Runtime-ready output', icon: TerminalSquare },
];

function stageStatus(stage: StageId, result: CompiledSkillResult | null, loading: boolean) {
  if (loading) return 'running';
  if (!result) return 'idle';
  if (stage === 'frontend' || stage === 'tasks' || stage === 'ir' || stage === 'backend' || stage === 'artifact') {
    return 'done';
  }
  return result.pipeline || result.skill_pipeline ? 'done' : 'idle';
}

function PanelTitle({
  icon: Icon,
  eyebrow,
  title,
  meta,
}: {
  icon: React.ComponentType<{ className?: string }>;
  eyebrow: string;
  title: string;
  meta?: string;
}) {
  return (
    <div className="compiler-panel-title">
      <span className="compiler-panel-icon"><Icon className="h-4 w-4" /></span>
      <div className="min-w-0">
        <span className="compiler-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {meta && <span className="compiler-panel-meta">{meta}</span>}
    </div>
  );
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="compiler-metric">
      <span>{label}</span>
      <strong className={accent ? 'text-cyan-200' : undefined}>{value}</strong>
    </div>
  );
}

function Tag({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'cyan' | 'violet' | 'amber' | 'green' }) {
  return <span className={`compiler-tag compiler-tag-${tone}`}>{children}</span>;
}

function EvidenceRow({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: 'cyan' | 'amber' | 'green' | 'neutral';
}) {
  return (
    <div className="compiler-evidence-row">
      <div className="min-w-0">
        <span>{label}</span>
        <small>{detail}</small>
      </div>
      <Tag tone={tone}>{value}</Tag>
    </div>
  );
}

function DiagnosticCard({ diagnostic }: { diagnostic: CompilerDiagnostic }) {
  const error = diagnostic.severity === 'error';
  return (
    <div className={`compiler-diagnostic ${error ? 'compiler-diagnostic-error' : 'compiler-diagnostic-warning'}`}>
      <div className="flex min-w-0 items-start gap-2.5">
        {error ? <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-data text-[10px] font-bold tracking-wide">{diagnostic.code}</span>
            <span className="text-[12px] font-semibold text-slate-100">{diagnostic.message}</span>
          </div>
          <p className="mt-1.5 text-[11.5px] leading-5 text-slate-400">{diagnostic.reason}</p>
          {diagnostic.required_capability && (
            <p className="mt-2 font-data text-[10px] text-slate-500">requires <span className="text-slate-300">{diagnostic.required_capability}</span></p>
          )}
        </div>
      </div>
    </div>
  );
}

function XmlHighlight({ xml }: { xml: string }) {
  const parts = xml.split(/(<[^>]*>)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (!part) return null;
        if (!part.startsWith('<')) return <span key={index} className="text-slate-400">{part}</span>;
        if (part.startsWith('<!--')) return <span key={index} className="text-slate-600 italic">{part}</span>;
        const match = /^(<\/?)([\w:.-]+)([\s\S]*?)(\/?>)$/.exec(part);
        if (!match) return <span key={index} className="text-slate-400">{part}</span>;
        return (
          <span key={index}>
            <span className="text-slate-600">{match[1]}</span>
            <span className="font-medium text-violet-300">{match[2]}</span>
            <span className="text-amber-200/80">{match[3]}</span>
            <span className="text-slate-600">{match[4]}</span>
          </span>
        );
      })}
    </>
  );
}

function PassSummary({ trace, label }: { trace?: PipelineTraceResult; label: string }) {
  if (!trace) return null;
  const modified = trace.passes.filter((pass) => pass.modified).length;
  const skipped = trace.passes.filter((pass) => pass.skipped).length;
  return (
    <div className="compiler-pass-summary">
      <div className="flex min-w-0 items-center gap-2">
        <span className="h-2 w-2 shrink-0 rounded-full bg-cyan-300 shadow-[0_0_0_4px_rgba(103,232,249,0.1)]" />
        <span className="truncate text-[12px] font-semibold text-slate-200">{label}</span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-data text-[10px] text-slate-500">
        <span>{trace.passes.length} passes</span>
        <span>{modified} modified</span>
        <span>{skipped} skipped</span>
        <span>{(trace.total_timing_s * 1000).toFixed(2)}ms</span>
      </div>
    </div>
  );
}

function StageRail({
  active,
  onSelect,
  result,
  loading,
}: {
  active: StageId;
  onSelect: (stage: StageId) => void;
  result: CompiledSkillResult | null;
  loading: boolean;
}) {
  return (
    <nav className="compiler-stage-rail" aria-label="Compilation stages">
      <button className={`compiler-stage-tab ${active === 'overview' ? 'is-active' : ''}`} onClick={() => onSelect('overview')}>
        <span className="compiler-stage-index">00</span>
        <span className="min-w-0"><strong>Run overview</strong><small>Live compile trace</small></span>
        <ChevronRight className="ml-auto h-3.5 w-3.5" />
      </button>
      {STAGES.map((stage) => {
        const Icon = stage.icon;
        const status = stageStatus(stage.id, result, loading);
        return (
          <button key={stage.id} className={`compiler-stage-tab ${active === stage.id ? 'is-active' : ''}`} onClick={() => onSelect(stage.id)}>
            <span className="compiler-stage-index">{stage.number}</span>
            <span className="compiler-stage-icon"><Icon className="h-3.5 w-3.5" /></span>
            <span className="min-w-0"><strong>{stage.label}</strong><small>{stage.detail}</small></span>
            {status === 'running' ? <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-cyan-300" /> : status === 'done' ? <CheckCircle2 className="ml-auto h-3.5 w-3.5 text-cyan-300" /> : <span className="ml-auto h-1.5 w-1.5 rounded-full bg-slate-700" />}
          </button>
        );
      })}
    </nav>
  );
}

export const CompilerView: React.FC = () => {
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [instruction, setInstruction] = useState(EXAMPLES[0]);
  const [targetMode, setTargetMode] = useState<TargetMode>('universal');
  const [robotId, setRobotId] = useState('franka_panda');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CompiledSkillResult | null>(null);
  const [blockingDiagnostics, setBlockingDiagnostics] = useState<CompilerDiagnostic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeStage, setActiveStage] = useState<StageId>('overview');
  const [copied, setCopied] = useState(false);
  const [includeAI, setIncludeAI] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [compatibility, setCompatibility] = useState<RobotComparisonResult | null>(null);
  const [compatibilityLoading, setCompatibilityLoading] = useState(false);
  const [compatibilityError, setCompatibilityError] = useState<string | null>(null);
  const [matrix, setMatrix] = useState<UniversalCompileMatrix | null>(null);
  const [artifactBackend, setArtifactBackend] = useState<'ros2' | 'urscript' | 'abb_rapid'>('ros2');
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  const handleCompile = async () => {
    if (!instruction.trim()) return;
    setLoading(true);
    setError(null);
    setBlockingDiagnostics(null);
    setResult(null);
    setMatrix(null);
    setCompatibility(null);
    setActiveStage('overview');
    try {
      if (targetMode === 'universal') {
        const data = await RoboWeaverAPI.compileMatrix(instruction);
        setMatrix(data);
        const firstTarget = Object.values(data.targets)[0];
        if (firstTarget) setResult(firstTarget);
        else {
          const diagnostics = Object.values(data.failures).flat();
          setBlockingDiagnostics(diagnostics.length ? diagnostics : null);
          setError(diagnostics.length ? null : 'No concrete target accepted this program.');
        }
      } else {
        const data = await RoboWeaverAPI.compile(instruction, robotId, true, includeAI);
        setResult(data);
      }
    } catch (e) {
      if (e instanceof CompilationFailedError) setBlockingDiagnostics(e.diagnostics);
      else setError('The compiler runtime did not respond. Check the engine connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    RoboWeaverAPI.robots().then(setRobots).catch(() => {});
    // Load one real compile so the workspace demonstrates a complete run on first open.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    handleCompile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFleetCheck = async () => {
    if (!instruction.trim()) return;
    setCompatibilityLoading(true);
    setCompatibilityError(null);
    try {
      setCompatibility(await RoboWeaverAPI.compare(instruction));
    } catch {
      setCompatibilityError('Fleet compatibility could not be checked right now.');
    } finally {
      setCompatibilityLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(result.behavior_tree_xml);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  const handleXmlDownload = () => {
    if (!result) return;
    const blob = new Blob([result.behavior_tree_xml], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${result.ir.skill.id}.xml`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const selectedRobot = useMemo(() => robots.find((robot) => robot.id === robotId), [robots, robotId]);
  const compiledRobot = useMemo(
    () => robots.find((robot) => robot.id === result?.robot),
    [robots, result?.robot],
  );
  const supportsUrScript = compiledRobot?.manufacturer === 'Universal Robots';
  const supportsAbbRapid = compiledRobot?.manufacturer === 'ABB Robotics';
  const effectiveArtifactBackend =
    (artifactBackend === 'urscript' && !supportsUrScript) ||
    (artifactBackend === 'abb_rapid' && !supportsAbbRapid)
      ? 'ros2'
      : artifactBackend;
  const handleArtifactDownload = async () => {
    if (!result) return;
    setArtifactLoading(true);
    setArtifactError(null);
    try {
      const artifact = await RoboWeaverAPI.artifact(
        instruction,
        result.robot,
        effectiveArtifactBackend,
      );
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (artifactFailure) {
      setArtifactError(
        artifactFailure instanceof Error ? artifactFailure.message : 'Artifact generation failed.',
      );
    } finally {
      setArtifactLoading(false);
    }
  };
  const capabilities = result
    ? [...result.ir.required_capabilities.perception, ...result.ir.required_capabilities.manipulation, ...result.ir.required_capabilities.sensing]
    : [];
  const warningCount = result?.diagnostics.filter((diagnostic) => diagnostic.severity === 'warning').length ?? 0;
  const assumedPoseCount = result?.ir.objects.filter((object) => object.pose_source === 'assumed_default').length ?? 0;
  const userPoseCount = result?.ir.objects.filter((object) => object.pose_source === 'user_specified').length ?? 0;
  const perceivedPoseCount = result?.ir.objects.filter((object) => object.pose_source === 'perception').length ?? 0;
  const unverifiedClaimCount = result?.ir.required_capabilities.claims.filter((claim) => !claim.verified).length ?? 0;

  return (
    <div className="compiler-page">
      <div className="compiler-page-inner">
        <header className="compiler-hero">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="kicker">Build a robot program</span>
              <span className="compiler-live-pill"><span className="status-dot-online" /> works across robot profiles</span>
            </div>
            <h1>Tell RoboWeaver what the robot should do.</h1>
            <p>
              Write one request in plain language. RoboWeaver builds an ordered program, tests it
              against one or many robots, calculates target-specific motion, and prepares a download.
            </p>
          </div>
          <div className="compiler-hero-aside">
            <div className="compiler-hero-mark"><Sparkles className="h-4 w-4" /></div>
            <div>
              <span className="compiler-eyebrow">Choose your view</span>
              <strong>{showAdvanced ? 'Compiler details are visible' : 'Simple guidance is visible'}</strong>
              <small>{showAdvanced ? 'Inspect all six stages, evidence, and generated structures.' : 'See the result first, then open technical details when needed.'}</small>
              <button type="button" className="compiler-view-switch" onClick={() => setShowAdvanced((current) => !current)}>
                {showAdvanced ? 'Return to simple view' : 'Show compiler details'}
              </button>
            </div>
          </div>
        </header>

        <section className="compiler-input-layout">
          <div className="app-card compiler-source-card">
            <div className="compiler-source-topline">
              <div className="flex min-w-0 items-center gap-2.5">
                {showAdvanced && <span className="compiler-window-dots"><i /><i /><i /></span>}
                <span className="font-data text-[10px] uppercase tracking-[0.16em] text-slate-500">Step 1 · Describe the job</span>
              </div>
              <span className="font-data text-[10px] text-slate-600">Use everyday language</span>
            </div>
            <div className={`compiler-editor-line ${showAdvanced ? '' : 'is-simple'}`}>
              {showAdvanced && <span className="compiler-editor-gutter">01</span>}
              {showAdvanced && <span className="compiler-editor-prompt">›</span>}
              <textarea
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                rows={3}
                aria-label="Robot program intent"
                placeholder="Example: Pick up the red cube and place it in the blue bin"
              />
            </div>
            <div className="compiler-example-row">
              <span className="compiler-eyebrow">Try an example</span>
              <div className="flex min-w-0 flex-wrap gap-1.5">
                {EXAMPLES.map((example) => (
                  <button key={example} onClick={() => setInstruction(example)} className="compiler-example-chip">{example}</button>
                ))}
              </div>
            </div>
          </div>

          <aside className="app-card compiler-config-card">
            <div className="compiler-config-header">
              <div>
                <span className="compiler-eyebrow">Step 2 · Choose the robots</span>
                <h2>Where should this program run?</h2>
              </div>
              <Network className="h-4 w-4 text-cyan-300" />
            </div>
            <div className="compiler-mode-switch" role="tablist" aria-label="Compilation target mode">
              <button className={targetMode === 'universal' ? 'is-active' : ''} onClick={() => setTargetMode('universal')} role="tab" aria-selected={targetMode === 'universal'}>
                <span>Try several robots</span><small>universal check</small>
              </button>
              <button className={targetMode === 'profile' ? 'is-active' : ''} onClick={() => setTargetMode('profile')} role="tab" aria-selected={targetMode === 'profile'}>
                <span>Use one robot</span><small>single target</small>
              </button>
            </div>
            {targetMode === 'universal' ? (
              <div className="compiler-scope-note">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-cyan-300" />
                <span>The same program is checked independently for every registered robot. Passing one robot does not make the others pass.</span>
              </div>
            ) : (
              <label className="block">
                <span className="compiler-eyebrow mb-1.5 block">Robot profile</span>
                <select value={robotId} onChange={(event) => setRobotId(event.target.value)} className="compiler-select">
                  {robots.map((robot) => <option key={robot.id} value={robot.id}>{robot.name} · {robot.dof}-DOF</option>)}
                </select>
              </label>
            )}
            <div className="compiler-config-footer">
              <button type="button" disabled={targetMode === 'universal'} title={targetMode === 'universal' ? 'AI explanation is available for a single selected profile.' : undefined} onClick={() => setIncludeAI((current) => !current)} className={`compiler-toggle ${includeAI && targetMode === 'profile' ? 'is-on' : ''}`}>
                <Brain className="h-3.5 w-3.5" /> {targetMode === 'universal' ? 'AI help: one robot only' : `AI explanation ${includeAI ? 'on' : 'off'}`}
              </button>
              {selectedRobot && targetMode === 'profile' && <span className="font-data text-[10px] text-slate-600">{selectedRobot.manufacturer}</span>}
            </div>
            <button onClick={handleCompile} disabled={loading || !instruction.trim()} className="btn-neon compiler-compile-button">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {loading ? 'Building and checking…' : 'Compile and verify'}
              <span className="ml-auto font-data text-[10px] opacity-60">⌘ ↵</span>
            </button>
          </aside>
        </section>

        {showAdvanced && <StageRail active={activeStage} onSelect={setActiveStage} result={result} loading={loading} />}

        {error && <div className="compiler-alert compiler-alert-error"><AlertTriangle className="h-4 w-4 shrink-0" /><span>{error}</span></div>}

        {blockingDiagnostics && (
          <section className="app-card compiler-blocking-card">
            <div className="compiler-section-heading"><AlertOctagon className="h-4 w-4 text-rose-300" /><div><span className="compiler-eyebrow">This program could not be built</span><h2>Review these required changes</h2></div></div>
            <div className="compiler-diagnostics-grid">{blockingDiagnostics.map((diagnostic, index) => <DiagnosticCard key={`${diagnostic.code}-${index}`} diagnostic={diagnostic} />)}</div>
          </section>
        )}

        {result && (
          <>
            <section className="compiler-result-layout animate-fade-in">
              <div className="compiler-main-stage">
                <div className="compiler-run-banner">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="compiler-success-icon"><CheckCircle2 className="h-4 w-4" /></span>
                    <div className="min-w-0"><span className="compiler-eyebrow">Compilation complete</span><strong className="block truncate text-[13px] text-white">{result.ir.skill.id}</strong></div>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-1 font-data text-[10px] text-slate-500"><span>IR {result.ir.ir_version}</span><span>{result.tasks.length} tasks</span><span>{warningCount} warnings</span>{matrix && <span>{Object.keys(matrix.targets).length} lowerings</span>}</div>
                </div>

                {!showAdvanced && (
                  <div className="compiler-simple-result">
                    <section className="compiler-simple-intro">
                      <div>
                        <span className="compiler-eyebrow">Your result</span>
                        <h2>The program is ready for review.</h2>
                        <p>
                          RoboWeaver understood the request, made an executable plan, and produced
                          target-specific motion for {matrix ? `${Object.keys(matrix.targets).length} robot${Object.keys(matrix.targets).length === 1 ? '' : 's'}` : compiledRobot?.name ?? result.robot}.
                        </p>
                      </div>
                      <button type="button" className="compiler-secondary-button" onClick={() => setShowAdvanced(true)}>
                        <Code2 className="h-3.5 w-3.5" /> Open compiler details
                      </button>
                    </section>

                    <div className="compiler-simple-grid">
                      <section className="compiler-simple-card">
                        <span className="compiler-simple-card-icon"><ScanSearch className="h-4 w-4" /></span>
                        <span className="compiler-eyebrow">1 · What it understood</span>
                        <h3>{result.intent.action} {result.intent.object_name}</h3>
                        <p>{Math.round(result.intent.confidence * 100)}% parser confidence · {Object.keys(result.intent.parameters).length} extracted parameter{Object.keys(result.intent.parameters).length === 1 ? '' : 's'}</p>
                      </section>
                      <section className="compiler-simple-card">
                        <span className="compiler-simple-card-icon"><Workflow className="h-4 w-4" /></span>
                        <span className="compiler-eyebrow">2 · What it planned</span>
                        <h3>{result.tasks.length} ordered robot action{result.tasks.length === 1 ? '' : 's'}</h3>
                        <p>{result.tasks.slice(0, 3).map((task) => task.description).join(' → ')}{result.tasks.length > 3 ? ' → …' : ''}</p>
                      </section>
                      <section className="compiler-simple-card">
                        <span className="compiler-simple-card-icon"><ShieldCheck className="h-4 w-4" /></span>
                        <span className="compiler-eyebrow">3 · Which robots passed</span>
                        <h3>{matrix ? `${Object.keys(matrix.targets).length} accepted · ${Object.keys(matrix.failures).length} rejected` : `${compiledRobot?.name ?? result.robot} accepted`}</h3>
                        <p>Each accepted robot received its own joint, IK, trajectory, capability, and safety checks.</p>
                      </section>
                      <section className="compiler-simple-card compiler-simple-card-download">
                        <span className="compiler-simple-card-icon"><Download className="h-4 w-4" /></span>
                        <span className="compiler-eyebrow">4 · Download the output</span>
                        <h3>Build a runtime package</h3>
                        <p>The package uses the currently selected accepted robot: {compiledRobot?.name ?? result.robot}.</p>
                        <div className="compiler-simple-actions">
                          <select aria-label="Download format" value={effectiveArtifactBackend} onChange={(event) => setArtifactBackend(event.target.value as 'ros2' | 'urscript' | 'abb_rapid')} className="compiler-select compiler-artifact-select">
                            <option value="ros2">ROS 2 package (.zip)</option>
                            <option value="urscript" disabled={!supportsUrScript}>URScript (.script)</option>
                            <option value="abb_rapid" disabled={!supportsAbbRapid}>ABB RAPID (.mod)</option>
                          </select>
                          <button onClick={handleArtifactDownload} disabled={artifactLoading} className="compiler-action-button is-primary">
                            {artifactLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                            {artifactLoading ? 'Building…' : 'Build download'}
                          </button>
                        </div>
                        {artifactError && <p className="compiler-simple-error">{artifactError}</p>}
                      </section>
                    </div>

                    <section className="compiler-simple-assumptions">
                      <div className="compiler-section-heading">
                        <AlertTriangle className="h-4 w-4 text-amber-300" />
                        <div><span className="compiler-eyebrow">Know before using hardware</span><h2>What is proven—and what is not</h2></div>
                      </div>
                      <div className="compiler-assumption-list">
                        <div className={assumedPoseCount ? 'is-warning' : 'is-ready'}><strong>Object position</strong><span>{assumedPoseCount ? `${assumedPoseCount} position${assumedPoseCount === 1 ? '' : 's'} assumed; provide measured poses before deployment.` : 'No default object position was consumed.'}</span></div>
                        <div className="is-warning"><strong>Environment collisions</strong><span>No room or workcell geometry was checked.</span></div>
                        <div className="is-warning"><strong>Physical robot</strong><span>This is software verification, not hardware certification or a live robot test.</span></div>
                      </div>
                    </section>

                    <section className="compiler-simple-flow">
                      <div className="compiler-section-heading"><Workflow className="h-4 w-4 text-cyan-300" /><div><span className="compiler-eyebrow">How the compiler works</span><h2>Six real stages are available to inspect</h2></div></div>
                      <div className="compiler-plain-flow">
                        {STAGES.map((stage) => {
                          const Icon = stage.icon;
                          return (
                            <button key={stage.id} type="button" onClick={() => { setActiveStage(stage.id); setShowAdvanced(true); }}>
                              <span>{stage.number}</span><Icon className="h-4 w-4" /><strong>{stage.label}</strong><small>{stage.detail}</small>
                            </button>
                          );
                        })}
                      </div>
                    </section>
                  </div>
                )}

                {showAdvanced && activeStage === 'overview' && (
                  <div className="compiler-stage-content">
                    <div className="compiler-overview-grid">
                      <div className="compiler-overview-card compiler-overview-card-wide"><span className="compiler-eyebrow">Program shape</span><div className="compiler-flow-strip"><div><span>source</span><strong>intent</strong></div><ArrowRight /><div><span>semantic</span><strong>ProgramSpec</strong></div><ArrowRight /><div><span>lowered</span><strong>{result.ir.execution.robot_id}</strong></div><ArrowRight /><div><span>runtime</span><strong>artifact</strong></div></div></div>
                      <div className="compiler-overview-card"><span className="compiler-eyebrow">Front-end confidence</span><strong className="compiler-big-number">{Math.round(result.intent.confidence * 100)}<small>%</small></strong><span className="text-[11px] text-slate-500">{result.intent.action} intent resolved</span></div>
                      <div className="compiler-overview-card"><span className="compiler-eyebrow">Required contract</span><strong className="compiler-big-number">{capabilities.length}<small> caps</small></strong><span className="text-[11px] text-slate-500">checked during verification</span></div>
                    </div>
                    <div className="compiler-section-heading"><Gauge className="h-4 w-4 text-cyan-300" /><div><span className="compiler-eyebrow">Execution trace</span><h2>What the compiler actually ran</h2></div></div>
                    <div className="compiler-trace-list">
                      <button onClick={() => setActiveStage('frontend')}><span className="compiler-trace-number">01</span><span><strong>Parse intent</strong><small>{result.intent.action} · {result.intent.object_name}</small></span><CheckCircle2 /></button>
                      <button onClick={() => setActiveStage('tasks')}><span className="compiler-trace-number">02</span><span><strong>Decompose task graph</strong><small>{result.tasks.length} executable task segments</small></span><CheckCircle2 /></button>
                      <button onClick={() => setActiveStage('ir')}><span className="compiler-trace-number">03</span><span><strong>Build typed RoboIR contract</strong><small>{result.ir.objects.length} objects · {capabilities.length} required capabilities</small></span><CheckCircle2 /></button>
                      <button onClick={() => setActiveStage('passes')}><span className="compiler-trace-number">04</span><span><strong>Run optimization + verification passes</strong><small>{(result.pipeline?.passes.length ?? 0) + (result.skill_pipeline?.passes.length ?? 0)} measured passes</small></span><CheckCircle2 /></button>
                      <button onClick={() => setActiveStage('backend')}><span className="compiler-trace-number">05</span><span><strong>Lower to motion backend</strong><small>{result.ir.execution.planner} · {result.ir.execution.dof}-DOF reference</small></span><CheckCircle2 /></button>
                      <button onClick={() => setActiveStage('artifact')}><span className="compiler-trace-number">06</span><span><strong>Emit runtime artifact</strong><small>ROS 2 package · URScript · BehaviorTree XML</small></span><CheckCircle2 /></button>
                    </div>
                  </div>
                )}

                {showAdvanced && activeStage === 'frontend' && (
                  <div className="compiler-stage-content"><PanelTitle icon={ScanSearch} eyebrow="Stage 01 · front-end" title="Resolve human intent into typed values" meta={result.ir.source.parser} /><div className="compiler-stat-grid"><Metric label="Action" value={result.intent.action} accent /><Metric label="Object" value={result.intent.object_name} /><Metric label="Confidence" value={`${Math.round(result.intent.confidence * 100)}%`} /><Metric label="Parameters" value={`${Object.keys(result.intent.parameters).length}`} /></div><div className="compiler-detail-grid"><div className="compiler-detail-card"><span className="compiler-eyebrow">Normalized source</span><p className="font-data text-[12px] leading-6 text-slate-300">{result.ir.source.raw_instruction}</p></div><div className="compiler-detail-card"><span className="compiler-eyebrow">Resolved parameters</span><div className="space-y-2">{Object.entries(result.intent.parameters).map(([key, value]) => <div key={key} className="flex items-center justify-between gap-3 font-data text-[11px]"><span className="text-slate-500">{key}</span><span className="text-cyan-200">{String(value)}</span></div>)}</div></div></div></div>
                )}

                {showAdvanced && activeStage === 'tasks' && (
                  <div className="compiler-stage-content"><PanelTitle icon={Workflow} eyebrow="Stage 02 · decomposition" title="Turn intent into executable work" meta={`${result.tasks.length} task nodes`} /><div className="compiler-task-list">{result.tasks.map((task, index) => <div key={`${task.type}-${index}`} className="compiler-task-row"><span className="compiler-task-index">{String(index + 1).padStart(2, '0')}</span><span className="compiler-task-type">{task.type}</span><span className="min-w-0 flex-1 text-[12px] text-slate-300">{task.description}</span><CheckCircle2 className="h-4 w-4 shrink-0 text-cyan-300" /></div>)}</div><div className="compiler-inline-note"><Workflow className="h-4 w-4 text-violet-300" /><span>This is the compiler’s execution plan—not a visual tree. Each task can be lowered to a different runtime backend later.</span></div></div>
                )}

                {showAdvanced && activeStage === 'ir' && (
                  <div className="compiler-stage-content"><PanelTitle icon={GitBranch} eyebrow="Stage 03 · intermediate representation" title="Shared program plus verified target lowering" meta={`v${result.ir.ir_version}`} /><div className="compiler-detail-grid compiler-ir-grid"><div className="compiler-detail-card"><span className="compiler-eyebrow">Entities</span><div className="space-y-2">{result.ir.objects.map((object) => <div key={object.id} className="flex flex-wrap items-center justify-between gap-2"><span className="text-[12px] text-slate-200">{object.name}</span><div className="flex gap-1.5"><Tag tone="cyan">{object.role}</Tag><Tag>{object.pose_source}</Tag></div></div>)}</div></div><div className="compiler-detail-card"><span className="compiler-eyebrow">Constraints</span><div className="space-y-2 font-data text-[11px] text-slate-300"><div className="flex justify-between gap-3"><span className="text-slate-500">payload</span><span>{result.ir.constraints.payload_kg ?? 'unbounded'} kg</span></div><div className="flex justify-between gap-3"><span className="text-slate-500">precision</span><span>{result.ir.constraints.precision_mm ?? 'unspecified'} mm</span></div><div className="flex justify-between gap-3"><span className="text-slate-500">collision model</span><span>{result.ir.verification.collision_check ? 'verified' : 'not modeled'}</span></div><div className="flex justify-between gap-3"><span className="text-slate-500">safety checks</span><span>{result.ir.verification.safety_checks.length} checks</span></div></div></div><div className="compiler-detail-card compiler-detail-card-wide"><span className="compiler-eyebrow">Required capabilities</span><div className="flex flex-wrap gap-1.5">{capabilities.length ? capabilities.map((capability) => <Tag key={capability} tone="violet">{capability}</Tag>) : <span className="text-[11px] text-slate-500">No extra capabilities declared.</span>}</div></div></div></div>
                )}

                {showAdvanced && activeStage === 'passes' && (
                  <div className="compiler-stage-content"><PanelTitle icon={Layers3} eyebrow="Stage 04 · compiler infrastructure" title="Inspect real pass-by-pass work" meta="measured at runtime" /><div className="compiler-pass-strip"><PassSummary trace={result.skill_pipeline} label="CompiledSkill optimization" /><PassSummary trace={result.pipeline} label="RoboIR verification" /></div><PipelineTraceView pipeline={result.pipeline} skillPipeline={result.skill_pipeline} /><div className="compiler-inline-note"><Code2 className="h-4 w-4 text-violet-300" /><span>{result.native_mlir?.status === 'succeeded' ? `Native ${result.native_mlir.version ?? 'mlir-opt'} executed ${result.native_mlir.pass_pipeline.join(' → ')}; output digest ${result.native_mlir.output_sha256?.slice(0, 12)}.` : result.native_mlir?.detail ?? 'Native MLIR evidence was not returned.'}</span></div>{result.diagnostics.length > 0 && <div className="compiler-diagnostics-grid">{result.diagnostics.map((diagnostic, index) => <DiagnosticCard key={`${diagnostic.code}-${index}`} diagnostic={diagnostic} />)}</div>}</div>
                )}

                {showAdvanced && activeStage === 'backend' && (
                  <div className="compiler-stage-content"><PanelTitle icon={Boxes} eyebrow="Stage 05 · backend lowering" title="Bind the shared program to one embodiment" meta={result.ir.execution.robot_id} /><div className="compiler-lowering-banner"><div className="compiler-lowering-node"><span>shared</span><strong>ProgramSpec</strong></div><ArrowRight /><div className="compiler-lowering-node is-active"><span>verified target</span><strong>{result.ir.execution.robot_id}</strong></div><ArrowRight /><div className="compiler-lowering-node"><span>motion</span><strong>{result.ir.execution.planner}</strong></div></div><div className="compiler-stat-grid"><Metric label="DOF model" value={`${result.ir.execution.dof}`} /><Metric label="Controller" value={result.ir.execution.controller} /><Metric label="Planner" value={result.ir.execution.planner} /><Metric label="Legalization rewrites" value={`${result.ir.lowering?.legalization_trace.length ?? 0}`} accent /></div>{result.ir.lowering?.legalization_trace.length ? <div className="compiler-detail-card"><span className="compiler-eyebrow">Full-conversion rewrite trace</span><div className="mt-3 space-y-1 font-data text-[10.5px] text-slate-400">{result.ir.lowering.legalization_trace.map((entry, index) => <div key={`${entry}-${index}`}>{String(index + 1).padStart(2, '0')} · {entry}</div>)}</div></div> : null}<div className="compiler-inline-note"><ShieldCheck className="h-4 w-4 text-cyan-300" /><span>{targetMode === 'universal' ? 'This is one independently planned lowering from the shared source digest. Switch targets in the Verified lowerings panel to inspect different joints, IK evidence and trajectories.' : 'This profile is independently planned and verified. Change profiles without rewriting the source program.'}</span></div></div>
                )}

                {showAdvanced && activeStage === 'artifact' && (
                  <div className="compiler-stage-content"><div className="flex flex-wrap items-start justify-between gap-4"><PanelTitle icon={TerminalSquare} eyebrow="Stage 06 · emitted artifacts" title="Download a target runtime" meta={result.ir.execution.robot_id} /><div className="flex flex-wrap gap-2"><select aria-label="Artifact backend" value={effectiveArtifactBackend} onChange={(event) => setArtifactBackend(event.target.value as 'ros2' | 'urscript' | 'abb_rapid')} className="compiler-select compiler-artifact-select"><option value="ros2">ROS 2 package (.zip)</option><option value="urscript" disabled={!supportsUrScript}>URScript (.script)</option><option value="abb_rapid" disabled={!supportsAbbRapid}>ABB RAPID (.mod)</option></select><button onClick={handleArtifactDownload} disabled={artifactLoading} className="compiler-action-button is-primary">{artifactLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}{artifactLoading ? 'Building…' : 'Build artifact'}</button></div></div>{artifactError && <div className="compiler-alert compiler-alert-error"><AlertTriangle className="h-4 w-4 shrink-0" /><span>{artifactError}</span></div>}<div className="compiler-artifact-meta"><Tag tone="green">complete RoboIR-derived output</Tag><Tag tone="cyan">{result.ir.lowering?.trajectories.reduce((total, trajectory) => total + trajectory.waypoints.length, 0) ?? 0} waypoints</Tag><Tag>{result.ir.lowering?.joint_names.length ?? 0} exact joints</Tag><span className="ml-auto font-data text-[10px] text-slate-600">reproducible source id · {result.ir.skill.id.slice(-12)}</span></div><div className="compiler-inline-note"><TerminalSquare className="h-4 w-4 text-cyan-300" /><span>ROS 2 export is a complete ament_python package with controller client, launch/config files, manifest, exact joints and trajectories. URScript is emitted only for a verified Universal Robots profile; ABB RAPID only for a verified ABB profile.</span></div><div className="flex flex-wrap items-center justify-between gap-3"><PanelTitle icon={Code2} eyebrow="Additional adapter" title="BehaviorTree XML preview" meta="application/xml" /><div className="flex gap-2"><button onClick={handleCopy} className="compiler-action-button">{copied ? <Check className="h-3.5 w-3.5 text-cyan-300" /> : <Copy className="h-3.5 w-3.5" />}{copied ? 'Copied' : 'Copy XML'}</button><button onClick={handleXmlDownload} className="compiler-action-button"><Download className="h-3.5 w-3.5" />Export XML</button></div></div><pre className="compiler-code-block"><XmlHighlight xml={result.behavior_tree_xml} /></pre></div>
                )}
              </div>

              <aside className="compiler-side-rail">
                {showAdvanced && <section className="app-card compiler-summary-card"><PanelTitle icon={GitBranch} eyebrow="Technical program" title="Complete RoboIR snapshot" /><div className="compiler-summary-list"><Metric label="skill" value={result.ir.skill.id} /><Metric label="action" value={result.ir.intent.action} accent /><Metric label="objects" value={`${result.ir.objects.length}`} /><Metric label="waypoints" value={`${result.ir.lowering?.trajectories.reduce((total, trajectory) => total + trajectory.waypoints.length, 0) ?? 0}`} /></div><div className="mt-4 flex flex-wrap gap-1.5"><Tag tone="cyan">{result.ir.source.parser}</Tag><Tag tone="violet">RoboIR v{result.ir.ir_version}</Tag><Tag tone="green">structurally verified</Tag></div></section>}
                <section className="app-card compiler-summary-card"><PanelTitle icon={ShieldCheck} eyebrow="What is proven?" title="Evidence and assumptions" /><div className="compiler-evidence-list"><EvidenceRow label="Request parsing" value="recorded" detail={`${result.ir.source.parser} · ${Math.round(result.intent.confidence * 100)}% confidence`} tone="cyan" /><EvidenceRow label="Object position" value={assumedPoseCount ? 'assumed' : perceivedPoseCount ? 'measured' : userPoseCount ? 'provided' : 'not required'} detail={assumedPoseCount ? `${assumedPoseCount} object pose${assumedPoseCount === 1 ? '' : 's'} use disclosed defaults` : perceivedPoseCount ? `${perceivedPoseCount} perception observation${perceivedPoseCount === 1 ? '' : 's'}` : userPoseCount ? `${userPoseCount} complete Cartesian pose${userPoseCount === 1 ? '' : 's'}` : 'No scene object pose consumed'} tone={assumedPoseCount ? 'amber' : 'green'} /><EvidenceRow label="Robot motion" value="computed" detail={`${result.ir.lowering?.ik_solutions.length ?? 0} IK solves · ${result.ir.lowering?.trajectories.length ?? 0} trajectories`} tone="green" /><EvidenceRow label="Capabilities" value={unverifiedClaimCount ? 'partial' : 'declared'} detail={unverifiedClaimCount ? `${unverifiedClaimCount} claim${unverifiedClaimCount === 1 ? '' : 's'} lack implementation evidence` : 'Every required claim has declared evidence'} tone={unverifiedClaimCount ? 'amber' : 'green'} /><EvidenceRow label="Room collisions" value="not checked" detail="No environment collision model was evaluated" tone="neutral" /></div></section>
                {matrix && <section className="app-card compiler-summary-card"><PanelTitle icon={Boxes} eyebrow="Robots tested" title="Accepted and rejected targets" meta={matrix.source_digest.slice(0, 8)} /><div className="mt-4 space-y-1.5">{Object.entries(matrix.targets).map(([id, target]) => <button type="button" key={id} onClick={() => setResult(target)} className={`compiler-target-row w-full text-left ${result.robot === id ? 'is-active' : ''}`}><span className="font-data text-[10px] text-cyan-300">{target.ir.execution.dof}D</span><span className="min-w-0 flex-1 truncate font-data text-[10.5px] text-slate-300">{id}</span><span className="font-data text-[10px] text-emerald-300">accepted</span></button>)}{Object.entries(matrix.failures).map(([id, diagnostics]) => <div key={id} className="compiler-target-row is-skipped"><span className="font-data text-[10px] text-slate-600">—</span><span className="min-w-0 flex-1 truncate font-data text-[10.5px] text-slate-500">{id}</span><span className="font-data text-[10px] text-amber-300" title={diagnostics.map((item) => item.message).join('; ')}>rejected</span></div>)}</div></section>}
                {showAdvanced && <section className="app-card compiler-summary-card"><div className="flex items-start justify-between gap-3"><PanelTitle icon={Network} eyebrow="Cross-target validation" title="Check the fleet" /><span className="font-data text-[10px] text-slate-600">optional</span></div><p className="mt-3 text-[11.5px] leading-5 text-slate-400">Compile the same instruction across compatible registered embodiments and rank the real cost.</p><button onClick={handleFleetCheck} disabled={compatibilityLoading} className="compiler-secondary-button mt-4 w-full">{compatibilityLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Boxes className="h-3.5 w-3.5" />}{compatibilityLoading ? 'Checking targets…' : 'Check fleet compatibility'}</button>{compatibilityError && <p className="mt-3 text-[11px] text-rose-300">{compatibilityError}</p>}{compatibility && <div className="mt-4 space-y-1.5"><div className="mb-2 flex items-center justify-between"><span className="compiler-eyebrow">ranked targets</span><Tag tone="violet">{compatibility.candidate_source}</Tag></div>{compatibility.ranked.slice(0, 4).map((entry, index) => <div key={entry.robot} className="compiler-target-row"><span className="font-data text-[10px] text-slate-600">0{index + 1}</span><span className="min-w-0 flex-1 truncate font-data text-[10.5px] text-slate-300">{entry.robot}</span><span className="font-data text-[10px] text-cyan-200">{entry.cost.estimated_cycle_time_s.toFixed(2)}s</span></div>)}{Object.entries(compatibility.skipped).slice(0, 2).map(([id, reason]) => <div key={id} className="compiler-target-row is-skipped"><span className="font-data text-[10px] text-slate-600">—</span><span className="min-w-0 flex-1 truncate font-data text-[10.5px] text-slate-500" title={reason}>{id}</span><span className="font-data text-[10px] text-amber-300">skipped</span></div>)}</div>}</section>}
                {showAdvanced && (result.explanation !== undefined || result.explanation_error) && <section className="app-card compiler-summary-card compiler-ai-card"><PanelTitle icon={Brain} eyebrow="Local annotation" title="Why this compiled" meta={result.explanation_model ?? 'local model'} />{result.explanation ? <p className="mt-3 whitespace-pre-wrap text-[11.5px] leading-5 text-slate-300">{result.explanation}</p> : <p className="mt-3 text-[11px] text-amber-300">{result.explanation_error ?? 'No local explanation returned.'}</p>}</section>}
              </aside>
            </section>

            {result.diagnostics.length > 0 && (!showAdvanced || activeStage !== 'passes') && <section className="app-card compiler-diagnostics-section"><div className="compiler-section-heading"><AlertTriangle className="h-4 w-4 text-amber-300" /><div><span className="compiler-eyebrow">What needs attention</span><h2>{result.diagnostics.length} non-blocking note{result.diagnostics.length === 1 ? '' : 's'}</h2></div></div><div className="compiler-diagnostics-grid">{result.diagnostics.map((diagnostic, index) => <DiagnosticCard key={`${diagnostic.code}-${index}`} diagnostic={diagnostic} />)}</div></section>}
          </>
        )}

        {!result && !blockingDiagnostics && loading && <div className="compiler-loading-state"><Loader2 className="h-5 w-5 animate-spin text-cyan-300" /><span>Running front-end, IR passes, verification, and backend lowering…</span></div>}
      </div>
    </div>
  );
};
