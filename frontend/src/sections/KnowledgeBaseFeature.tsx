import React from 'react';
import { BookOpen, Database, FileSearch, ShieldCheck } from 'lucide-react';

const features = [
  { title: '本地索引', description: '扫描用户选择的资料目录，索引 Markdown、PDF、Office 文件和项目资料。', icon: Database },
  { title: '来源引用', description: '问答结果保留引用片段，便于回到原始资料核对。', icon: FileSearch },
  { title: '数据留本地', description: '数据库、上传文件和日志写入用户 AppData，不写入安装目录。', icon: ShieldCheck },
];

export function KnowledgeBaseFeature() {
  return (
    <section className="bg-[#0A0A0A] px-6 py-24 md:px-12">
      <div className="mx-auto max-w-6xl">
        <div className="mb-10 max-w-2xl">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-emerald-400/30 px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-emerald-300">
            <BookOpen size={14} />
            Knowledge Base
          </div>
          <h2 className="mb-4 text-3xl font-bold text-white md:text-5xl">设计知识库</h2>
          <p className="text-sm leading-7 text-zinc-400">
            知识库页面用于接入本地项目资料、规范文件和历史案例，为项目分析与 AI 代理提供可追溯上下文。
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <div key={feature.title} className="rounded-lg border border-[#333333] bg-[#111111] p-5">
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-400 text-black">
                  <Icon size={20} />
                </div>
                <h3 className="mb-2 text-lg font-semibold text-white">{feature.title}</h3>
                <p className="text-sm leading-6 text-zinc-400">{feature.description}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
