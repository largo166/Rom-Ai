export type ExecutionReference = {
  source_path?: string;
  heading?: string;
  quote?: string;
};

export function compactReferenceLabel(ref: ExecutionReference) {
  const path = ref.source_path || '';
  const filename = path.split(/[\\/]/).filter(Boolean).pop() || '';
  return ref.heading || filename || '项目资料';
}

export function uniqueExecutionReferences(refs: ExecutionReference[]) {
  const seen = new Set<string>();
  return refs.filter((ref) => {
    const key = `${ref.source_path || ''}::${ref.heading || ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
