// Анкета з CRM у фреймі (D-065). Кіоск слухає лише свій фрейм і лише
// origin CRM: інакше будь-яка сторінка могла б закрити анкету чи вдати, що
// її надіслано.
import test from 'node:test';
import assert from 'node:assert/strict';
import { ENROLL_SOURCE, formOrigin, readFormMessage } from '../src/form.js';

const frame = {};
const ORIGIN = 'https://crm.itrobotics.com.ua';
const msg = (data, { source = frame, origin = ORIGIN } = {}) => ({ data, source, origin });

test('accepts known events from its own frame and origin', () => {
  for (const type of ['ready', 'activity', 'submitted', 'done', 'error']) {
    assert.equal(readFormMessage(msg({ source: ENROLL_SOURCE, type }), frame, ORIGIN), type);
  }
});

test('ignores other windows, origins and shapes', () => {
  const ok = { source: ENROLL_SOURCE, type: 'done' };
  assert.equal(readFormMessage(msg(ok, { source: {} }), frame, ORIGIN), null);
  assert.equal(readFormMessage(msg(ok, { origin: 'https://evil.example' }), frame, ORIGIN), null);
  assert.equal(readFormMessage(msg({ source: 'other', type: 'done' }), frame, ORIGIN), null);
  assert.equal(readFormMessage(msg({ source: ENROLL_SOURCE, type: 'navigate' }), frame, ORIGIN), null);
  assert.equal(readFormMessage(msg('done'), frame, ORIGIN), null);
  assert.equal(readFormMessage(msg(ok), null, ORIGIN), null);
});

test('frames only https addresses (and a CRM on the loopback for local checks)', () => {
  assert.equal(formOrigin('https://crm.itrobotics.com.ua/enroll/abc?kiosk=1'), ORIGIN);
  assert.equal(formOrigin('http://crm.itrobotics.com.ua/enroll/abc'), '');
  assert.equal(formOrigin('javascript:alert(1)'), '');
  assert.equal(formOrigin(''), '');
  assert.equal(formOrigin(undefined), '');
  assert.equal(formOrigin('http://localhost:3012/enroll/abc'), 'http://localhost:3012');
  assert.equal(formOrigin('http://evil.localhost.example/enroll'), '');
});
