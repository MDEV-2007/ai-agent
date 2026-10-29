// AgentLab HQ — asosiy frontend fayli: Phaser sahnasi (ofis + mebel),
// personajlar (yurish, deskda ishlash, speech-bubble), HUD (agent tanlash,
// vazifa yuborish) va WebSocket orqali real vaqtda holat yangilanishi.

// ---------------------------------------------------------------- Global holat
let selectedAgentId = null;
const AGENT_INFO = {};   // agent_id -> {name, role, status, ...} (oxirgi payload)
const AGENT_ORDER = [];  // roster kelish tartibi (desk/palitra indeksi uchun)
const AGENT_QUEUES = {}; // agent_id -> kutayotgan vazifalar
let officeScene = null;

const STATUS_LABELS = {
  idle: "bo'sh",
  thinking: "o'ylayapti",
  running: "ishlayapti",
  done: "tugatdi",
  error: "xatolik",
};
const STATUS_COLORS = {
  idle: "#94a3b8",
  thinking: "#f59e0b",
  running: "#22c55e",
  done: "#38bdf8",
  error: "#ef4444",
};

// ---------------------------------------------------------------- Personaj
class AgentCharacter {
  constructor(scene, agentId, index) {
    this.scene = scene;
    this.agentId = agentId;
    this.texKey = `char-${agentId}`;
    
    // Skrinshotdagi kabi boshlang'ich o'rinlar (Aziz, Malika, Bek, Nilufar, Timur)
    const initialSeats = [
      { row: 12, col: 2 },  // Aziz (Dam Olish)
      { row: 4, col: 12 },  // Malika (Dev Zona)
      { row: 4, col: 10 },  // Bek (Dev Zona)
      { row: 13, col: 10 }, // Nilufar (Yo'lak)
      { row: 2, col: 5 },   // Timur (Dev Zona)
    ];

    const seat = initialSeats[index % initialSeats.length] || DESKS[index % DESKS.length];
    this.deskPos = seat;
    this.seatRow = seat.row;
    this.seatCol = seat.col;

    this.row = this.seatRow;
    this.col = this.seatCol;
    this.path = [];
    this.moving = false;
    this.dir = "down";
    this.frame = 0;
    this.status = "idle";
    this.localIdle = true;
    this.wanderTimer = Phaser.Math.Between(300, 600);

    const pal = CHARACTER_PALETTES[index % CHARACTER_PALETTES.length];
    createCharacterTextures(scene, this.texKey, pal);

    const { x, y } = tileToWorld(this.row, this.col);
    
    // Agent oyog'i ostidagi miltillovchi rangli neon aura halqasi (skrinshotdagi kabi)
    const auraColors = [0x38bdf8, 0xec4899, 0xf59e0b, 0xa855f7, 0x22c55e];
    const auraColor = auraColors[index % auraColors.length];
    this.auraRing = scene.add.ellipse(x, y + 10, 24, 12, auraColor, 0.5).setDepth(9);
    scene.tweens.add({
      targets: this.auraRing,
      alpha: 0.85,
      scaleX: 1.15,
      scaleY: 1.15,
      duration: 1000,
      yoyo: true,
      repeat: -1,
    });

    this.sprite = scene.add.image(x, y, `${this.texKey}-down-0`).setDepth(10);
    this.statusIcon = scene.add.text(x + 12, y - 26, "", { fontSize: "14px" }).setDepth(12);
    this.bubble = scene.add
      .text(x, y - 40, "", {
        fontSize: "10px",
        fontFamily: "monospace",
        color: "#ffffff",
        backgroundColor: "#000000dd",
        padding: { x: 5, y: 3 },
        wordWrap: { width: 140 },
      })
      .setOrigin(0.5, 1)
      .setDepth(13)
      .setVisible(false);
    this.nameLabel = scene.add
      .text(x, y + 17, "", {
        fontSize: "10px",
        fontFamily: "Inter, system-ui, sans-serif",
        fontWeight: "700",
        color: "#ffffff",
        backgroundColor: "#10141fdd",
        padding: { x: 5, y: 2 },
      })
      .setOrigin(0.5, 0)
      .setDepth(12);
  }

  setName(name) {
    this.nameLabel.setText(name);
  }

  applyState(state) {
    this.status = state.status;
    this.localIdle = state.status === "idle";
    const task = state.current_task || "";
    const tool = state.current_tool ? `[${state.current_tool}]` : "";

    if (state.status === "thinking") {
      this.statusIcon.setText("\u{1F4AD}");
      this.setBubble(task || "o'ylayapman...");
      this.goToSeat();
    } else if (state.status === "running") {
      const reading = /read|list|screenshot/.test(state.current_tool || "");
      this.statusIcon.setText(reading ? "\u{1F4D6}" : "\u{2328}\u{FE0F}");
      this.setBubble(`${tool} ${task}`.trim());
      this.goToSeat();
    } else if (state.status === "done") {
      this.statusIcon.setText("\u{2705}");
      this.setBubble(state.last_message || "tayyor");
      this.scene.time.delayedCall(5000, () => {
        if (this.status === "done") {
          this.bubble.setVisible(false);
          this.statusIcon.setText("");
          this.localIdle = true; // yana ofis bo'ylab yurishi mumkin
        }
      });
    } else if (state.status === "error") {
      this.statusIcon.setText("\u{26A0}\u{FE0F}");
      this.setBubble(state.last_message || "xatolik");
      this.scene.time.delayedCall(7000, () => {
        if (this.status === "error") {
          this.bubble.setVisible(false);
          this.statusIcon.setText("");
          this.localIdle = true;
        }
      });
    } else {
      this.statusIcon.setText("");
      this.bubble.setVisible(false);
    }
  }

  setBubble(text) {
    if (!text) {
      this.bubble.setVisible(false);
      return;
    }
    this.bubble.setText(text.length > 90 ? text.slice(0, 90) + "…" : text);
    this.bubble.setVisible(true);
  }

  // Tasdiq kutilayotganda personaj tepasida pauza belgisi ko'rsatiladi.
  // Keyingi holat xabari (approve/rad) kelganda applyState uni almashtiradi.
  markWaitingApproval(reason) {
    this.statusIcon.setText("\u{23F8}\u{FE0F}");
    this.setBubble(`⏸ tasdiq kutilmoqda: ${reason}`);
  }

  goToSeat() {
    if (this.row === this.seatRow && this.col === this.seatCol) {
      this.faceDesk();
      return;
    }
    this.moveTo(this.seatRow, this.seatCol);
  }

  faceDesk() {
    this.dir = "up"; // desk tepada — unga qaraydi
    this.sprite.setTexture(`${this.texKey}-up-0`);
  }

  moveTo(targetRow, targetCol) {
    const path = bfsPath(this.row, this.col, targetRow, targetCol);
    if (path.length) this.path = path;
  }

  wander() {
    const canWander = this.localIdle && !this.path.length && !this.moving;
    if (!canWander) return;
    this.wanderTimer -= 1;
    if (this.wanderTimer > 0) return;
    this.wanderTimer = Phaser.Math.Between(150, 400);
    const target = Phaser.Utils.Array.GetRandom(WALKABLE_TILES);
    if (target) this.moveTo(target.row, target.col);
  }

  update() {
    this.wander();

    if (this.path.length && !this.moving) {
      const next = this.path.shift();
      this.moving = true;

      // Yo'nalishni aniqlash va yurish kadrini almashtirish
      if (next.col > this.col) this.dir = "right";
      else if (next.col < this.col) this.dir = "left";
      else if (next.row > this.row) this.dir = "down";
      else this.dir = "up";
      this.frame = this.frame === 0 ? 1 : 0;
      this.sprite.setTexture(`${this.texKey}-${this.dir}-${this.frame}`);

      const { x, y } = tileToWorld(next.row, next.col);
      this.scene.tweens.add({
        targets: this.sprite,
        x, y,
        duration: 240,
        onUpdate: () => this.syncOverlays(),
        onComplete: () => {
          this.row = next.row;
          this.col = next.col;
          this.moving = false;
          if (!this.path.length) {
            // Manzilga yetdi: ish holatida deskka qaraydi, aks holda tik turadi
            if ((this.status === "running" || this.status === "thinking") &&
                this.row === this.seatRow && this.col === this.seatCol) {
              this.faceDesk();
            } else {
              this.sprite.setTexture(`${this.texKey}-${this.dir}-0`);
            }
          }
        },
      });
    } else {
      this.syncOverlays();
    }
  }

  syncOverlays() {
    const x = this.sprite.x;
    const y = this.sprite.y;
    if (this.auraRing) this.auraRing.setPosition(x, y + 10);
    this.statusIcon.setPosition(x + 12, y - 26);
    this.bubble.setPosition(x, y - 40);
    this.nameLabel.setPosition(x, y + 17);
  }
}

// ---------------------------------------------------------------- Sahna
class OfficeScene extends Phaser.Scene {
  constructor() {
    super("office");
    this.characters = {};
  }

  create() {
    officeScene = this;
    this.drawOffice();
    this.drawZoneLabels();
    connectSocket();
    fetch("/agents")
      .then((r) => r.json())
      .then((list) => list.forEach((s) => handleStatePayload(s)));
  }

  // --- Ofisni chizish: pol, devor va mebel ---
  drawOffice() {
    const g = this.add.graphics();

    for (let r = 0; r < OFFICE_ROWS; r++) {
      for (let c = 0; c < OFFICE_COLS; c++) {
        const tile = OFFICE_GRID[r][c];
        const x = c * TILE_SIZE;
        const y = r * TILE_SIZE;

        // Avval pol (zona rangi bilan)
        const floorColor = tile === T.RUG ? 0x7fa06a : zoneFloorColor(r, c);
        g.fillStyle(floorColor, 1);
        g.fillRect(x, y, TILE_SIZE - 1, TILE_SIZE - 1);

        switch (tile) {
          case T.WALL:
            g.fillStyle(0x33343a, 1);
            g.fillRect(x, y, TILE_SIZE, TILE_SIZE);
            g.fillStyle(0x44454d, 1);
            g.fillRect(x, y, TILE_SIZE, 5); // yuqori qirra effekti
            break;
          case T.DESK:
            this.drawDesk(g, x, y);
            break;
          case T.CHAIR:
            g.fillStyle(0x5c4a32, 1);
            g.fillRect(x + 9, y + 9, 14, 14);
            g.fillStyle(0x4a3a26, 1);
            g.fillRect(x + 9, y + 6, 14, 4);
            break;
          case T.TABLE:
            g.fillStyle(0xa9814f, 1);
            g.fillRect(x, y, TILE_SIZE, TILE_SIZE);
            g.fillStyle(0x8d6a3f, 1);
            g.fillRect(x, y, TILE_SIZE, 4);
            break;
          case T.PLANT:
            g.fillStyle(0x7c5a3a, 1);
            g.fillRect(x + 11, y + 20, 10, 8); // tuvak
            g.fillStyle(0x3f7d3f, 1);
            g.fillCircle(x + 16, y + 14, 8);
            g.fillStyle(0x549e54, 1);
            g.fillCircle(x + 12, y + 10, 5);
            g.fillCircle(x + 20, y + 10, 5);
            break;
          case T.SOFA:
            g.fillStyle(0x8a5fbf, 1);
            g.fillRect(x + 2, y + 8, TILE_SIZE - 4, 18);
            g.fillStyle(0x744fa3, 1);
            g.fillRect(x + 2, y + 4, TILE_SIZE - 4, 6); // suyanchiq
            break;
          case T.RACK:
            this.drawRack(g, x, y);
            break;
          case T.SHELF:
            g.fillStyle(0x6b4f33, 1);
            g.fillRect(x + 2, y + 4, TILE_SIZE - 4, TILE_SIZE - 8);
            for (let i = 0; i < 4; i++) {
              const bookColors = [0xc0553a, 0x4a7ab5, 0x5f9e4f, 0xd0a040];
              g.fillStyle(bookColors[i], 1);
              g.fillRect(x + 5 + i * 6, y + 8, 4, 10);
            }
            break;
          case T.PING:
            g.fillStyle(0x2e8b8b, 1);
            g.fillRect(x + 1, y + 6, TILE_SIZE - 2, 20);
            g.fillStyle(0xffffff, 1);
            g.fillRect(x + TILE_SIZE / 2 - 1, y + 6, 2, 20); // to'r chizig'i
            break;
        }
      }
    }

    // Server xonasidagi Plazma Reaktori (Energy Core)
    const rx = 21 * TILE_SIZE;
    const ry = 11 * TILE_SIZE;
    this.add.ellipse(rx, ry + 12, 44, 20, 0x0f172a).setDepth(6);
    const reactorCore = this.add.ellipse(rx, ry, 34, 46, 0x38bdf8, 0.75).setDepth(7);
    const reactorRing = this.add.ellipse(rx, ry, 44, 16, 0x818cf8, 0.9).setDepth(8);
    this.tweens.add({
      targets: reactorCore,
      alpha: 0.35,
      scaleX: 1.12,
      scaleY: 1.12,
      duration: 1200,
      yoyo: true,
      repeat: -1,
    });
    this.tweens.add({
      targets: reactorRing,
      angle: 360,
      duration: 5000,
      repeat: -1,
    });

    // DEV ZONADAGI AI Agent Terminali
    const aiX = 10 * TILE_SIZE;
    const aiY = 3 * TILE_SIZE;
    this.add.rectangle(aiX, aiY, 32, 22, 0x1e293b, 0.9).setDepth(6);
    this.add.text(aiX, aiY, "AI Agent", {
      fontSize: "9px",
      fontFamily: "Inter, sans-serif",
      fontWeight: "bold",
      color: "#38bdf8"
    }).setOrigin(0.5).setDepth(7);
  }

  drawDesk(g, x, y) {
    // Stol usti
    g.fillStyle(0x8a6d3b, 1);
    g.fillRect(x, y + 4, TILE_SIZE, TILE_SIZE - 8);
    g.fillStyle(0x74592e, 1);
    g.fillRect(x, y + 4, TILE_SIZE, 4);
    // Monitor
    g.fillStyle(0x1c1c22, 1);
    g.fillRect(x + 7, y + 8, 18, 12);
    g.fillStyle(0x3fa7d6, 1);
    g.fillRect(x + 9, y + 10, 14, 8); // ekran
    // Klaviatura
    g.fillStyle(0x2a2a30, 1);
    g.fillRect(x + 9, y + 22, 14, 4);
  }

  drawRack(g, x, y) {
    g.fillStyle(0x15171c, 1);
    g.fillRect(x + 3, y + 2, TILE_SIZE - 6, TILE_SIZE - 4);
    // Miltillovchi indikator chiroqlar
    for (let i = 0; i < 3; i++) {
      const ledX = x + 8;
      const ledY = y + 6 + i * 8;
      const led = this.add.rectangle(ledX, ledY, 3, 3, i % 2 ? 0x5fd068 : 0xe05b5b).setDepth(5);
      this.tweens.add({
        targets: led,
        alpha: 0.15,
        duration: Phaser.Math.Between(400, 900),
        yoyo: true,
        repeat: -1,
        delay: Phaser.Math.Between(0, 600),
      });
      const led2 = this.add.rectangle(ledX + 8, ledY, 3, 3, 0x3fa7d6).setDepth(5);
      this.tweens.add({
        targets: led2,
        alpha: 0.2,
        duration: Phaser.Math.Between(500, 1100),
        yoyo: true,
        repeat: -1,
        delay: Phaser.Math.Between(0, 800),
      });
    }
  }

  drawZoneLabels() {
    for (const z of ZONES) {
      this.add
        .text(z.label.c * TILE_SIZE, z.label.r * TILE_SIZE, ` ${z.name} `, {
          fontSize: "11px",
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: "800",
          color: "#fbbf24",
          backgroundColor: "#0f131edd",
          padding: { x: 6, y: 3 },
        })
        .setDepth(20);
    }
  }

  getOrCreateCharacter(agentId) {
    if (!this.characters[agentId]) {
      if (!AGENT_ORDER.includes(agentId)) AGENT_ORDER.push(agentId);
      const index = AGENT_ORDER.indexOf(agentId);
      this.characters[agentId] = new AgentCharacter(this, agentId, index);
    }
    return this.characters[agentId];
  }

  update() {
    Object.values(this.characters).forEach((c) => c.update());
  }
}

// ---------------------------------------------------------------- HUD
const AGENT_EMOJIS = {
  aziz: "💻",
  malika: "🌸",
  bek: "☕",
  nilufar: "🟢",
  timur: "⚙️",
};

function renderChips() {
  const container = document.getElementById("agentChips");
  container.innerHTML = "";
  for (const id of AGENT_ORDER) {
    const info = AGENT_INFO[id];
    if (!info) continue;
    const chip = document.createElement("button");
    chip.className = "chip" + (id === selectedAgentId ? " selected" : "");
    const color = STATUS_COLORS[info.status] || "#8a8d94";
    const emoji = AGENT_EMOJIS[id] || "👤";
    chip.innerHTML =
      `<span class="dot" style="background:${color}"></span>` +
      `<span class="chip-name">${emoji} ${info.name || id}</span>` +
      `<span class="chip-status">${STATUS_LABELS[info.status] || info.status}</span>`;
    chip.title = info.role || "";
    chip.onclick = () => {
      selectedAgentId = id;
      renderChips();
      renderPlan();
      renderQueue();
      const input = document.getElementById("taskInput");
      input.placeholder = `${info.name}ga vazifa bering...`;
      input.focus();
    };
    container.appendChild(chip);
  }
  updateKpi();
}

// KPI kartalarni real server ma'lumoti bilan yangilash
function updateKpi() {
  const agents = Object.values(AGENT_INFO);
  const total = agents.length;
  const active = agents.filter(a => a.status === "running" || a.status === "thinking").length;
  
  const kpiOnline = document.getElementById("kpi-online");
  const kpiActive = document.getElementById("kpi-active");
  const kpiDone = document.getElementById("kpi-done");
  const kpiUptime = document.getElementById("kpi-uptime");
  
  if (kpiOnline) kpiOnline.textContent = total || "0";
  if (kpiActive) kpiActive.textContent = active || "0";
  
  // Bugungi yakunlangan vazifalar — historyList'dan hisoblaymiz
  const historyList = document.getElementById("historyList");
  const today = new Date().toDateString();
  let doneToday = 0;
  if (historyList) {
    for (const li of historyList.children) {
      doneToday++;
    }
  }
  if (kpiDone) kpiDone.textContent = doneToday || "0";
  
  // Uptime: hech qaysi agent error holatida bo'lmasa 100%, aks holda hisob
  const errorCount = agents.filter(a => a.status === "error").length;
  const uptime = total > 0 ? Math.round((1 - errorCount / total) * 100) : 100;
  if (kpiUptime) kpiUptime.textContent = `${uptime}%`;
}

// Queue badge yangilash
function updateQueueBadge() {
  const allQueues = Object.values(AGENT_QUEUES);
  const total = allQueues.reduce((sum, q) => sum + (Array.isArray(q) ? q.length : 0), 0);
  const badge = document.getElementById("badge-count");
  const empty = document.getElementById("queueEmpty");
  if (badge) badge.textContent = total;
  if (empty) empty.style.display = total === 0 ? "block" : "none";
}

function renderPlan() {
  const list = document.getElementById("planList");
  const empty = document.getElementById("planEmpty");
  const plan = selectedAgentId ? (AGENT_INFO[selectedAgentId]?.plan || []) : [];
  list.innerHTML = "";
  empty.style.display = plan.length ? "none" : "block";
  for (const item of plan) {
    const li = document.createElement("li");
    li.className = `plan-${item.status || "active"}`;
    li.textContent = `${item.status === "done" ? "✓" : item.status === "error" ? "⚠" : "…"} ${item.label}`;
    list.appendChild(li);
  }
}

function renderQueue() {
  const list = document.getElementById("queueList");
  const queued = selectedAgentId ? (AGENT_QUEUES[selectedAgentId] || []) : [];
  list.innerHTML = "";
  if (queued.length > 0) {
    for (const task of queued) {
      const li = document.createElement("li");
      li.textContent = task;
      list.appendChild(li);
    }
  }
  updateQueueBadge();
}

function addHistory(entry) {
  const list = document.getElementById("historyList");
  const li = document.createElement("li");
  li.className = "history-item";
  const icon = entry.status === "error" ? "⚠" : "✓";
  // Server finished_at ISO formatida keladi — mahalliy vaqtga o'giramiz
  let timeStr = "";
  if (entry.finished_at) {
    try {
      timeStr = new Date(entry.finished_at).toLocaleTimeString("uz", { hour: "2-digit", minute: "2-digit" });
    } catch (_) { timeStr = ""; }
  }
  const agentName = entry.agent_name || entry.agent_id || "";
  li.innerHTML = `<b>${icon} ${agentName} — ${entry.task}</b><div class="history-meta">${timeStr}${timeStr ? " · " : ""}Tugallandi</div>`;
  list.prepend(li);
  while (list.children.length > 30) list.removeChild(list.lastChild);
  // KPI "Bugungi yakunlangan" raqamini yangilash
  updateKpi();
}

function appendLog(payload, prev) {
  if (prev && prev.status === payload.status && prev.current_tool === payload.current_tool) return;
  const list = document.getElementById("logList");
  const li = document.createElement("li");
  const time = new Date().toLocaleTimeString("uz", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const name = payload.name || payload.agent_id;
  const color = STATUS_COLORS[payload.status] || "#8a8d94";
  let text = STATUS_LABELS[payload.status] || payload.status;
  if (payload.status === "running" && payload.current_tool) text = `${payload.current_tool}`;
  if (payload.status === "done" && payload.last_message) text = `✓ ${payload.last_message.slice(0, 60)}`;
  if (payload.status === "error" && payload.last_message) text = `⚠ ${payload.last_message.slice(0, 60)}`;
  
  li.innerHTML = `<span class="log-time">${time}</span> <b>${name}</b> ${text}`;
  list.appendChild(li);
  while (list.children.length > 120) list.removeChild(list.firstChild);
  const panel = document.getElementById("logPanel");
  panel.scrollTop = panel.scrollHeight;
}

// ---------------------------------------------------------------- WebSocket
function connectSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  const statusEl = document.getElementById("connStatus");

  ws.onopen = () => {
    statusEl.textContent = "● jonli";
    statusEl.style.color = "#5fd068";
  };
  ws.onclose = () => {
    statusEl.textContent = "● uzildi";
    statusEl.style.color = "#e05b5b";
    setTimeout(connectSocket, 2500);
  };
  ws.onmessage = (event) => routeMessage(JSON.parse(event.data));
}

function routeMessage(msg) {
  if (msg.type === "approval_request") {
    enqueueApproval(msg);
  } else if (msg.type === "approval_resolved") {
    resolveApproval(msg);
  } else if (msg.type === "queue") {
    AGENT_QUEUES[msg.agent_id] = msg.queued || [];
    renderQueue();
  } else if (msg.type === "history") {
    addHistory(msg.entry);
  } else {
    handleStatePayload(msg);
  }
}

function handleStatePayload(payload) {
  const prev = AGENT_INFO[payload.agent_id];
  if (!AGENT_ORDER.includes(payload.agent_id)) AGENT_ORDER.push(payload.agent_id);
  AGENT_INFO[payload.agent_id] = payload;

  if (!selectedAgentId) {
    selectedAgentId = payload.agent_id;
    const input = document.getElementById("taskInput");
    if (input) input.placeholder = `${payload.name || payload.agent_id}ga vazifa bering...`;
  }
  renderChips();
  renderPlan();
  appendLog(payload, prev);

  if (officeScene) {
    const character = officeScene.getOrCreateCharacter(payload.agent_id);
    character.setName(payload.name || payload.agent_id);
    character.applyState(payload);
  }
}

// ---------------------------------------------------------------- Tasdiq oqimi
const approvalQueue = [];
let currentApproval = null;

function enqueueApproval(req) {
  const known =
    (currentApproval && currentApproval.approval_id === req.approval_id) ||
    approvalQueue.some((a) => a.approval_id === req.approval_id);
  if (known) return;
  approvalQueue.push(req);
  markAgentWaiting(req.agent_id, req.reason);
  if (!currentApproval) showNextApproval();
}

function showNextApproval() {
  currentApproval = approvalQueue.shift() || null;
  const overlay = document.getElementById("approvalOverlay");
  if (!currentApproval) {
    overlay.classList.add("hidden");
    return;
  }
  document.getElementById("modalAgent").textContent =
    `${currentApproval.agent_name || currentApproval.agent_id} so'rayapti:`;
  document.getElementById("modalReason").textContent = currentApproval.reason;
  document.getElementById("approveYes").disabled = false;
  document.getElementById("approveNo").disabled = false;
  overlay.classList.remove("hidden");
}

function resolveApproval(msg) {
  const idx = approvalQueue.findIndex((a) => a.approval_id === msg.approval_id);
  if (idx >= 0) approvalQueue.splice(idx, 1);
  const req = currentApproval && currentApproval.approval_id === msg.approval_id ? currentApproval : null;
  logApprovalOutcome(req, msg);
  if (currentApproval && currentApproval.approval_id === msg.approval_id) {
    showNextApproval();
  }
}

async function decideApproval(decision) {
  if (!currentApproval) return;
  document.getElementById("approveYes").disabled = true;
  document.getElementById("approveNo").disabled = true;
  await fetch("/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: currentApproval.approval_id, decision }),
  });
}

function markAgentWaiting(agentId, reason) {
  if (officeScene && officeScene.characters[agentId]) {
    officeScene.characters[agentId].markWaitingApproval(reason);
  }
}

function logApprovalOutcome(req, msg) {
  const list = document.getElementById("logList");
  const li = document.createElement("li");
  let text;
  if (msg.timed_out) text = `⏱ tasdiq kutish vaqti tugadi — rad etildi`;
  else if (msg.decision) text = `✅ foydalanuvchi ruxsat berdi`;
  else text = `🚫 foydalanuvchi rad etdi`;
  const name = req ? req.agent_name || req.agent_id : "";
  li.innerHTML = `<span style="color:#ffcf6b">${name ? "<b>" + name + "</b> " : ""}${text}</span>`;
  list.appendChild(li);
  if (document.getElementById("logPanel")) document.getElementById("logPanel").scrollTop = 99999;
}

// ---------------------------------------------------------------- Vazifa formasi
function setupTaskForm() {
  const input = document.getElementById("taskInput");
  const button = document.getElementById("sendBtn");

  const submit = async () => {
    const task = input.value.trim();
    if (!task || !selectedAgentId) return;
    input.value = "";
    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task, agent_id: selectedAgentId }),
      });
      const data = await res.json();
      if (data.status === "navbatga qo'shildi") {
        const list = document.getElementById("logList");
        const li = document.createElement("li");
        li.innerHTML = `<span style="color:#e8c34a">⏳ ${AGENT_INFO[selectedAgentId]?.name || selectedAgentId} hozir band — keyinroq urinib ko'ring</span>`;
        list.appendChild(li);
      }
    } catch (e) {
      console.error("Vazifa yuborishda xatolik:", e);
    }
  };

  button.addEventListener("click", submit);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
  });
}


// ---------------------------------------------------------------- Ishga tushirish
document.addEventListener("DOMContentLoaded", () => {
  setupTaskForm();
  document.getElementById("approveYes").addEventListener("click", () => decideApproval(true));
  document.getElementById("approveNo").addEventListener("click", () => decideApproval(false));

  // Boshlang'ich KPI va queue badge (agent holati WebSocket orqali kelgandan keyin yangilanadi)
  updateKpi();
  updateQueueBadge();

  // /history endpointidan real ma'lumotlar yuklanadi
  fetch("/history")
    .then((r) => r.json())
    .then((items) => {
      if (items && items.length) {
        items.reverse().forEach(addHistory);
      }
      // Bo'sh bo'lsa — hech narsa ko'rsatmaymiz (mock yo'q)
    })
    .catch(() => {
      // Tarmoq xatosi — jimgina o'tamiz, bo'sh holat ko'rsatiladi
    });
});

new Phaser.Game({
  type: Phaser.AUTO,
  parent: "game",
  backgroundColor: "#101114",
  // FIT — kichik ekranlarda xarita konteynerga sig'ib, proporsional kichrayadi
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH,
    width: OFFICE_COLS * TILE_SIZE,
    height: OFFICE_ROWS * TILE_SIZE,
  },
  scene: [OfficeScene],
});
