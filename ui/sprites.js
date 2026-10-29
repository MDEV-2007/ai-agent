// Proseduraviy piksel-odam sprite'lari. Tashqi rasm fayllarisiz — har agent
// uchun 4 yo'nalish x 2 yurish kadri Phaser Graphics orqali texturaga chiziladi.
// Har piksel PX marta kattalashtiriladi (12x16 piksel odam -> 24x32 ekranda).

const PX = 2;          // bitta "piksel"ning ekran o'lchami
const SPRITE_W = 12;   // odam kengligi (piksel)
const SPRITE_H = 16;   // odam balandligi (piksel)

// Har agent uchun rang palitralari (roster tartibida beriladi)
const CHARACTER_PALETTES = [
  { skin: 0xf0c8a0, hair: 0x2b1d0e, shirt: 0x38bdf8, pants: 0x1e293b, longHair: false }, // Aziz
  { skin: 0xe8b88a, hair: 0x151515, shirt: 0xec4899, pants: 0x3b2f4f, longHair: true },  // Malika
  { skin: 0xd9a066, hair: 0x5a3825, shirt: 0x8fc93a, pants: 0x30362a, longHair: false }, // Bek
  { skin: 0xf0c8a0, hair: 0x6b3fa0, shirt: 0xa855f7, pants: 0x403020, longHair: true },  // Nilufar
  { skin: 0xe8b88a, hair: 0x334155, shirt: 0x22c55e, pants: 0x1e293b, longHair: false }, // Timur
];

// Bitta piksel-katak chizish yordamchisi
function px(g, x, y, w, h, color) {
  g.fillStyle(color, 1);
  g.fillRect(x * PX, y * PX, w * PX, h * PX);
}

// Bitta kadrni chizadi: dir = down|up|left|right, frame = 0|1
function drawPerson(g, dir, frame, pal) {
  const SHOE = 0x1a1a1a;

  // Soch (bosh usti)
  px(g, 3, 0, 6, 3, pal.hair);

  // Yuz yoki boshning orqasi
  if (dir === "up") {
    px(g, 3, 3, 6, 3, pal.hair); // orqadan soch ko'rinadi
  } else {
    px(g, 3, 3, 6, 3, pal.skin);
    if (dir === "down") {
      px(g, 4, 4, 1, 1, 0x222222); // ikki ko'z
      px(g, 7, 4, 1, 1, 0x222222);
    } else if (dir === "left") {
      px(g, 4, 4, 1, 1, 0x222222); // profil — bitta ko'z
    } else if (dir === "right") {
      px(g, 7, 4, 1, 1, 0x222222);
    }
  }

  // Uzun soch (yelkaga tushadi)
  if (pal.longHair && dir !== "up") {
    px(g, 2, 2, 1, 5, pal.hair);
    px(g, 9, 2, 1, 5, pal.hair);
  }

  // Tana (ko'ylak) va qo'llar
  px(g, 3, 6, 6, 5, pal.shirt);
  px(g, 2, 6, 1, 3, pal.shirt);  // chap yeng
  px(g, 9, 6, 1, 3, pal.shirt);  // o'ng yeng
  px(g, 2, 9, 1, 1, pal.skin);   // chap qo'l
  px(g, 9, 9, 1, 1, pal.skin);   // o'ng qo'l

  // Shim: son qismi to'liq, oyoqlar alohida
  px(g, 3, 11, 6, 1, pal.pants);
  px(g, 3, 12, 2, 2, pal.pants); // chap oyoq
  px(g, 7, 12, 2, 2, pal.pants); // o'ng oyoq

  // Poyabzal — yurish kadriga qarab almashinadi
  if (frame === 0) {
    px(g, 3, 14, 2, 1, SHOE);
    px(g, 7, 14, 2, 1, SHOE);
  } else {
    px(g, 3, 13, 2, 1, SHOE); // chap oyoq ko'tarilgan
    px(g, 7, 15, 2, 1, SHOE); // o'ng oyoq oldinda
  }
}

// Agent uchun barcha kadr texturalarini yaratadi.
// Textura kalitlari: `${key}-down-0`, `${key}-left-1` va hokazo.
function createCharacterTextures(scene, key, pal) {
  for (const dir of ["down", "up", "left", "right"]) {
    for (const frame of [0, 1]) {
      const texKey = `${key}-${dir}-${frame}`;
      if (scene.textures.exists(texKey)) continue;
      const g = scene.add.graphics();
      drawPerson(g, dir, frame, pal);
      g.generateTexture(texKey, SPRITE_W * PX, SPRITE_H * PX);
      g.destroy();
    }
  }
}
