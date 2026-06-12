import test from 'node:test';
import assert from 'node:assert/strict';
import { compactReferenceLabel, uniqueExecutionReferences } from './executionReferences.ts';

test('uses heading as compact reference label first', () => {
  const label = compactReferenceLabel({
    heading: '启动会纪要',
    source_path: 'project-deposits/project-1/meetings/meeting-1.md',
  });

  assert.equal(label, '启动会纪要');
});

test('falls back to filename for compact reference label', () => {
  const label = compactReferenceLabel({
    source_path: 'project-deposits/project-1/meetings/meeting-1.md',
  });

  assert.equal(label, 'meeting-1.md');
});

test('deduplicates repeated execution references', () => {
  const refs = uniqueExecutionReferences([
    { heading: '启动会纪要', source_path: 'a.md' },
    { heading: '启动会纪要', source_path: 'a.md' },
    { heading: '任务拆解', source_path: 'b.md' },
  ]);

  assert.deepEqual(refs, [
    { heading: '启动会纪要', source_path: 'a.md' },
    { heading: '任务拆解', source_path: 'b.md' },
  ]);
});
