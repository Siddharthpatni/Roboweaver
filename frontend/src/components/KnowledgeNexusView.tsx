'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Search, Sparkles, ArrowRight, CheckCircle2, Loader2, AlertTriangle } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { NexusPackage, NexusRecommendation } from '../types';

export const KnowledgeNexusView: React.FC = () => {
  const [packages, setPackages] = useState<NexusPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [recommenderPrompt, setRecommenderPrompt] = useState('');
  const [recommenderResult, setRecommenderResult] = useState<NexusRecommendation | null>(null);
  const [recommending, setRecommending] = useState(false);

  useEffect(() => {
    RoboWeaverAPI.nexusPackages()
      .then((data) => {
        setPackages(data);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, []);

  const categories = useMemo(
    () => ['all', ...Array.from(new Set(packages.map((p) => p.category)))],
    [packages]
  );

  const filteredPackages = packages.filter((pkg) => {
    const matchesCat = selectedCategory === 'all' || pkg.category === selectedCategory;
    const q = searchQuery.toLowerCase();
    const matchesSearch =
      !q ||
      pkg.name.toLowerCase().includes(q) ||
      pkg.description.toLowerCase().includes(q) ||
      pkg.default_topics.some((t) => t.toLowerCase().includes(q));
    return matchesCat && matchesSearch;
  });

  const handleGenerateArchitecture = async () => {
    const prompt =
      recommenderPrompt.trim() ||
      'Build a visitor card scanner system with TurtleBot4 to scan security ID badges and navigate to reception desk';
    setRecommending(true);
    try {
      const rec = await RoboWeaverAPI.nexusRecommend(prompt);
      setRecommenderResult(rec);
    } catch {
      setError(true);
    } finally {
      setRecommending(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto p-8 space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <span className="kicker">Knowledge Nexus</span>
            <h1 className="text-[19px] font-semibold text-white mt-1">ROS 2 package catalog</h1>
            <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-xl">
              Live index of ROS 2 packages, hardware drivers, and navigation/manipulation stacks, served
              directly from the backend package catalog.
            </p>
          </div>
          <div className="app-card px-4 py-3 text-right shrink-0">
            <div className="text-[10.5px] text-slate-500">Indexed packages</div>
            <div className="text-xl font-semibold font-data text-emerald-400">{packages.length}</div>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2.5 px-4 py-3 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[13px]">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Could not reach the RoboWeaver backend. Start it with: roboweaver dashboard --port 8080</span>
          </div>
        )}

        {/* Architecture recommender */}
        <div className="app-card p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-emerald-400" />
            <h3 className="text-[13px] font-semibold text-slate-200">Architecture recommender</h3>
            <span className="text-[11px] text-slate-500">— keyword-matched, not ML-based</span>
          </div>

          <div className="flex flex-col sm:flex-row gap-2.5">
            <input
              type="text"
              value={recommenderPrompt}
              onChange={(e) => setRecommenderPrompt(e.target.value)}
              placeholder='e.g., "Connect ShopMate-R fleet with Inspire Hand RS485 grasping and TurtleBot4 card scanner"'
              className="flex-1 app-well rounded-lg px-3.5 py-2.5 text-[13px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/40 transition-colors"
            />
            <button
              onClick={handleGenerateArchitecture}
              disabled={recommending}
              className="shrink-0 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-[#0a0c11] text-[13px] font-semibold transition-colors"
            >
              {recommending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              Generate
            </button>
          </div>

          {recommenderResult && (
            <div className="app-well rounded-lg p-4 space-y-4 animate-fade-in">
              <div className="flex items-center gap-2 flex-wrap">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="text-[12.5px] text-slate-300">
                  Matched robots: <span className="font-medium text-slate-100">{recommenderResult.matched_robots.join(', ') || 'none'}</span>
                </span>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {recommenderResult.recommended_packages.map((p) => (
                  <span key={p} className="px-2 py-0.5 rounded-md bg-violet-500/10 border border-violet-500/20 font-data text-[11px] text-violet-300">
                    {p}
                  </span>
                ))}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                <div>
                  <div className="text-[11px] font-medium text-slate-500 mb-2">Active ROS 2 topics</div>
                  <div className="space-y-1.5 font-data text-[12px] text-slate-300">
                    {recommenderResult.ros2_topics.map((item, idx) => (
                      <div key={idx} className="flex items-center gap-1.5">
                        <ArrowRight className="w-3 h-3 text-emerald-500 shrink-0" />
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="text-[11px] font-medium text-slate-500 mb-2">package.xml dependencies</div>
                  <div className="flex flex-wrap gap-1.5">
                    {recommenderResult.package_xml_dependencies.map((dep, idx) => (
                      <span key={idx} className="px-2 py-0.5 rounded bg-black/20 border border-white/[0.06] font-data text-[11px] text-slate-300">
                        {dep}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
            {categories.map((cat) => {
              const isSelected = selectedCategory === cat;
              return (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-3 py-1.5 rounded-md text-[12px] font-medium capitalize transition-colors shrink-0 ${
                    isSelected
                      ? 'bg-emerald-500/15 text-emerald-300'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                  }`}
                >
                  {cat}
                </button>
              );
            })}
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search packages, topics…"
              className="w-full app-well rounded-lg pl-8 pr-3 py-2 text-[12.5px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/40 transition-colors"
            />
          </div>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-slate-500 text-[13px]">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading catalog…
          </div>
        )}

        {/* Package grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredPackages.map((pkg) => (
            <div key={pkg.id} className="app-card p-5 flex flex-col justify-between hover:border-white/[0.14] transition-colors">
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="text-[13.5px] font-semibold text-slate-100 truncate">{pkg.name}</h3>
                    <div className="text-[11px] font-data text-slate-500 mt-0.5 truncate">{pkg.id}</div>
                  </div>
                  <span className="shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 capitalize">
                    {pkg.category}
                  </span>
                </div>

                <p className="text-[12px] text-slate-400 leading-relaxed min-h-[36px]">{pkg.description}</p>

                <div className="space-y-1.5">
                  <div className="text-[10.5px] font-medium text-slate-600">ROS 2 topics</div>
                  <div className="flex flex-wrap gap-1">
                    {pkg.default_topics.map((t, idx) => (
                      <span key={idx} className="px-1.5 py-0.5 rounded bg-black/20 font-data text-[10.5px] text-teal-400">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <div className="text-[10.5px] font-medium text-slate-600">Compatible robots</div>
                  <div className="flex flex-wrap gap-1">
                    {pkg.compatible_robots.map((r, idx) => (
                      <span key={idx} className="px-1.5 py-0.5 rounded bg-black/20 font-data text-[10.5px] text-amber-400">
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="pt-3 mt-3 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-slate-500 font-data">
                <span>v{pkg.version}</span>
                <span>{pkg.ros2_dependencies.length} deps</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
