// Знімок — вхідні дані: криве значення з пристрою не має зламати кіоск,
// а лише лишити типове.
import test from 'node:test';
import assert from 'node:assert/strict';
import { applyKioskSettings, DEFAULTS, kioskSettings } from '../src/kiosk-settings.js';

test('налаштування зі знімка застосовуються й повідомляють про зміну', () => {
  applyKioskSettings(undefined);
  assert.equal(applyKioskSettings({ banner_interval_s: 30, show_wifi: false, sleeping: true }), true);
  assert.equal(kioskSettings.banner_interval_s, 30);
  assert.equal(kioskSettings.show_wifi, false);
  assert.equal(kioskSettings.sleeping, true);
  assert.equal(applyKioskSettings({ banner_interval_s: 30, show_wifi: false, sleeping: true }), false);
});

test('криві значення лишають типові', () => {
  applyKioskSettings({ banner_interval_s: 1, video_volume: 300, show_wifi: 'no', reduced_motion: 1 });
  assert.deepEqual({ ...kioskSettings }, { ...DEFAULTS });
  applyKioskSettings(null);
  assert.deepEqual({ ...kioskSettings }, { ...DEFAULTS });
});
