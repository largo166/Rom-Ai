import { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { fetchRecommendations } from '../../lib/projectsApi';

export type RecommendationItem = {
  title: string;
  content_preview: string;
  source_type: string;
  source_id: string;
  source_path: string;
  hit_reason: string;
  relevance_score: number;
};

export type RecommendationsResult = {
  trigger: string;
  recommendations: RecommendationItem[];
  query_keywords: string[];
  generated_at: string;
};

type Props = {
  projectId: string;
  trigger: string;
  options?: {
    transcript_text?: string;
    card_type?: string;
    file_names?: string;
    limit?: number;
  };
};

function sourceIcon(sourceType: string): string {
  if (sourceType === 'knowledge_item') return '📄';
  if (sourceType === 'skill_card') return '🎯';
  if (sourceType === 'meeting') return '📋';
  if (sourceType === 'inbox') return '📥';
  return '📄';
}

function sourceLabel(sourceType: string): string {
  if (sourceType === 'knowledge_item') return '知识库';
  if (sourceType === 'skill_card') return '技能卡';
  if (sourceType === 'meeting') return '会议';
  if (sourceType === 'inbox') return '收件箱';
  return '知识库';
}

export function RecommendationPanel({ projectId, trigger, options }: Props) {
  const [data, setData] = useState<RecommendationsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [fetched, setFetched] = useState(false);

  // 懒加载：展开时才请求
  useEffect(() => {
    if (collapsed || fetched) return;
    if (!projectId) return;

    let cancelled = false;
    setLoading(true);

    fetchRecommendations(projectId, trigger, options)
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setFetched(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData({ trigger, recommendations: [], query_keywords: [], generated_at: '' });
          setFetched(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, trigger, options, collapsed, fetched]);

  const items = data?.recommendations ?? [];
  const count = items.length;

  return (
    <div className="rounded-lg border border-stone-200 bg-[#FAF8F5]">
      {/* 面板标题栏 */}
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-left"
        onClick={() => setCollapsed((v) => !v)}
      >
        <span className="flex items-center gap-2">
          <span className="font-serif text-sm font-semibold text-stone-700">相关知识推荐</span>
          {!loading && count > 0 && (
            <span className="rounded-full bg-stone-200 px-2 py-0.5 text-[11px] text-stone-600">
              {count}
            </span>
          )}
        </span>
        <span className="text-stone-400">
          {collapsed ? <ChevronDown size={15} /> : <ChevronUp size={15} />}
        </span>
      </button>

      {/* 面板内容 */}
      {!collapsed && (
        <div className="border-t border-stone-100">
          {loading ? (
            /* 骨架屏 */
            <div className="space-y-3 p-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="space-y-1.5">
                  <div className="h-3.5 w-2/3 animate-pulse rounded bg-stone-100" />
                  <div className="h-3 w-full animate-pulse rounded bg-stone-100" />
                  <div className="h-3 w-4/5 animate-pulse rounded bg-stone-100" />
                </div>
              ))}
            </div>
          ) : items.length === 0 ? (
            /* 空状态 */
            <div className="py-5 text-center">
              <p className="text-sm italic text-stone-400">暂无相关推荐</p>
            </div>
          ) : (
            /* 推荐列表 */
            <div>
              {items.map((item, idx) => (
                <div
                  key={item.source_id || idx}
                  className={`px-4 py-3 ${idx < items.length - 1 ? 'border-b border-stone-100' : ''}`}
                >
                  <div className="mb-1 flex items-start justify-between gap-2">
                    <span className="font-serif text-sm font-medium text-stone-800 leading-snug">
                      {sourceIcon(item.source_type)} {item.title}
                    </span>
                    <span className="shrink-0 rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-600">
                      {sourceLabel(item.source_type)}
                    </span>
                  </div>
                  {item.content_preview && (
                    <p className="mb-1.5 line-clamp-2 text-sm leading-5 text-stone-600">
                      {item.content_preview}
                    </p>
                  )}
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-600">
                      {item.hit_reason}
                    </span>
                    {item.relevance_score > 0 && (
                      <span className="text-[11px] text-stone-400">
                        相关度 {Math.round(item.relevance_score * 100)}%
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
