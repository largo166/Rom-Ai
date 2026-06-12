type ActionObject = {
  title?: unknown;
  owner?: unknown;
  status?: unknown;
};

function formatActionObject(item: ActionObject) {
  const title = typeof item.title === 'string' ? item.title.trim() : '';
  const owner = typeof item.owner === 'string' ? item.owner.trim() : '';
  const status = typeof item.status === 'string' ? item.status.trim() : '';
  const details = [owner, status].filter(Boolean).join(' · ');

  if (title && details) return `${title}（${details}）`;
  if (title) return title;
  if (details) return details;
  return '';
}

function toActionText(item: unknown) {
  if (typeof item === 'string') return item;
  if (typeof item === 'object' && item !== null) {
    const formatted = formatActionObject(item as ActionObject);
    return formatted || JSON.stringify(item);
  }
  return String(item);
}

export function parseMeetingActionItems(nextActionsJson: string) {
  if (!nextActionsJson) return [];
  try {
    const parsed = JSON.parse(nextActionsJson);
    if (Array.isArray(parsed)) return parsed.map(toActionText);
    if (typeof parsed === 'object' && parsed !== null) {
      return Object.values(parsed as Record<string, unknown>).flatMap((value) => {
        if (Array.isArray(value)) return value.map(toActionText);
        return [toActionText(value)];
      });
    }
    return [];
  } catch {
    return [];
  }
}
