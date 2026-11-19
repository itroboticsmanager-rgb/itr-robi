// «Що зараз на заняттях»: поділ за годинником планшета, без мережі.
import test from 'node:test';
import assert from 'node:assert/strict';
import { hasLessonsAhead, splitLessons } from '../src/lessons.js';

const at = iso => Date.parse(iso);
const lessons = [
  { id: 1, course: 'Lego', start: '2026-11-19T12:00:00Z', end: '2026-11-19T13:30:00Z' },
  { id: 2, course: 'Python', start: '2026-11-19T14:30:00Z', end: '2026-11-19T16:00:00Z' },
  { id: 3, course: 'Scratch', start: '2026-11-19T16:00:00Z', end: '2026-11-19T17:30:00Z' },
  { id: 4, course: 'Криве', start: 'вчора', end: '2026-11-19T17:30:00Z' },
];

test('заняття діляться на зараз, далі й завершені', () => {
  const parts = splitLessons(lessons, at('2026-11-19T15:00:00Z'));
  assert.deepEqual(parts.now.map(l => l.id), [2]);
  assert.deepEqual(parts.next.map(l => l.id), [3]);
  assert.deepEqual(parts.done.map(l => l.id), [1]);
});

test('межі: початок — уже «зараз», кінець — уже «завершилось»', () => {
  assert.deepEqual(splitLessons(lessons, at('2026-11-19T14:30:00Z')).now.map(l => l.id), [2]);
  assert.deepEqual(splitLessons(lessons, at('2026-11-19T16:00:00Z')).now.map(l => l.id), [3]);
});

test('кнопка на головній — лише поки сьогодні щось попереду', () => {
  assert.equal(hasLessonsAhead(lessons, at('2026-11-19T15:00:00Z')), true);
  assert.equal(hasLessonsAhead(lessons, at('2026-11-19T18:00:00Z')), false);
  assert.equal(hasLessonsAhead(undefined), false);
});
