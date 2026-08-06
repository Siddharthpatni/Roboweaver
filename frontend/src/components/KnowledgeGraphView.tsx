'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCenter,
  forceCollide,
  Simulation,
  SimulationNodeDatum,
  SimulationLinkDatum,
} from 'd3-force';
import { Share2, Download, Search, X, Loader2, AlertTriangle, Route, Sparkles } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { AIEnrichmentResult, KnowledgeGraphNode } from '../types';

interface SimNode extends KnowledgeGraphNode, SimulationNodeDatum {}
interface SimLink extends SimulationLinkDatum<SimNode> {
  relation: string;
}

const NODE_COLOR: Record<string, string> = {
  ROBOT: '#fb7185',
  PACKAGE: '#22d3ee',
  SKILL: '#a78bfa',
};
const NODE_RADIUS: Record<string, number> = {
  ROBOT: 9,
  PACKAGE: 7,
  SKILL: 7,
};
const DEFAULT_COLOR = '#94a3b8';

const WIDTH = 960;
const HEIGHT = 600;

function resolve(end: string | number | SimNode, byId: Map<string, SimNode>): SimNode | undefined {
  if (typeof end === 'object') return end;
  return byId.get(String(end));
}

/**
 * A real force-directed view of the same knowledge graph
 * `roboweaver graph export-obsidian` writes as cross-linked Obsidian notes
 * (knowledge/ingest_registry.py, knowledge/obsidian_export.py) -- every node
 * and edge here is `/api/graph`'s real response, laid out with a real d3-force
 * physics simulation (not a static hand-placed diagram), and the "Find path"
 * feature calls the same real BFS `/api/graph/path` uses.
 */
export const KnowledgeGraphView: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  // Real state, not a ref: the rAF loop below re-sets this every frame (a new
  // array wrapper around the same, still-d3-owned node objects) specifically
  // so the render body never has to read a ref's `.current` to know the
  // simulation moved -- refs are for imperative access from event handlers
  // (drag, pan, zoom below), not values the render output depends on.
  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [links, setLinks] = useState<SimLink[]>([]);
  const [selected, setSelected] = useState<SimNode | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [pathFrom, setPathFrom] = useState<SimNode | null>(null);
  const [pathTo, setPathTo] = useState<SimNode | null>(null);
  const [pathIds, setPathIds] = useState<string[] | null>(null);
  const [pathLoading, setPathLoading] = useState(false);
  const [pathError, setPathError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [enrichment, setEnrichment] = useState<AIEnrichmentResult | null>(null);
  const [enrichmentError, setEnrichmentError] = useState<string | null>(null);
  const [nodeSummary, setNodeSummary] = useState<string | null>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });

  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragNode = useRef<SimNode | null>(null);
  const panRef = useRef<{ startX: number; startY: number; startTX: number; startTY: number } | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    RoboWeaverAPI.graph()
      .then((g) => {
        const simNodes: SimNode[] = g.nodes.map((n) => ({ ...n }));
        const validIds = new Set(simNodes.map((n) => n.id));
        const simLinks: SimLink[] = g.edges
          .filter((e) => validIds.has(e.source_id) && validIds.has(e.target_id))
          .map((e) => ({ source: e.source_id, target: e.target_id, relation: e.relation }));

        const sim = forceSimulation(simNodes)
          .force('charge', forceManyBody().strength(-280))
          .force(
            'link',
            // No fixed .strength() override -- d3's default (~1/min(degree))
            // pulls high-degree hub nodes (a no-sensor-requirement skill
            // connects to all 11 robots) less aggressively than a normal
            // edge, which is what actually keeps a hub-heavy graph like this
            // one from collapsing into a dense knot.
            forceLink<SimNode, SimLink>(simLinks)
              .id((d) => d.id)
              .distance(85)
          )
          .force('center', forceCenter(WIDTH / 2, HEIGHT / 2))
          .force('collide', forceCollide<SimNode>().radius(22));

        simRef.current = sim;
        setLinks(simLinks);
        setLoading(false);

        const loop = () => {
          // A new array reference each frame so React re-renders; the node
          // objects inside are the same ones d3 mutates in place, and
          // `links[i].source/target` (resolved by forceLink to those same
          // objects after the simulation's first tick) read fresh x/y too.
          setNodes([...sim.nodes()]);
          rafRef.current = requestAnimationFrame(loop);
        };
        rafRef.current = requestAnimationFrame(loop);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      simRef.current?.stop();
    };
  }, []);

  const nodesById = new Map<string, SimNode>();
  for (const n of nodes) nodesById.set(n.id, n);

  const pathEdgeSet = useMemo(() => {
    const s = new Set<string>();
    if (!pathIds) return s;
    for (let i = 0; i < pathIds.length - 1; i++) {
      s.add(`${pathIds[i]}|${pathIds[i + 1]}`);
      s.add(`${pathIds[i + 1]}|${pathIds[i]}`);
    }
    return s;
  }, [pathIds]);

  const screenToGraph = useCallback(
    (clientX: number, clientY: number) => {
      const svg = svgRef.current;
      if (!svg) return { x: 0, y: 0 };
      const rect = svg.getBoundingClientRect();
      const sx = ((clientX - rect.left) / rect.width) * WIDTH;
      const sy = ((clientY - rect.top) / rect.height) * HEIGHT;
      return { x: (sx - transform.x) / transform.k, y: (sy - transform.y) / transform.k };
    },
    [transform]
  );

  const onNodePointerDown = (e: React.PointerEvent, node: SimNode) => {
    e.stopPropagation();
    dragNode.current = node;
    simRef.current?.alphaTarget(0.3).restart();
  };

  const onSvgPointerMove = (e: React.PointerEvent) => {
    if (dragNode.current) {
      const { x, y } = screenToGraph(e.clientX, e.clientY);
      dragNode.current.fx = x;
      dragNode.current.fy = y;
      return;
    }
    if (panRef.current) {
      const dx = e.clientX - panRef.current.startX;
      const dy = e.clientY - panRef.current.startY;
      setTransform((t) => ({ ...t, x: panRef.current!.startTX + dx, y: panRef.current!.startTY + dy }));
    }
  };

  const onSvgPointerUp = () => {
    if (dragNode.current) {
      dragNode.current.fx = null;
      dragNode.current.fy = null;
      simRef.current?.alphaTarget(0);
      dragNode.current = null;
    }
    panRef.current = null;
  };

  const onSvgPointerDown = (e: React.PointerEvent) => {
    panRef.current = { startX: e.clientX, startY: e.clientY, startTX: transform.x, startTY: transform.y };
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    setTransform((t) => ({ ...t, k: Math.min(4, Math.max(0.25, t.k * factor)) }));
  };

  const runFindPath = async () => {
    if (!pathFrom || !pathTo) return;
    setPathLoading(true);
    setPathError(null);
    setPathIds(null);
    try {
      const res = await RoboWeaverAPI.graphPath(pathFrom.id, pathTo.id);
      if (res.path === null) {
        setPathError(`No path within 6 hops between ${pathFrom.name} and ${pathTo.name} -- a real "unreachable", not a failed request.`);
      } else {
        setPathIds(res.path);
      }
    } catch {
      setPathError('Could not reach the RoboWeaver backend.');
    } finally {
      setPathLoading(false);
    }
  };

  const handleDownloadObsidian = async () => {
    setDownloading(true);
    try {
      const blob = await RoboWeaverAPI.graphExportObsidian();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'roboweaver-knowledge-graph-obsidian.zip';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // handled by leaving the button re-enabled; no separate toast system exists in this app.
    } finally {
      setDownloading(false);
    }
  };

  const handleAIEnrich = async () => {
    setEnriching(true);
    setEnrichmentError(null);
    try {
      const result = await RoboWeaverAPI.aiEnrich('edges');
      setEnrichment(result);
    } catch (e) {
      setEnrichmentError(e instanceof Error ? e.message : 'The local Ollama enrichment model is unavailable.');
    } finally {
      setEnriching(false);
    }
  };

  const handleAINote = async () => {
    if (!selected) return;
    setEnriching(true);
    setEnrichmentError(null);
    setNodeSummary(null);
    try {
      const result = await RoboWeaverAPI.aiEnrich('summary', selected.id);
      setNodeSummary(result.summaries?.[0]?.summary ?? null);
    } catch (e) {
      setEnrichmentError(e instanceof Error ? e.message : 'The local Ollama enrichment model is unavailable.');
    } finally {
      setEnriching(false);
    }
  };

  const matchQuery = search.trim().toLowerCase();
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const n of nodes) c[n.type] = (c[n.type] ?? 0) + 1;
    return c;
  }, [nodes]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex items-center gap-2.5 text-slate-500 text-[13px]">
          <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
          Loading the real knowledge graph…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="flex items-center gap-2.5 px-4 py-3 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[13px]">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          Could not reach the RoboWeaver backend. Start it with: roboweaver dashboard
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <span className="kicker">Knowledge Graph</span>
            <h1 className="text-[19px] font-semibold text-white mt-1">Robots, packages, and skills — one real graph</h1>
            <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-2xl">
              Every node and edge below is <code className="font-data text-slate-300">/api/graph</code>&apos;s real
              response (knowledge/ingest_registry.py) — laid out live with a real d3-force simulation, drag any
              node, scroll to zoom. The same graph <code className="font-data text-slate-300">roboweaver graph
              export-obsidian</code> writes as cross-linked Obsidian notes.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleAIEnrich}
              disabled={enriching}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg border border-violet-400/25 bg-violet-500/[0.08] text-violet-300 text-[13px] disabled:opacity-50 hover:bg-violet-500/[0.13]"
            >
              {enriching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              AI Enrich
            </button>
            <button
              onClick={handleDownloadObsidian}
              disabled={downloading}
              className="flex items-center gap-2 px-3.5 py-2 btn-neon text-[13px] disabled:opacity-50"
            >
              {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              Download Obsidian vault
            </button>
          </div>
        </div>

        {(enrichment?.suggestions || enrichmentError) && (
          <div className="app-card p-4 border-violet-400/20 space-y-3 animate-fade-in">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-violet-300" />
              <h3 className="text-[12.5px] font-semibold text-slate-200">Suggested SUITABLE_FOR edges</h3>
              {enrichment?.model && <span className="font-data text-[10px] text-slate-600">{enrichment.model}</span>}
            </div>
            {enrichmentError && <p className="text-[11.5px] text-amber-300">{enrichmentError}</p>}
            {enrichment?.suggestions && enrichment.suggestions.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {enrichment.suggestions.map((suggestion) => (
                  <div key={`${suggestion.robot_id}-${suggestion.skill_category}`} className="app-well rounded-lg p-3">
                    <div className="flex items-center gap-2 font-data text-[10.5px]">
                      <span className="text-cyan-300">{suggestion.robot_id}</span>
                      <span className="text-slate-600">→</span>
                      <span className="text-violet-300">{suggestion.skill_category}</span>
                      <span className="ml-auto text-slate-500">{Math.round(suggestion.confidence * 100)}%</span>
                    </div>
                    <p className="mt-1.5 text-[11px] text-slate-500 leading-relaxed">{suggestion.reasoning}</p>
                  </div>
                ))}
              </div>
            ) : enrichment && !enrichmentError ? (
              <p className="text-[11.5px] text-slate-500">The model found no new validated edges to suggest.</p>
            ) : null}
            <p className="font-data text-[9.5px] text-slate-600">Review-only · suggestions are not applied to the authoritative graph.</p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          {(['ROBOT', 'PACKAGE', 'SKILL'] as const).map((t) => (
            <span key={t} className="flex items-center gap-1.5 text-[11.5px] text-slate-400">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: NODE_COLOR[t] }} />
              {t.charAt(0) + t.slice(1).toLowerCase()}s
              <span className="font-data text-slate-500">({counts[t] ?? 0})</span>
            </span>
          ))}
          <span className="text-[11.5px] text-slate-600 font-data">{links.length} edges</span>
          <div className="flex-1" />
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Highlight a node…"
              className="app-well rounded-lg pl-8 pr-3 py-1.5 text-[12px] text-slate-200 placeholder-slate-500 focus:outline-none w-56"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
          <div className="app-card p-2 overflow-hidden">
            <svg
              ref={svgRef}
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              className="w-full h-[560px] touch-none cursor-grab active:cursor-grabbing"
              onPointerMove={onSvgPointerMove}
              onPointerUp={onSvgPointerUp}
              onPointerLeave={onSvgPointerUp}
              onPointerDown={onSvgPointerDown}
              onWheel={onWheel}
            >
              <rect width={WIDTH} height={HEIGHT} fill="transparent" />
              <g transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
                {links.map((l, i) => {
                  const s = resolve(l.source, nodesById);
                  const tgt = resolve(l.target, nodesById);
                  if (!s || !tgt || s.x === undefined || tgt.x === undefined) return null;
                  const onPath = pathEdgeSet.has(`${s.id}|${tgt.id}`);
                  return (
                    <line
                      key={i}
                      x1={s.x}
                      y1={s.y}
                      x2={tgt.x}
                      y2={tgt.y}
                      stroke={onPath ? '#22d3ee' : 'rgba(148,163,184,0.18)'}
                      strokeWidth={onPath ? 2 : 1}
                    />
                  );
                })}
                {nodes.map((n) => {
                  if (n.x === undefined || n.y === undefined) return null;
                  const dimmed = matchQuery.length > 0 && !n.name.toLowerCase().includes(matchQuery);
                  const isSelected = selected?.id === n.id;
                  const onPath = pathIds?.includes(n.id) ?? false;
                  const showLabel = transform.k > 1.6 || isSelected || onPath || hoveredId === n.id || (matchQuery.length > 0 && !dimmed);
                  return (
                    <g
                      key={n.id}
                      transform={`translate(${n.x},${n.y})`}
                      onPointerDown={(e) => onNodePointerDown(e, n)}
                      onPointerEnter={() => setHoveredId(n.id)}
                      onPointerLeave={() => setHoveredId((h) => (h === n.id ? null : h))}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelected(n);
                        setNodeSummary(null);
                      }}
                      style={{ cursor: 'pointer', opacity: dimmed ? 0.15 : 1 }}
                    >
                      <circle
                        r={NODE_RADIUS[n.type] ?? 6}
                        fill={NODE_COLOR[n.type] ?? DEFAULT_COLOR}
                        stroke={isSelected || onPath ? '#ffffff' : 'rgba(0,0,0,0.4)'}
                        strokeWidth={isSelected || onPath ? 2 : 1}
                      />
                      {showLabel && (
                        <text
                          x={0}
                          y={(NODE_RADIUS[n.type] ?? 6) + 11}
                          textAnchor="middle"
                          fontSize={9}
                          fill="#cbd5e1"
                          className="select-none pointer-events-none"
                        >
                          {n.name.length > 20 ? `${n.name.slice(0, 18)}…` : n.name}
                        </text>
                      )}
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>

          <div className="space-y-4">
            <div className="app-card p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Route className="w-4 h-4 text-slate-500" />
                <h3 className="text-[12.5px] font-semibold text-slate-200">Find a real path</h3>
              </div>
              <div className="space-y-1.5 text-[11.5px]">
                <div className="app-well rounded-lg px-2.5 py-2 flex items-center justify-between gap-2">
                  <span className="text-slate-500">From</span>
                  <span className="font-data text-slate-200 truncate">{pathFrom?.name ?? '— click a node —'}</span>
                </div>
                <div className="app-well rounded-lg px-2.5 py-2 flex items-center justify-between gap-2">
                  <span className="text-slate-500">To</span>
                  <span className="font-data text-slate-200 truncate">{pathTo?.name ?? '— click a node —'}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => selected && setPathFrom(selected)}
                  disabled={!selected}
                  className="flex-1 px-2 py-1.5 rounded-md bg-white/[0.04] hover:bg-white/[0.07] disabled:opacity-40 text-[11px] text-slate-300"
                >
                  Set from
                </button>
                <button
                  onClick={() => selected && setPathTo(selected)}
                  disabled={!selected}
                  className="flex-1 px-2 py-1.5 rounded-md bg-white/[0.04] hover:bg-white/[0.07] disabled:opacity-40 text-[11px] text-slate-300"
                >
                  Set to
                </button>
              </div>
              <button
                onClick={runFindPath}
                disabled={!pathFrom || !pathTo || pathLoading}
                className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md bg-cyan-500/15 hover:bg-cyan-500/20 disabled:opacity-40 text-[11.5px] font-medium text-cyan-300"
              >
                {pathLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Route className="w-3.5 h-3.5" />}
                Find path
              </button>
              {pathIds && (
                <p className="text-[11px] text-cyan-300/90 leading-relaxed font-data">{pathIds.join(' → ')}</p>
              )}
              {pathError && <p className="text-[11px] text-amber-300 leading-relaxed">{pathError}</p>}
              {(pathFrom || pathTo || pathIds) && (
                <button
                  onClick={() => {
                    setPathFrom(null);
                    setPathTo(null);
                    setPathIds(null);
                    setPathError(null);
                  }}
                  className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3 h-3" /> Clear
                </button>
              )}
            </div>

            <div className="app-card p-4 space-y-2.5">
              <div className="flex items-center gap-2">
                <Share2 className="w-4 h-4 text-slate-500" />
                <h3 className="text-[12.5px] font-semibold text-slate-200">
                  {selected ? selected.name : 'Node details'}
                </h3>
              </div>
              {!selected && <p className="text-[11.5px] text-slate-500">Click any node to inspect its real properties.</p>}
              {selected && (
                <div className="space-y-1.5 text-[11.5px]">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Type</span>
                    <span className="font-data" style={{ color: NODE_COLOR[selected.type] ?? DEFAULT_COLOR }}>
                      {selected.type}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">id</span>
                    <span className="font-data text-slate-300 truncate max-w-[160px]">{selected.id}</span>
                  </div>
                  {Object.entries(selected.properties).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between gap-2">
                      <span className="text-slate-500 shrink-0">{k}</span>
                      <span className="font-data text-slate-300 truncate text-right">{String(v)}</span>
                    </div>
                  ))}
                  <button
                    onClick={handleAINote}
                    disabled={enriching}
                    className="mt-2 w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md border border-violet-400/20 bg-violet-500/[0.06] text-violet-300 disabled:opacity-50"
                  >
                    {enriching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    Generate Obsidian summary
                  </button>
                  {nodeSummary && (
                    <p className="mt-2 p-2.5 rounded-md bg-violet-500/[0.05] border border-violet-400/10 text-slate-400 leading-relaxed">
                      {nodeSummary}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
