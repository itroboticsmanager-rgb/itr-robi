const paths = {
  courses: 'M4 8l8-5 8 5-8 5-8-5Zm3 3v6c3 3 7 3 10 0v-6M20 8v8',
  store: 'M4 8h16l-2-5H6L4 8Zm1 0v12h14V8M9 20v-7h6v7',
  price: 'M12 3v18M16 7H9a3 3 0 0 0 0 6h6a3 3 0 0 1 0 6H7',
  time: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  place: 'M12 21s7-6 7-11a7 7 0 0 0-14 0c0 5 7 11 7 11ZM12 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  contact: 'M4 6h16v12H4zM4 7l8 6 8-6',
  robot: 'M5 7h14v12H5zM12 7V3M8 11v3M16 11v3M9 17h6M2 10v6M22 10v6',
  video: 'M3 5h13v14H3zM16 10l5-3v10l-5-3',
  back: 'M15 5l-7 7 7 7', next: 'm9 5 7 7-7 7',
  home: 'm3 11 9-8 9 8M5 10v11h14V10M9 21v-7h6v7',
  grid: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  code: 'm8 8-4 4 4 4M16 8l4 4-4 4M14 4l-4 16',
  palette: 'M12 3a9 9 0 1 0 0 18c1.1 0 2-.8 2-1.8 0-1-.9-1.5-.9-2.4 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8ZM7.5 11.5h.01M10 7.5h.01M15 7.5h.01',
  cube: 'M12 3 4 7.5v9L12 21l8-4.5v-9L12 3ZM12 12v9M4 7.5 12 12l8-4.5',
  rocket: 'M9.5 14.5 7 12c1.2-4.6 4.6-8.4 12-9-.6 7.4-4.4 10.8-9 12ZM7 12l-3 1 2-4h4M12 17l-1 3 4-2v-4M6 17c-1.4.6-2 2.4-2 3.5 1.1 0 2.9-.6 3.5-2',
  check: 'm5 12.5 4.5 4.5L19 7',
};
// Ключі тем CRM (`course-theme.ts` у репо CRM) приходять із контентом як є,
// у нижньому регістрі. Власного малюнка під кожен тут немає й не треба:
// вони зводяться до кількох знайомих батькам образів, а невідоме — до сітки.
const themeAliases = {
  bot: 'robot', cpu: 'robot', circuit: 'robot', cog: 'robot', wrench: 'robot',
  terminal: 'code', laptop: 'code', monitor: 'code', smartphone: 'code', gamepad: 'code', joystick: 'code',
  brush: 'palette', pencil: 'palette', pen: 'palette', drama: 'palette', music: 'palette', mic: 'palette', headphones: 'palette',
  camera: 'video', clapperboard: 'video',
  box: 'cube', printer: 'cube', shapes: 'cube', ruler: 'cube', blocks: 'cube', puzzle: 'cube',
  sparkles: 'rocket', star: 'rocket', trophy: 'rocket', lightbulb: 'rocket', atom: 'rocket', flask: 'rocket', microscope: 'rocket', brain: 'rocket', globe: 'rocket', compass: 'rocket',
  coins: 'price', piggybank: 'price', banknote: 'price', wallet: 'price', creditcard: 'price', landmark: 'price', vault: 'price', handcoins: 'price', receipt: 'price', shoppingcart: 'price', percent: 'price', trendingup: 'price', piechart: 'price', scale: 'price', calculator: 'price',
  book: 'courses', graduationcap: 'courses', languages: 'courses', sprout: 'courses',
};
export function icon(name) {
  const aliases = { course: 'courses', products: 'store', prices: 'price', schedule: 'time', contacts: 'contact', location: 'place', form: 'contact', models: 'robot', ...themeAliases };
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', paths[aliases[name] ?? name] ?? paths.grid); svg.append(path); return svg;
}
export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
