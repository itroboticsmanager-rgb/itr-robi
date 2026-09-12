// Кнопка-код у меню («Оплатити», D-060). Вона показується лише тоді, коли
// пристрій підтвердив, що її посилання пройде allowlist: дотик у нікуди біля
// стійки гірший за відсутню кнопку.
import test from 'node:test';
import assert from 'node:assert/strict';
import { ContentTree } from '../src/content.js';

const tree = pay => new ContentTree({
  content: {
    root: 'root',
    nodes: [
      { id: 'root', kind: 'menu', title: 'Обрати заняття', items: ['robo', 'pay'] },
      { id: 'robo', kind: 'card', title: 'Робототехніка', items: [] },
      { id: 'pay', kind: 'qr', title: 'Оплатити', items: [], ...pay },
    ],
  },
});

test('кнопка-код розпізнається окремо від меню й картки', () => {
  const t = tree({ allowed: true });
  assert.equal(t.isQr('pay'), true);
  assert.equal(t.isQr('robo'), false);
  assert.equal(t.isCard('pay'), false);
  assert.equal(t.isMenu('pay'), false);
});

test('кнопка-код видима лише з підтвердженням пристрою', () => {
  assert.equal(tree({ allowed: true }).visible('pay'), true);
  assert.equal(tree({ allowed: false }).visible('pay'), false);
  // Старий пристрій, що не знає про allowed, кнопки теж не покаже.
  assert.equal(tree({}).visible('pay'), false);
});

test('звичайні вузли видимі завжди, невідомі — ні', () => {
  const t = tree({ allowed: false });
  assert.equal(t.visible('robo'), true);
  assert.equal(t.visible('root'), true);
  assert.equal(t.visible('нема'), false);
});
