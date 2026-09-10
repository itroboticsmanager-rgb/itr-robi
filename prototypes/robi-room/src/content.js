// Контент-меню у вебі. Правила навігації повторюють `InfoMode` на пристрої:
// стек вузлів, крок назад із кореня означає вихід, а стан не переживає вихід.
// Це не збіг і не стиль — поки обидва шляхи живі, вони мусять поводитися
// однаково, інакше перемикання між ними змінить поведінку для відвідувача.
//
// Вузол лишається набором полів (`D-048`): жодної розмітки з CRM тут не
// виконується, рендер вирішує клієнт.

export class ContentTree {
  constructor(snapshot) {
    const raw = snapshot?.content ?? {};
    this.nodes = new Map();
    for (const node of Array.isArray(raw.nodes) ? raw.nodes : []) {
      if (node && typeof node.id === 'string' && node.id) this.nodes.set(node.id, node);
    }
    this.root = typeof raw.root === 'string' && this.nodes.has(raw.root) ? raw.root : '';
  }
  // Порожній або битий контент — не аварія: меню просто немає, а решта
  // пристрою працює далі. Так само поводиться pygame-версія.
  get available() { return this.root !== ''; }
  node(id) { return this.nodes.get(id) ?? null; }
  has(id) { return this.nodes.has(id); }
  labelFor(id) { return this.nodes.get(id)?.title ?? ''; }
  iconFor(id) { return this.nodes.get(id)?.icon ?? ''; }
  isMenu(id) { return this.nodes.get(id)?.kind === 'menu'; }
}

export class Navigation {
  constructor(tree) {
    this.tree = tree;
    this.stack = tree.available ? [tree.root] : [];
    this.released = false;
    this.direction = 1;
  }
  get current() { return this.tree.node(this.stack[this.stack.length - 1]); }
  get depth() { return this.stack.length; }
  get atRoot() { return this.stack.length === 1; }

  /** Відкрити меню, за потреби одразу на гілці з команди CRM. */
  enter(nodeId = '') {
    if (!this.tree.available) return false;
    this.stack = [this.tree.root];
    this.released = false;
    this.direction = 1;
    // `id` з команди — вхідні дані, а не адреса, якій можна вірити.
    const target = String(nodeId ?? '').trim();
    if (target && this.tree.has(target) && target !== this.tree.root) this.stack.push(target);
    return true;
  }
  open(nodeId) {
    if (!this.tree.has(nodeId)) return false;
    this.stack.push(nodeId);
    this.direction = 1;
    return true;
  }
  /** Крок назад. Із кореня це вихід із меню, а не глухий кут. */
  back() {
    if (this.stack.length > 1) { this.stack.pop(); this.direction = -1; return false; }
    this.released = true;
    return true;
  }
  /** Наступний відвідувач починає з початку, а не там, де копався попередній. */
  exit() {
    this.stack = this.tree.available ? [this.tree.root] : [];
    this.released = false;
  }
}

/** Знімок стану пристрою. Помилка мережі — не аварія: меню просто немає. */
export async function readSnapshot(fetcher = fetch, url = '/api/snapshot') {
  try {
    const response = await fetcher(url, { cache: 'no-store' });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}
