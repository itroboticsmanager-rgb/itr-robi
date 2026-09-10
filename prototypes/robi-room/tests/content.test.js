// Меню у вебі мусить поводитися рівно так, як `InfoMode` на пристрої: доки
// живі обидва шляхи, розбіжність у навігації змінила б поведінку для
// відвідувача просто від того, який із них зараз показує екран.
import test from 'node:test';
import assert from 'node:assert/strict';
import { ContentTree, Navigation, readSnapshot } from '../src/content.js';

const SNAPSHOT = {
  revision: 1,
  device: { id: 'robi-1', site: 'kyiv' },
  mascot: { state: 'idle' },
  content: {
    root: 'root',
    nodes: [
      { id: 'root', kind: 'menu', title: 'Головна', items: ['kurs', 'ціни'], body: '', price: '', icon: '', image: '' },
      { id: 'kurs', kind: 'menu', title: 'Курси', items: ['robo'], body: '', price: '', icon: 'course', image: '' },
      { id: 'robo', kind: 'card', title: 'Робототехніка', items: [], body: 'Опис', price: '1200 грн', icon: '', image: 'robo.png' },
      { id: 'ціни', kind: 'card', title: 'Ціни', items: [], body: 'Таблиця', price: '', icon: '', image: '' },
    ],
  },
};

const tree = () => new ContentTree(SNAPSHOT);

test('дерево читає вузли й корінь зі знімка', () => {
  const t = tree();
  assert.equal(t.available, true);
  assert.equal(t.root, 'root');
  assert.equal(t.labelFor('robo'), 'Робототехніка');
  assert.equal(t.iconFor('kurs'), 'course');
  assert.equal(t.isMenu('root'), true);
  assert.equal(t.isMenu('robo'), false);
  assert.equal(t.node('немає'), null);
});

test('порожній або битий контент означає відсутнє меню, а не аварію', () => {
  for (const snapshot of [undefined, {}, { content: {} }, { content: { root: 'x', nodes: [] } }]) {
    const t = new ContentTree(snapshot);
    assert.equal(t.available, false);
    assert.equal(new Navigation(t).enter(), false);
  }
});

test('навігація починається з кореня і заглиблюється стеком', () => {
  const nav = new Navigation(tree());
  assert.equal(nav.enter(), true);
  assert.equal(nav.current.id, 'root');
  assert.equal(nav.depth, 1);
  assert.equal(nav.open('kurs'), true);
  assert.equal(nav.open('robo'), true);
  assert.equal(nav.current.id, 'robo');
  assert.equal(nav.depth, 3);
});

test('крок назад піднімає стек, а з кореня означає вихід', () => {
  const nav = new Navigation(tree());
  nav.enter(); nav.open('kurs');
  assert.equal(nav.back(), false);
  assert.equal(nav.current.id, 'root');
  assert.equal(nav.released, false);
  // Із кореня повертатися нікуди: це вихід із меню, а не глухий кут.
  assert.equal(nav.back(), true);
  assert.equal(nav.released, true);
});

test('команда CRM відкриває наявну гілку і відхиляє вигадану', () => {
  const nav = new Navigation(tree());
  nav.enter('kurs');
  assert.deepEqual(nav.stack, ['root', 'kurs']);
  // Невідомий id — це вхідні дані, а не адреса, якій можна вірити.
  nav.enter('../secret');
  assert.deepEqual(nav.stack, ['root']);
  // Корінь у команді не подвоюється.
  nav.enter('root');
  assert.deepEqual(nav.stack, ['root']);
});

test('вихід скидає стан, щоб наступний відвідувач починав з початку', () => {
  const nav = new Navigation(tree());
  nav.enter(); nav.open('kurs'); nav.open('robo');
  nav.back(); nav.back(); nav.back();
  assert.equal(nav.released, true);
  nav.exit();
  assert.deepEqual(nav.stack, ['root']);
  assert.equal(nav.released, false);
});

test('невідомий вузол не потрапляє в стек', () => {
  const nav = new Navigation(tree());
  nav.enter();
  assert.equal(nav.open('нема-такого'), false);
  assert.equal(nav.depth, 1);
});

test('знімок читається, а збій мережі лишає пристрій без меню, не в аварії', async () => {
  const ok = await readSnapshot(async () => ({ ok: true, json: async () => SNAPSHOT }));
  assert.equal(ok.content.root, 'root');
  assert.equal(await readSnapshot(async () => ({ ok: false })), null);
  assert.equal(await readSnapshot(async () => { throw new Error('offline'); }), null);
  assert.equal(await readSnapshot(async () => ({ ok: true, json: async () => { throw new Error('bad json'); } })), null);
});
