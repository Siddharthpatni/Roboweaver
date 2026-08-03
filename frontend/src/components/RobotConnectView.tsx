'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Radar,
  RefreshCw,
  Plug,
  PlugZap,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  SearchX,
  Signal,
  Server,
  Cable,
  Usb,
  CircuitBoard,
  Network,
  Sparkles,
  DollarSign,
} from 'lucide-react';
import { RoboWeaverAPI, TimeoutError } from '../lib/api';
import {
  DiscoveredRobot,
  DiscoveryResult,
  ConnectionResult,
  ConnectionAdvice,
  NetworkInfo,
  RobotProfile,
} from '../types';

/**
 * Maps a discovery heuristic (`robot_type_guess`) onto a real entry in
 * ROBOT_REGISTRY. The connect endpoint needs a registry id to load a RobotSpec,
 * and a wrong guess would compile motion against the wrong kinematics — so every
 * card exposes this as an editable select rather than silently committing to it.
 */
const GUESS_TO_REGISTRY_ID: Record<string, string> = {
  'Universal Robots (UR)': 'ur5e',
  'KUKA Industrial': 'kuka_iiwa',
  'ABB Industrial': 'abb_irb120',
  'Franka Emika Panda': 'franka_panda',
};

function defaultRegistryId(robot: DiscoveredRobot): string {
  return GUESS_TO_REGISTRY_ID[robot.robot_type_guess] ?? 'franka_panda';
}

/**
 * The backend's ROS 2 bridge performs a real rclpy/DDS attempt; every other
 * protocol it supports resolves to a genuine TCP reachability probe. Anything
 * that isn't ROS 2 is therefore sent as "sim" — that is the bridge that
 * actually probes the socket, instead of ROS2HardwareBridge reporting rclpy
 * missing for what is really a raw TCP controller port.
 */
function bridgeProtocolFor(robot: DiscoveredRobot): 'ros2' | 'sim' {
  return robot.protocol === 'ros2' ? 'ros2' : 'sim';
}

function bridgeUriFor(robot: DiscoveredRobot): string {
  const scheme = bridgeProtocolFor(robot);
  return `${scheme}://${robot.host}:${robot.port}`;
}

/** Presentation metadata for each local (non-IP) transport kind. */
const TRANSPORT_KIND_LABEL: Record<string, string> = {
  serial: 'Serial / RS-485',
  can: 'CAN bus',
  unix_socket: 'Unix socket',
};

const TRANSPORT_KIND_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  serial: Usb,
  can: CircuitBoard,
  unix_socket: Cable,
};

/**
 * Link quality bars derived strictly from the measured TCP connect latency —
 * this is not an RF signal reading, and the UI labels it as such.
 */
function latencyBars(latencyMs: number): number {
  if (latencyMs <= 1) return 4;
  if (latencyMs <= 5) return 3;
  if (latencyMs <= 25) return 2;
  return 1;
}

function SignalBars({ latencyMs }: { latencyMs: number }) {
  const bars = latencyBars(latencyMs);
  return (
    <span className="flex items-end gap-[2px]" title={`${latencyMs} ms TCP connect latency`}>
      {[1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className={`w-[3px] rounded-sm transition-colors ${
            i <= bars ? 'bg-cyan-400' : 'bg-slate-700'
          }`}
          style={{ height: `${4 + i * 2.5}px` }}
        />
      ))}
    </span>
  );
}

/** Animated radar sweep shown while a scan is in flight. */
function RadarSweep({ scanning }: { scanning: boolean }) {
  return (
    <div className="relative w-28 h-28 shrink-0">
      {[38, 26, 14].map((r) => (
        <span
          key={r}
          className="absolute rounded-full border border-cyan-400/15"
          style={{
            inset: `${50 - r}%`,
          }}
        />
      ))}
      <span className="absolute left-1/2 top-0 bottom-0 w-px bg-cyan-400/10 -translate-x-1/2" />
      <span className="absolute top-1/2 left-0 right-0 h-px bg-cyan-400/10 -translate-y-1/2" />

      {scanning && (
        <div className="absolute inset-0 animate-radar-sweep">
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background:
                'conic-gradient(from 0deg, rgba(34,211,238,0.35) 0deg, rgba(34,211,238,0.06) 40deg, transparent 90deg)',
            }}
          />
        </div>
      )}

      <span
        className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-cyan-400 ${
          scanning ? 'animate-breathing' : ''
        }`}
        style={{ boxShadow: '0 0 10px 3px rgba(34,211,238,0.35)' }}
      />
    </div>
  );
}

export const RobotConnectView: React.FC = () => {
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Per-endpoint UI state, keyed by `host:port`.
  const [registryIds, setRegistryIds] = useState<Record<string, string>>({});
  const [connecting, setConnecting] = useState<Record<string, boolean>>({});
  const [connections, setConnections] = useState<Record<string, ConnectionResult>>({});
  const [robots, setRobots] = useState<RobotProfile[]>([]);

  // LAN sweep + LLM advisor state
  const [network, setNetwork] = useState<NetworkInfo | null>(null);
  const [subnet, setSubnet] = useState('');
  const [provider, setProvider] = useState('ollama');
  const [advising, setAdvising] = useState<Record<string, boolean>>({});
  const [advice, setAdvice] = useState<Record<string, ConnectionAdvice>>({});

  const scan = useCallback(async (range?: string) => {
    setScanning(true);
    setError(null);
    try {
      const data = range
        ? await RoboWeaverAPI.discoverSubnet(range)
        : await RoboWeaverAPI.discover();
      setResult(data);
    } catch (e) {
      setResult(null);
      if (e instanceof TimeoutError) {
        setError(`${e.message} A very large range or a slow host can cause this — try a smaller /24.`);
      } else if (e instanceof Error && e.message.includes('400')) {
        setError(
          `The backend refused that range. Ranges are capped at ${
            network?.max_scan_hosts ?? 1024
          } hosts — a /24 is the usual robot subnet.`
        );
      } else {
        setError('Could not reach the RoboWeaver backend to run a scan. Start it with: roboweaver dashboard --port 8080');
      }
    } finally {
      setScanning(false);
    }
  }, [network]);

  useEffect(() => {
    // `scan()` sets state (setScanning(true)) before its first await, so
    // calling it directly here would run that setState synchronously inside
    // the effect body -- every other view in this app avoids that by only
    // setting state inside a .then(). Deferring past a microtask keeps the
    // "scan on mount" behavior (imperceptible delay) while keeping the state
    // update genuinely asynchronous relative to the effect.
    void Promise.resolve().then(() => scan());
    RoboWeaverAPI.robots()
      .then(setRobots)
      .catch(() => {});
    RoboWeaverAPI.network()
      .then((info) => {
        setNetwork(info);
        if (info.ranges.length > 0) setSubnet(info.ranges[0].cidr);
      })
      .catch(() => {});
    // Intentionally runs once: `scan` closes over `network` only for its error
    // message, and re-running discovery whenever that resolves would double-scan.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAdvise = async (robot: DiscoveredRobot) => {
    const key = `${robot.host}:${robot.port}`;
    setAdvising((a) => ({ ...a, [key]: true }));
    try {
      const res = await RoboWeaverAPI.adviseConnection(robot, provider);
      setAdvice((a) => ({ ...a, [key]: res }));
      // Only pre-select the robot when the backend actually validated the id.
      if (res.robot_id) {
        setRegistryIds((r) => ({ ...r, [key]: res.robot_id as string }));
      }
    } catch (e) {
      const message =
        e instanceof TimeoutError
          ? `${e.message} Cloud providers and a cold-loading local model can both take a while — try again.`
          : 'Backend unreachable while requesting advice.';
      setAdvice((a) => ({
        ...a,
        [key]: {
          robot_id: null, protocol: null, uri: null, reasoning: '', confidence: 0,
          provider, model: '', error: message,
        },
      }));
    } finally {
      setAdvising((a) => ({ ...a, [key]: false }));
    }
  };

  const providerOptions = network
    ? [
        { id: 'ollama', label: 'Ollama (local)', ready: network.advisor.ollama_available, free: true },
        { id: 'openrouter', label: 'OpenRouter', ready: network.advisor.openrouter_configured, free: true },
        { id: 'anthropic', label: 'Anthropic', ready: network.advisor.anthropic_configured, free: false },
        { id: 'openai', label: 'OpenAI', ready: network.advisor.openai_configured, free: false },
      ]
    : [];

  const handleConnect = async (robot: DiscoveredRobot) => {
    const key = `${robot.host}:${robot.port}`;
    const registryId = registryIds[key] ?? defaultRegistryId(robot);

    setConnecting((c) => ({ ...c, [key]: true }));
    try {
      const status = await RoboWeaverAPI.connectRobot(
        registryId,
        bridgeProtocolFor(robot),
        bridgeUriFor(robot)
      );
      setConnections((c) => ({ ...c, [key]: status }));
    } catch {
      setConnections((c) => ({
        ...c,
        [key]: { is_connected: false, error: 'Backend unreachable while opening the bridge.' },
      }));
    } finally {
      setConnecting((c) => ({ ...c, [key]: false }));
    }
  };

  const found = result?.discovered ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto p-8 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-5 flex-wrap">
          <div>
            <span className="kicker">Robot Connect</span>
            <h1 className="text-[19px] font-semibold text-white mt-1">Auto-discover nearby robots</h1>
            <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-2xl">
              Probes the standard robot and simulator control ports — ROS 2 DDS, Isaac Sim, Gazebo,
              Webots, UR, KUKA, Fanuc, ABB and Franka — with a real TCP connect. Only sockets that
              actually answered are listed, so an empty result genuinely means nothing is listening.
            </p>
          </div>
          <button
            onClick={() => scan()}
            disabled={scanning}
            className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg btn-neon disabled:opacity-50 text-[13px]"
          >
            {scanning ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            {scanning ? 'Scanning…' : 'Scan this machine'}
          </button>
        </div>

        {/* LAN range sweep */}
        <div className="app-card p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Network className="w-4 h-4 text-cyan-400" />
            <h3 className="text-[13.5px] font-semibold text-slate-200">Scan the local network</h3>
          </div>

          {network && network.ranges.length > 0 ? (
            <p className="text-[12px] text-slate-400 leading-relaxed">
              Detected{' '}
              <span className="font-data text-cyan-300">{network.ranges[0].cidr}</span> on{' '}
              <span className="font-data text-slate-300">{network.ranges[0].interface_name}</span> (
              {network.ranges[0].host_count} hosts).{' '}
              {network.ranges[0].netmask_source === 'interface' ? (
                <>Prefix read from the interface.</>
              ) : (
                <span className="text-amber-300/90">
                  Netmask could not be read — a /24 was assumed, so this may cover the wrong
                  addresses.
                </span>
              )}
            </p>
          ) : (
            <p className="text-[12px] text-slate-400">
              No LAN range detected — the host has no default route, so only this machine can be
              scanned.
            </p>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            <input
              value={subnet}
              onChange={(e) => setSubnet(e.target.value)}
              placeholder="192.168.1.0/24"
              className="app-well rounded-lg px-3 py-2 text-[12.5px] font-data text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-400/40 flex-1 min-w-[180px]"
            />
            <button
              onClick={() => scan(subnet)}
              disabled={scanning || !subnet.trim()}
              className="flex items-center gap-2 px-4 py-2 btn-neon disabled:opacity-50 text-[12.5px]"
            >
              {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Radar className="w-4 h-4" />}
              Sweep range
            </button>
          </div>
          <p className="text-[11px] text-slate-500">
            Sweeps every host in the range for the {result?.ports_scanned ?? 14} robot control ports.
            Capped at {network?.max_scan_hosts ?? 1024} hosts. Only scan networks you are authorised
            to scan.
          </p>
        </div>

        {/* Radar + scan stats */}
        <div className="app-card hud-corners p-6 flex items-center gap-6 flex-wrap">
          <RadarSweep scanning={scanning} />
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex items-center gap-2">
              <Radar className="w-4 h-4 text-cyan-400" />
              <span className="text-[13.5px] font-semibold text-slate-200">
                {scanning
                  ? 'Sweeping local control ports…'
                  : found.length > 0
                  ? `${found.length} endpoint${found.length === 1 ? '' : 's'} responding`
                  : 'Scan complete'}
              </span>
            </div>
            {result && !scanning && (
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11.5px] font-data text-slate-500">
                <span>
                  duration: <span className="text-slate-300">{result.scan_duration_ms} ms</span>
                </span>
                <span>
                  hosts: <span className="text-slate-300">{result.hosts_scanned}</span>
                </span>
                <span>
                  range:{' '}
                  <span className="text-slate-300">
                    {result.scanned_range || 'this machine only'}
                  </span>
                </span>
                <span>
                  ports/host: <span className="text-slate-300">{result.ports_scanned}</span>
                </span>
              </div>
            )}
            <p className="text-[11.5px] text-slate-500 leading-relaxed">
              Scans <span className="font-data text-slate-400">127.0.0.1</span> and{' '}
              <span className="font-data text-slate-400">localhost</span>. Reachability is verified at
              the TCP layer — the vendor application handshake is not implemented, so a responding
              socket proves something is listening on that port, not that it is the robot named here.
            </p>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2.5 px-4 py-3 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[12.5px] animate-fade-in">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Empty state */}
        {!scanning && !error && found.length === 0 && (
          <div className="app-card p-8 text-center space-y-3 animate-fade-in">
            <SearchX className="w-8 h-8 text-slate-600 mx-auto" />
            <h3 className="text-[14px] font-semibold text-slate-200">No robots responding</h3>
            <p className="text-[12.5px] text-slate-400 leading-relaxed max-w-lg mx-auto">
              Nothing is listening on the scanned control ports. That is the honest result — not a
              scan failure. To get a live endpoint, start one of these and scan again:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl mx-auto pt-1 text-left">
              {[
                ['ROS 2 bridge', 'ros2 launch rosbridge_server rosbridge_websocket_launch.xml'],
                ['Gazebo', 'gz sim -v 4'],
                ['Webots', 'webots --stream'],
                ['UR simulator', 'URSim on port 30002'],
              ].map(([label, cmd]) => (
                <div key={label} className="app-well rounded-lg px-3 py-2">
                  <div className="text-[11.5px] font-medium text-slate-300">{label}</div>
                  <code className="text-[10.5px] font-data text-slate-500 break-all">{cmd}</code>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Discovered robots */}
        {found.length > 0 && (
          <div className="space-y-3 stagger-children">
            {found.map((robot) => {
              const key = `${robot.host}:${robot.port}`;
              const conn = connections[key];
              const isConnecting = connecting[key];
              const registryId = registryIds[key] ?? defaultRegistryId(robot);

              return (
                <div key={key} className="app-card p-5 space-y-4">
                  {/* Row 1: identity */}
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shrink-0">
                        <Server className="w-4 h-4 text-cyan-400" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="text-[13.5px] font-semibold text-slate-100">{robot.name}</h3>
                          <span className="px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300 font-data text-[10px]">
                            {robot.protocol}
                          </span>
                        </div>
                        <p className="text-[11.5px] text-slate-500 mt-0.5">{robot.description}</p>
                        {robot.caveat && (
                          <p className="text-[11px] text-amber-300/90 mt-1 flex items-start gap-1.5">
                            <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                            <span>{robot.caveat}</span>
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-4 shrink-0">
                      <div className="text-right">
                        <div className="text-[10.5px] text-slate-500">latency</div>
                        <div className="font-data text-[12.5px] text-cyan-300">{robot.latency_ms} ms</div>
                      </div>
                      <div className="text-right">
                        <div className="text-[10.5px] text-slate-500 flex items-center gap-1 justify-end">
                          <Signal className="w-3 h-3" />
                          link
                        </div>
                        <SignalBars latencyMs={robot.latency_ms} />
                      </div>
                    </div>
                  </div>

                  {/* Row 2: endpoint facts */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    <div className="app-well rounded-lg px-3 py-2">
                      <div className="text-[10.5px] text-slate-500">endpoint</div>
                      <div className="font-data text-[12px] text-slate-200 truncate">{key}</div>
                    </div>
                    <div className="app-well rounded-lg px-3 py-2">
                      <div className="text-[10.5px] text-slate-500 flex items-center justify-between gap-1">
                        <span>type guess</span>
                        <span
                          className={`font-data ${
                            robot.confidence >= 0.5 ? 'text-cyan-400/80' : 'text-amber-400/90'
                          }`}
                        >
                          {Math.round(robot.confidence * 100)}%
                        </span>
                      </div>
                      <div className="text-[12px] text-slate-200 truncate">{robot.robot_type_guess}</div>
                    </div>
                    <div className="app-well rounded-lg px-3 py-2">
                      <div className="text-[10.5px] text-slate-500">bridge</div>
                      <div className="font-data text-[12px] text-slate-200 truncate">
                        {bridgeProtocolFor(robot)}
                      </div>
                    </div>
                  </div>

                  {/* Row 2b: LLM-assisted identification */}
                  <div className="flex items-center justify-between gap-2 flex-wrap pt-1 border-t border-cyan-400/[0.07]">
                    <div className="flex items-center gap-2 pt-2 flex-wrap">
                      <Sparkles className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                      <span className="text-[11.5px] text-slate-500">Identify with</span>
                      <select
                        value={provider}
                        onChange={(e) => setProvider(e.target.value)}
                        className="app-well rounded-lg px-2 py-1 text-[11.5px] text-slate-200 focus:outline-none"
                      >
                        {providerOptions.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.label}
                            {p.free ? '' : ' ($)'}
                            {p.ready ? '' : ' — not configured'}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => handleAdvise(robot)}
                        disabled={advising[key]}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/25 text-violet-300 text-[11.5px] disabled:opacity-50 transition-colors"
                      >
                        {advising[key] ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5" />
                        )}
                        {advising[key] ? 'Asking…' : 'Ask model'}
                      </button>
                      {providerOptions.find((p) => p.id === provider && !p.free) && (
                        <span className="flex items-center gap-1 text-[10.5px] text-amber-300/90">
                          <DollarSign className="w-3 h-3" />
                          billed per call
                        </span>
                      )}
                    </div>
                  </div>

                  {advice[key] && (
                    <div
                      className={`rounded-lg border p-3 space-y-1.5 animate-fade-in ${
                        advice[key].robot_id
                          ? 'bg-violet-500/[0.06] border-violet-500/25'
                          : 'bg-amber-500/[0.06] border-amber-500/25'
                      }`}
                    >
                      {advice[key].robot_id ? (
                        <>
                          <div className="flex items-center gap-2 flex-wrap">
                            <Sparkles className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                            <span className="text-[12px] text-slate-200">
                              Suggests{' '}
                              <span className="font-data text-violet-300">
                                {advice[key].robot_id}
                              </span>{' '}
                              over{' '}
                              <span className="font-data text-violet-300">
                                {advice[key].protocol}
                              </span>
                            </span>
                            <span className="text-[10.5px] font-data text-slate-500">
                              {Math.round(advice[key].confidence * 100)}% · {advice[key].provider}
                            </span>
                          </div>
                          {advice[key].reasoning && (
                            <p className="text-[11.5px] text-slate-400 leading-relaxed pl-5.5">
                              {advice[key].reasoning}
                            </p>
                          )}
                          <p className="text-[10.5px] text-slate-500 pl-5.5">
                            A suggestion, not a verification — the robot selector below has been
                            pre-filled; confirm before connecting.
                          </p>
                        </>
                      ) : (
                        <p className="text-[11.5px] text-amber-300/90 flex items-start gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                          <span>{advice[key].error}</span>
                        </p>
                      )}
                    </div>
                  )}

                  {/* Row 3: kinematics target + connect */}
                  <div className="flex items-center justify-between gap-3 flex-wrap pt-1">
                    <label className="flex items-center gap-2 text-[11.5px] text-slate-500">
                      Compile against
                      <select
                        value={registryId}
                        onChange={(e) =>
                          setRegistryIds((r) => ({ ...r, [key]: e.target.value }))
                        }
                        className="app-well rounded-lg px-2.5 py-1.5 text-[12px] text-slate-200 focus:outline-none"
                      >
                        {robots.length === 0 && <option value={registryId}>{registryId}</option>}
                        {robots.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name} ({r.dof}-DOF)
                          </option>
                        ))}
                      </select>
                    </label>

                    <button
                      onClick={() => handleConnect(robot)}
                      disabled={isConnecting}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-[12.5px] font-semibold transition-all disabled:opacity-50 ${
                        conn?.is_connected
                          ? 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-300'
                          : 'btn-neon'
                      }`}
                    >
                      {isConnecting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : conn?.is_connected ? (
                        <PlugZap className="w-4 h-4" />
                      ) : (
                        <Plug className="w-4 h-4" />
                      )}
                      {isConnecting ? 'Connecting…' : conn?.is_connected ? 'Connected' : 'Connect'}
                    </button>
                  </div>

                  {/* Row 4: connection outcome */}
                  {conn && (
                    <div
                      className={`rounded-lg border p-3.5 space-y-2 animate-fade-in ${
                        conn.is_connected
                          ? 'bg-cyan-500/[0.06] border-cyan-500/25'
                          : 'bg-rose-500/[0.06] border-rose-500/25'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {conn.is_connected ? (
                          <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                        )}
                        <span
                          className={`text-[12.5px] font-medium ${
                            conn.is_connected ? 'text-cyan-300' : 'text-rose-300'
                          }`}
                        >
                          {conn.is_connected ? 'Bridge live' : 'Bridge not established'}
                        </span>
                        {conn.protocol && (
                          <span className="font-data text-[11px] text-slate-500 truncate">
                            {conn.protocol}
                          </span>
                        )}
                      </div>

                      {(conn.message || conn.error) && (
                        <p className="text-[11.5px] text-slate-400 leading-relaxed pl-6">
                          {conn.message ?? conn.error}
                        </p>
                      )}

                      {conn.is_connected && (
                        <div className="pl-6 flex flex-wrap gap-x-5 gap-y-1 text-[11px] font-data text-slate-500">
                          {conn.robot_id && (
                            <span>
                              robot: <span className="text-slate-300">{conn.robot_id}</span>
                            </span>
                          )}
                          {conn.dof !== undefined && (
                            <span>
                              dof: <span className="text-slate-300">{conn.dof}</span>
                            </span>
                          )}
                          {conn.latency_ms !== undefined && (
                            <span>
                              latency: <span className="text-slate-300">{conn.latency_ms} ms</span>
                            </span>
                          )}
                          {conn.active_controllers && conn.active_controllers.length > 0 && (
                            <span>
                              controllers:{' '}
                              <span className="text-slate-300">
                                {conn.active_controllers.join(', ')}
                              </span>
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Local (non-IP) transports */}
        {result && (
          <div className="app-card p-6 space-y-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <Cable className="w-4 h-4 text-violet-400" />
                <h3 className="text-[13.5px] font-semibold text-slate-200">Local transports</h3>
              </div>
              <span className="text-[11px] font-data text-slate-500">
                {result.platform_name} · {result.supported_transports.join(', ') || 'none supported'}
              </span>
            </div>

            <p className="text-[12px] text-slate-400 leading-relaxed">
              Not every robot is reachable over TCP. Serial/RS-485 arms and hands, CAN-bus joints and
              socket-based middleware are found here instead — these are the paths that exist when the
              machine has no network route to the robot at all.
            </p>

            {!result.supported_transports.includes('can') && (
              <p className="text-[11.5px] text-amber-300/90 flex items-start gap-1.5">
                <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                <span>
                  SocketCAN enumeration needs <span className="font-data">/sys/class/net</span>, which
                  only exists on Linux. On {result.platform_name}, CAN interfaces cannot be detected —
                  this is not the same as &ldquo;no CAN hardware present&rdquo;.
                </span>
              </p>
            )}

            {result.local_transports.length > 0 ? (
              <div className="space-y-2">
                {result.local_transports.map((t) => {
                  const Icon = TRANSPORT_KIND_ICON[t.kind] ?? Cable;
                  return (
                    <div key={`${t.kind}:${t.device}`} className="app-well rounded-lg px-3.5 py-2.5">
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <Icon className="w-4 h-4 text-violet-400 shrink-0" />
                          <div className="min-w-0">
                            <div className="font-data text-[12.5px] text-slate-200 truncate">
                              {t.device}
                            </div>
                            <div className="text-[11px] text-slate-500 truncate">{t.description}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300 font-data">
                            {TRANSPORT_KIND_LABEL[t.kind] ?? t.kind}
                          </span>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded font-data ${
                              t.readable
                                ? 'bg-cyan-500/10 text-cyan-300'
                                : 'bg-amber-500/10 text-amber-300'
                            }`}
                          >
                            {t.readable ? 'accessible' : 'permission denied'}
                          </span>
                        </div>
                      </div>
                      {t.detail && (
                        <p className="text-[11px] text-amber-300/90 mt-1.5 pl-6.5 leading-relaxed">
                          {t.detail}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-[12.5px] text-slate-500">
                No serial, CAN or middleware sockets present. Plug in a USB/RS-485 adapter (it appears
                as <span className="font-data text-slate-400">/dev/ttyUSB0</span> on Linux or{' '}
                <span className="font-data text-slate-400">/dev/cu.usbserial*</span> on macOS) and scan
                again.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
