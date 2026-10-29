// Piksel-ofis xaritasi — 26x16 katak, 4 ta zona: DEV zona (chap), majlis
// xonasi (yuqori o'ng), server xonasi (pastki o'ng), dam olish (pastki chap).
// Katak kodlari T obyektida. Yurish mumkin: FLOOR va RUG, qolgani to'siq.

const TILE_SIZE = 32;
const OFFICE_COLS = 26;
const OFFICE_ROWS = 16;

const T = {
  FLOOR: 0,   // oddiy pol
  WALL: 1,    // devor
  DESK: 2,    // ish stoli (monitor bilan)
  CHAIR: 3,   // stul (majlis xonasida)
  PLANT: 4,   // o'simlik
  TABLE: 5,   // majlis stoli
  SOFA: 6,    // divan
  RACK: 7,    // server shkafi
  SHELF: 8,   // kitob javoni
  RUG: 9,     // gilam (dam olish zonasi, yurish mumkin)
  PING: 10,   // ping-pong stoli
};

// --- Xaritani dasturiy qurish -------------------------------------------
const OFFICE_GRID = [];
for (let r = 0; r < OFFICE_ROWS; r++) OFFICE_GRID.push(new Array(OFFICE_COLS).fill(T.FLOOR));

// Tashqi devorlar
for (let c = 0; c < OFFICE_COLS; c++) {
  OFFICE_GRID[0][c] = T.WALL;
  OFFICE_GRID[OFFICE_ROWS - 1][c] = T.WALL;
}
for (let r = 0; r < OFFICE_ROWS; r++) {
  OFFICE_GRID[r][0] = T.WALL;
  OFFICE_GRID[r][OFFICE_COLS - 1] = T.WALL;
}

// Majlis xonasi (yuqori o'ng): col 17 devor (eshik r=4), row 7 devor (eshik c=21)
for (let r = 1; r <= 6; r++) if (r !== 4) OFFICE_GRID[r][17] = T.WALL;
for (let c = 18; c <= 24; c++) if (c !== 21) OFFICE_GRID[7][c] = T.WALL;

// Server xonasi (pastki o'ng): col 17 devor (eshik r=11)
for (let r = 8; r <= 14; r++) if (r !== 11) OFFICE_GRID[r][17] = T.WALL;

// DEV zona desklari — 2 qator, har birining ostida agent o'tiradigan bo'sh joy
for (const r of [3, 7]) {
  for (const c of [3, 6, 9, 12]) OFFICE_GRID[r][c] = T.DESK;
}

// Majlis xonasi: 2x2 stol + atrofida stullar
for (const r of [3, 4]) for (const c of [20, 21]) OFFICE_GRID[r][c] = T.TABLE;
for (const [r, c] of [[2, 20], [2, 21], [5, 20], [5, 21], [3, 19], [4, 19], [3, 22], [4, 22]]) {
  OFFICE_GRID[r][c] = T.CHAIR;
}

// Server xonasi: rak ustunlari (r=11 yo'lak ochiq qoladi)
for (const c of [19, 21, 23]) {
  for (const r of [9, 10, 12, 13]) OFFICE_GRID[r][c] = T.RACK;
}

// Dam olish zonasi: gilam, divan, ping-pong, o'simliklar
for (let r = 11; r <= 14; r++) for (let c = 1; c <= 7; c++) {
  if (OFFICE_GRID[r][c] === T.FLOOR) OFFICE_GRID[r][c] = T.RUG;
}
for (const c of [2, 3, 4]) OFFICE_GRID[13][c] = T.SOFA;
OFFICE_GRID[11][6] = T.PING;
OFFICE_GRID[11][7] = T.PING;

// Kitob javonlari va o'simliklar
for (const c of [14, 15, 16]) OFFICE_GRID[1][c] = T.SHELF;
for (const [r, c] of [[1, 1], [1, 13], [9, 16], [14, 8], [8, 1], [1, 24], [14, 18], [14, 24]]) {
  if (OFFICE_GRID[r][c] === T.FLOOR || OFFICE_GRID[r][c] === T.RUG) OFFICE_GRID[r][c] = T.PLANT;
}

// --- Zonalar (pol rangi + yorliq) ----------------------------------------
const ZONES = [
  { name: "DEV ZONA", x1: 1, y1: 1, x2: 16, y2: 10, floor: 0x121624, label: { r: 1.45, c: 6.2 } },
  { name: "MAJLIS XONASI", x1: 18, y1: 1, x2: 24, y2: 6, floor: 0x3a2618, label: { r: 1.45, c: 19.2 } },
  { name: "SERVER XONASI", x1: 18, y1: 8, x2: 24, y2: 14, floor: 0x141a29, label: { r: 8.45, c: 18.8 } },
  { name: "DAM OLISH", x1: 1, y1: 11, x2: 8, y2: 14, floor: 0x2d4a3b, label: { r: 10.45, c: 2.0 } },
];

function zoneFloorColor(row, col) {
  for (const z of ZONES) {
    if (row >= z.y1 && row <= z.y2 && col >= z.x1 && col <= z.x2) return z.floor;
  }
  return 0x121624;
}

// --- Desklar ro'yxati (roster tartibida agentlarga beriladi) --------------
const DESKS = [];
for (let r = 0; r < OFFICE_ROWS; r++) {
  for (let c = 0; c < OFFICE_COLS; c++) {
    if (OFFICE_GRID[r][c] === T.DESK) DESKS.push({ row: r, col: c });
  }
}

// --- Yurish va yo'l topish -------------------------------------------------
function isWalkable(row, col) {
  if (row < 0 || row >= OFFICE_ROWS || col < 0 || col >= OFFICE_COLS) return false;
  const t = OFFICE_GRID[row][col];
  return t === T.FLOOR || t === T.RUG;
}

function tileToWorld(row, col) {
  return { x: col * TILE_SIZE + TILE_SIZE / 2, y: row * TILE_SIZE + TILE_SIZE / 2 };
}

// Ikki katak orasidagi eng qisqa yo'l — BFS (faqat yurish mumkin kataklar bo'ylab)
function bfsPath(startRow, startCol, targetRow, targetCol) {
  if (!isWalkable(targetRow, targetCol)) return [];
  if (startRow === targetRow && startCol === targetCol) return [];

  const key = (r, c) => `${r},${c}`;
  const visited = new Set([key(startRow, startCol)]);
  const queue = [[startRow, startCol, []]];
  const dirs = [[-1, 0], [1, 0], [0, -1], [0, 1]];

  while (queue.length) {
    const [r, c, path] = queue.shift();
    for (const [dr, dc] of dirs) {
      const nr = r + dr;
      const nc = c + dc;
      if (!isWalkable(nr, nc)) continue;
      const k = key(nr, nc);
      if (visited.has(k)) continue;
      visited.add(k);
      const newPath = [...path, { row: nr, col: nc }];
      if (nr === targetRow && nc === targetCol) return newPath;
      queue.push([nr, nc, newPath]);
    }
  }
  return [];
}

// Barcha yurish mumkin kataklar — bo'sh yurish (wander) uchun nomzodlar
const WALKABLE_TILES = [];
for (let r = 0; r < OFFICE_ROWS; r++) {
  for (let c = 0; c < OFFICE_COLS; c++) {
    if (isWalkable(r, c)) WALKABLE_TILES.push({ row: r, col: c });
  }
}
