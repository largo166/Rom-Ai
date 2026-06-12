import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseMeetingActionItems } from './meetingActions.ts';

test('formats meeting action objects as readable text', () => {
  const actions = parseMeetingActionItems(JSON.stringify([
    { title: '补齐规划条件', owner: '项目经理', status: 'todo' },
    { title: '整理技术复用卡', owner: 'AI资料管理员' },
  ]));

  assert.deepEqual(actions, [
    '补齐规划条件（项目经理 · todo）',
    '整理技术复用卡（AI资料管理员）',
  ]);
});

test('keeps string meeting actions readable', () => {
  const actions = parseMeetingActionItems(JSON.stringify(['确认会议纪要', '同步任务看板']));

  assert.deepEqual(actions, ['确认会议纪要', '同步任务看板']);
});
