import React from 'react';
import { Cpu, BookOpen, Users, Building2 } from 'lucide-react';

export const CentralHub: React.FC = () => {
  const modules = [
    {
      id: 'project-intelligence',
      icon: Cpu,
      title: '项目智能中心',
      subtitle: 'Project Intelligence Center',
      desc: '上传项目文档，自动生成多专业分析报告',
      color: 'from-amber-400 to-amber-600',
    },
    {
      id: 'ai-design-overview',
      icon: Building2,
      title: 'AI设计代理',
      subtitle: 'Design Agents',
      desc: '项目研判、任务编排、AI 生图与 PPT 大纲',
      color: 'from-blue-400 to-blue-600',
    },
    {
      id: 'knowledge',
      icon: BookOpen,
      title: '建筑知识库',
      subtitle: 'Architecture Brain',
      desc: '案例、经验、方法论检索',
      color: 'from-emerald-400 to-emerald-600',
    },
    {
      id: 'network',
      icon: Users,
      title: '设计师网络',
      subtitle: 'Designer Network',
      desc: '匹配最适合的专家人才',
      color: 'from-purple-400 to-purple-600',
    },
  ];

  return (
    <section className="relative py-20 md:py-32 px-6 md:px-12 bg-[#0A0A0A]">
      <div className="max-w-[1440px] mx-auto">
        {/* Section Header */}
        <div className="text-center mb-16">
          <span className="reveal text-xs font-medium text-zinc-500 uppercase tracking-[0.3em] mb-4 block">
            Platform Modules
          </span>
          <h2 className="reveal text-3xl md:text-5xl font-bold text-white tracking-tight mb-4">
            RMO-Ai 核心平台架构
          </h2>
          <p className="reveal text-zinc-400 max-w-2xl mx-auto">
            四大模块协同工作，覆盖从项目分析到设计落地的全链路
          </p>
        </div>

        {/* Central Hub Layout */}
        <div className="relative">
          {/* Center Glow */}
          <div className="hidden lg:block absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48">
            <div className="absolute inset-0 rounded-full bg-amber-500/20 blur-3xl animate-pulse-glow" />
            <div className="absolute inset-8 rounded-full bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center shadow-lg shadow-amber-500/30">
              <span className="text-black font-bold text-lg">RMO</span>
            </div>
          </div>

          {/* Module Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 lg:gap-8 lg:px-32">
            {modules.map((mod, i) => (
              <div
                key={mod.id}
                id={mod.id}
                className="reveal group relative bg-[#1C1C1C] border border-[#333333]/40 rounded-2xl p-6 md:p-8 hover:border-zinc-600 transition-all duration-300 cursor-pointer"
                style={{ transitionDelay: `${i * 100}ms` }}
              >
                {/* Icon */}
                <div
                  className={`w-12 h-12 rounded-xl bg-gradient-to-br ${mod.color} flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300`}
                >
                  <mod.icon size={24} className="text-white" />
                </div>

                {/* Content */}
                <h3 className="text-xl font-semibold text-white mb-1">
                  {mod.title}
                </h3>
                <span className="text-xs text-zinc-500 uppercase tracking-wider mb-3 block">
                  {mod.subtitle}
                </span>
                <p className="text-sm text-zinc-400 leading-relaxed">
                  {mod.desc}
                </p>

                {/* Connection Line (decorative) */}
                <div className="hidden lg:block absolute top-1/2 -translate-y-1/2 w-8 h-px bg-gradient-to-r from-[#333333] to-transparent"
                  style={{
                    left: i % 2 === 0 ? '100%' : 'auto',
                    right: i % 2 === 1 ? '100%' : 'auto',
                    background: i % 2 === 0
                      ? 'linear-gradient(to right, #333333, transparent)'
                      : 'linear-gradient(to left, #333333, transparent)',
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};
