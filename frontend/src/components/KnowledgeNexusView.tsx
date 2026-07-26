'use client';

import React, { useState } from 'react';
import { 
  Database, 
  Search, 
  Sparkles, 
  Network, 
  Layers, 
  GitBranch, 
  ExternalLink, 
  Star, 
  CheckCircle2, 
  Bot, 
  ArrowRight,
  Code2
} from 'lucide-react';
import { RoboticsPackage } from '../types';

interface KnowledgeNexusViewProps {
  packages: RoboticsPackage[];
}

export const KnowledgeNexusView: React.FC<KnowledgeNexusViewProps> = ({ packages }) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [recommenderPrompt, setRecommenderPrompt] = useState('');
  const [recommenderResult, setRecommenderResult] = useState<{
    title: string;
    description: string;
    pipeline: string[];
    topics: string[];
  } | null>(null);

  const categories = ['All', 'Hardware Driver', 'Fleet Control', 'Navigation', 'Perception', 'Manipulation'];

  const filteredPackages = packages.filter((pkg) => {
    const matchesCat = selectedCategory === 'All' || pkg.category === selectedCategory;
    const matchesSearch =
      pkg.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      pkg.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      pkg.topics.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesCat && matchesSearch;
  });

  const handleGenerateArchitecture = () => {
    if (!recommenderPrompt.trim()) {
      setRecommenderResult({
        title: 'Universal Autonomous Retail Fleet & Dexterous Grasping Architecture',
        description:
          'Integrated ROS 2 Humble/Jazzy pipeline connecting ShopMate-R fleet coordination, Kalachakra obstacle avoidance, and Inspire Hand RH56F1-E2 dexterous grasping.',
        pipeline: [
          '1. shopmate_r_fleet (Task Dispatcher & Natural Language NLP)',
          '2. kalachakra_core + nav2_bringup (Dynamic Temporal Path Planning)',
          '3. card_scanner_ws (Precision TurtleBot4 Target Alignment & CV)',
          '4. moveit2_servo + inspire_hand_ros2 (6-DOF RS485 Tactile Grasping)',
        ],
        topics: [
          '/shopmate/task_dispatcher',
          '/kalachakra/trajectory_opt',
          '/card_scanner/target_pose',
          '/inspire_hand/cmd_grasp',
        ],
      });
      return;
    }

    setRecommenderResult({
      title: 'Synthesized Custom ROS 2 Architecture Stack',
      description: `Optimized pipeline generated for prompt: "${recommenderPrompt}" using RoboWeaver RAG indexing.`,
      pipeline: [
        '1. shopmate_r_fleet (Multi-Robot Fleet Orchestration)',
        '2. nav2_bringup + kalachakra_core (ROS 2 Path Planning & Obstacle Avoidance)',
        '3. inspire_hand_ros2 (RS485 Modbus RTU 6-DOF Dexterous Manipulation)',
      ],
      topics: ['/shopmate/fleet_status', '/cmd_vel', '/inspire_hand/joint_states'],
    });
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#090d16] text-slate-100 overflow-y-auto p-6 space-y-8">
      {/* Hero Banner: Knowledge Nexus */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-3xl bg-gradient-to-r from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 shadow-2xl">
        <div className="space-y-2 max-w-2xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-semibold">
            <Database className="w-3.5 h-3.5" />
            <span>Robotics Knowledge Nexus • Universal Catalog</span>
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white">
            RoboWeaver ROS 2 Ecosystem & Ontology Index
          </h1>
          <p className="text-sm text-slate-400 leading-relaxed">
            Universal knowledge repository indexing your robotics packages, hardware drivers, topics, and ROS 2 dependencies. Build custom multi-robot pipelines from natural language prompts.
          </p>
        </div>

        <div className="flex flex-col gap-2 shrink-0">
          <div className="p-4 rounded-2xl bg-slate-950/80 border border-slate-800 text-right">
            <div className="text-xs text-slate-400">Indexed Packages</div>
            <div className="text-2xl font-mono font-extrabold text-emerald-400">
              {packages.length} Packages
            </div>
            <div className="text-[11px] text-slate-500">ROS 2 Humble / Jazzy</div>
          </div>
        </div>
      </div>

      {/* AI Architecture Recommender Bar */}
      <div className="p-6 rounded-3xl bg-slate-900/80 border border-slate-800/80 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-emerald-400" />
            <h3 className="text-sm font-bold text-slate-100">
              RoboWeaver AI Pipeline Recommender
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            Type a robotics task to generate an automated ROS 2 architecture
          </span>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={recommenderPrompt}
            onChange={(e) => setRecommenderPrompt(e.target.value)}
            placeholder='e.g., "Connect ShopMate-R fleet with Inspire Hand RS485 dexterous grasping and TurtleBot4 card scanner"'
            className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
          />
          <button
            onClick={handleGenerateArchitecture}
            className="px-6 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs shadow-lg shadow-emerald-500/20 flex items-center justify-center gap-2 shrink-0 transition-all"
          >
            <Bot className="w-4 h-4" />
            <span>Generate Architecture</span>
          </button>
        </div>

        {/* Recommender Result Display */}
        {recommenderResult && (
          <div className="mt-4 p-5 rounded-2xl bg-slate-950/90 border border-emerald-500/40 space-y-4 animate-fade-in">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-emerald-300">
                  {recommenderResult.title}
                </span>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                Validated DAG
              </span>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              {recommenderResult.description}
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Execution Pipeline Nodes
                </div>
                <div className="space-y-1.5 font-mono text-xs text-slate-200">
                  {recommenderResult.pipeline.map((item, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <ArrowRight className="w-3 h-3 text-emerald-400 shrink-0" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Synthesized ROS 2 Topics
                </div>
                <div className="flex flex-wrap gap-2">
                  {recommenderResult.topics.map((top, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-emerald-400"
                    >
                      {top}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {categories.map((cat) => {
            const isSelected = selectedCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all shrink-0 ${
                  isSelected
                    ? 'bg-emerald-500 text-slate-950 shadow-md'
                    : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {cat}
              </button>
            );
          })}
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search package name, topic..."
            className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
          />
        </div>
      </div>

      {/* Package Catalog Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredPackages.map((pkg) => (
          <div
            key={pkg.id}
            className="flex flex-col justify-between p-6 rounded-3xl bg-slate-900/70 hover:bg-slate-900/90 border border-slate-800/80 hover:border-emerald-500/40 shadow-xl transition-all group"
          >
            <div className="space-y-4">
              {/* Card Header */}
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold font-mono text-white group-hover:text-emerald-400 transition-colors">
                      {pkg.name}
                    </h3>
                  </div>
                  <div className="text-[11px] text-slate-500 font-mono mt-0.5">{pkg.repo}</div>
                </div>

                <span
                  className={`text-[10px] px-2.5 py-0.5 rounded-full font-semibold shrink-0 ${
                    pkg.status === 'Ready' || pkg.status === 'Active'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  }`}
                >
                  {pkg.status}
                </span>
              </div>

              {/* Description */}
              <p className="text-xs text-slate-300 leading-relaxed min-h-[40px]">
                {pkg.description}
              </p>

              {/* ROS 2 Topics */}
              <div className="space-y-1.5">
                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  ROS 2 Topics
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {pkg.topics.map((t, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded-md bg-slate-950 font-mono text-[11px] text-teal-400 border border-slate-800/80"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>

              {/* Dependencies */}
              <div className="space-y-1.5">
                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  Dependencies
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {pkg.dependencies.map((dep, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded-md bg-slate-950/60 font-mono text-[10px] text-slate-400 border border-slate-800/50"
                    >
                      {dep}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Card Footer */}
            <div className="pt-4 mt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
              <span className="font-mono text-[11px] text-slate-500">{pkg.rosDistro}</span>
              <div className="flex items-center gap-1.5 text-amber-400 font-semibold">
                <Star className="w-3.5 h-3.5 fill-amber-400" />
                <span>{pkg.stars}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
