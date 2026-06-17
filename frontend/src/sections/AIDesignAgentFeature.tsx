import React from 'react';
import { Bot, FileText, ListChecks, Presentation, Sparkles } from 'lucide-react';

const cards = [
  { title: '任务拆解', description: '把项目目标转成任务、负责人和交付要求。', icon: ListChecks },
  { title: '技术重点', description: '提取日照、退界、面积、消防等复用重点。', icon: FileText },
  { title: '汇报结构', description: '生成业主汇报或内部评审的 PPT 框架。', icon: Presentation },
];

export function AIDesignAgentFeature() {
  return (
    <section className="bg-[#0A0A0A] px-6 py-24 md:px-12">
      <div className="mx-auto max-w-6xl">
        <div className="mb-10 max-w-2xl">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-amber-400/30 px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-amber-300">
            <Bot size={14} />
            AI Agent
          </div>
          <h2 className="mb-4 text-3xl font-bold text-white md:text-5xl">AI 设计代理</h2>
          <p className="text-sm leading-7 text-zinc-400">
            桌面版保留稳定的项目工作台入口，AI 代理能力通过项目上下文、知识库检索和技能卡片协同运行。
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <div key={card.title} className="rounded-lg border border-[#333333] bg-[#111111] p-5">
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-amber-400 text-black">
                  <Icon size={20} />
                </div>
                <h3 className="mb-2 text-lg font-semibold text-white">{card.title}</h3>
                <p className="text-sm leading-6 text-zinc-400">{card.description}</p>
              </div>
            );
          })}
        </div>

        <div className="mt-6 inline-flex items-center gap-2 text-sm text-zinc-400">
          <Sparkles size={16} className="text-amber-300" />
          真实执行入口请使用桌面应用的“AI代理”和项目详情页“执行台”。
        </div>
      </div>
    </section>
  );
}
