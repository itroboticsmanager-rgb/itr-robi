// Галерея бере лише те, що віддає пристрій зі свого кешу: адреса з іншого
// місця — це вже не наш файл, і кіоск її не показує.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mediaOf, mediaSummary } from '../src/gallery.js';

test('обкладинка йде першою, далі галерея в порядку CRM', () => {
  const node = {
    image: '/media/content/level-1',
    media: [
      { kind: 'video', url: '/media/content/level-1/m/0', poster: '/media/content/level-1/m/0/poster' },
      { kind: 'image', url: '/media/content/level-1/m/1', poster: '' },
    ],
  };
  assert.deepEqual(mediaOf(node), [
    { kind: 'image', url: '/media/content/level-1', poster: '' },
    { kind: 'video', url: '/media/content/level-1/m/0', poster: '/media/content/level-1/m/0/poster' },
    { kind: 'image', url: '/media/content/level-1/m/1', poster: '' },
  ]);
});

test('чужі адреси й невідомі типи не потрапляють у галерею', () => {
  const node = {
    image: 'https://evil.example/x.jpg',
    media: [
      { kind: 'video', url: 'https://cdn.example/v.mp4' },
      { kind: 'gif', url: '/media/content/a/m/0' },
      { kind: 'video', url: '/media/content/a/m/1', poster: 'javascript:alert(1)' },
      null,
    ],
  };
  assert.deepEqual(mediaOf(node), [{ kind: 'video', url: '/media/content/a/m/1', poster: '' }]);
  assert.deepEqual(mediaOf({}), []);
  assert.deepEqual(mediaOf({ media: 'x' }), []);
});

test('підпис галереї рахує відео й фото окремо', () => {
  const v = { kind: 'video' }, p = { kind: 'image' };
  assert.equal(mediaSummary([v, p, p]), '1 відео · 2 фото');
  assert.equal(mediaSummary([p]), '1 фото');
  assert.equal(mediaSummary([v, v]), '2 відео');
});
