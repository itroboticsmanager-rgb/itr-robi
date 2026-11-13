// Налаштування стійки з CRM, як їх віддає пристрій у знімку (D-068).
// Системні яскравість і гучність ставить сам пристрій; сюди доходить лише
// те, що вирішує сторінка: інтервал банерів, кнопки, рух, звук відео й сон.
// Значення перевіряються вдруге: знімок — вхідні дані, а не обіцянка.

export const DEFAULTS = Object.freeze({
  banner_interval_s: 14,
  reduced_motion: false,
  video_sound: true,
  video_volume: 80,
  show_wifi: true,
  show_scanner: true,
  open_now: true,
  sleeping: false,
});

const RANGES = { banner_interval_s: [4, 120], video_volume: [0, 100] };

export const kioskSettings = { ...DEFAULTS };

/** Приймає `snapshot.settings`; повертає true, якщо щось змінилося. */
export function applyKioskSettings(raw) {
  const next = { ...DEFAULTS };
  if (raw && typeof raw === 'object') {
    for (const [key, fallback] of Object.entries(DEFAULTS)) {
      const value = raw[key];
      if (typeof fallback === 'boolean' && typeof value === 'boolean') next[key] = value;
      else if (key in RANGES && Number.isInteger(value) && value >= RANGES[key][0] && value <= RANGES[key][1]) next[key] = value;
    }
  }
  const changed = Object.keys(next).some(key => next[key] !== kioskSettings[key]);
  Object.assign(kioskSettings, next);
  if (changed && typeof document !== 'undefined') document.dispatchEvent(new CustomEvent('robi:settings', { detail: { ...next } }));
  return changed;
}
