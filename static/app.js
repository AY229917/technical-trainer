const app = document.querySelector("#app");
const navs = document.querySelectorAll(".nav");
let view = "list";
let coin = "";
let timeframe = "1d";
let poll = null;

const GUIDE = [
  { name: "ダブルボトム", tone: "up", parts: [{ text: "近い安値が2つ。間の山を終値で上抜けたら確定。", tone: "up" }] },
  { name: "ダブルトップ", tone: "down", parts: [{ text: "近い高値が2つ。間の谷を終値で下抜けたら確定。", tone: "down" }] },
  { name: "トリプルボトム", tone: "up", parts: [{ text: "近い安値が3つ。間の山の高い方を終値で上抜けたら確定。", tone: "up" }] },
  { name: "トリプルトップ", tone: "down", parts: [{ text: "近い高値が3つ。間の谷の安い方を終値で下抜けたら確定。", tone: "down" }] },
  { name: "逆ヘッド＆ショルダー", tone: "up", parts: [{ text: "中央の谷が最も深い。ネックラインを終値で上抜けたら確定。", tone: "up" }] },
  { name: "ヘッド＆ショルダー", tone: "down", parts: [{ text: "中央の山が最も高い。下向きのネックラインなら右の谷を終値で下抜けて確定。", tone: "down" }] },
  { name: "上昇フラッグ", tone: "up", parts: [{ text: "上昇の急な動きのあと、15本未満の保ち合い。上側を終値で上抜けたら確定。", tone: "up" }] },
  { name: "下降フラッグ", tone: "down", parts: [{ text: "下降の急な動きのあと、15本未満の保ち合い。下側を終値で下抜けたら確定。", tone: "down" }] },
  { name: "上昇ペナント", tone: "up", parts: [{ text: "上昇の急な動きのあと、上下の線が収束。上側を終値で上抜けたら確定。", tone: "up" }] },
  { name: "下降ペナント", tone: "down", parts: [{ text: "下降の急な動きのあと、収束。下側を終値で下抜けたら確定。", tone: "down" }] },
  { name: "上昇三角保ち合い", tone: "", parts: [
    { text: "高値がほぼ水平で、安値が切り上がる。", tone: "" },
    { text: "上へ抜けたら上方向。", tone: "up" },
    { text: "下へ抜けたら下方向。", tone: "down" },
  ] },
  { name: "下降三角保ち合い", tone: "", parts: [
    { text: "安値がほぼ水平で、高値が切り下がる。", tone: "" },
    { text: "上へ抜けたら上方向。", tone: "up" },
    { text: "下へ抜けたら下方向。", tone: "down" },
  ] },
  { name: "上昇レクタングル", tone: "up", parts: [{ text: "上下がほぼ水平な箱。上側を終値で上抜けたら確定。", tone: "up" }] },
  { name: "下降レクタングル", tone: "down", parts: [{ text: "上下がほぼ水平な箱。下側を終値で下抜けたら確定。", tone: "down" }] },
  { name: "上昇ウェッジ", tone: "", parts: [
    { text: "上下の線がともに上向きで収束。", tone: "" },
    { text: "上抜けはその方向。", tone: "up" },
    { text: "下抜けはその方向で、こちらの方が多い。", tone: "down" },
  ] },
  { name: "下降ウェッジ", tone: "", parts: [
    { text: "上下の線がともに下向きで収束。", tone: "" },
    { text: "上抜けはその方向。", tone: "up" },
    { text: "下抜けはその方向。", tone: "down" },
  ] },
  { name: "ソーサーボトム", tone: "up", parts: [{ text: "丸い底。縁を終値で上へ抜けた形。山と谷では数えないので、図解だけ。", tone: "up" }] },
  { name: "ソーサートップ", tone: "down", parts: [{ text: "丸い天井。縁を終値で下へ抜けた形。図解だけ。", tone: "down" }] },
];

const FIELDS = [
  ["show_top", "画面に出す順位"],
  ["save_top", "保存する順位"],
  ["volume_mult", "出来高急増の倍率"],
  ["rsi_low", "RSIの下限"],
  ["rsi_high", "RSIの上限"],
  ["rci_line", "RCIの±"],
  ["stoch_low", "ストキャスティクスの下限"],
  ["stoch_high", "ストキャスティクスの上限"],
  ["adx_line", "ADXの基準"],
  ["price_pct", "価格が近いとみなす差（%）"],
  ["pivot_bars", "山と谷の左右の本数"],
  ["pole_pct", "急な動きの大きさ（%）"],
];

navs.forEach((button) => {
  button.addEventListener("click", () => {
    view = button.dataset.view;
    coin = "";
    show();
  });
});

function money(value) {
  const n = Number(value) || 0;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function when(iso) {
  if (!iso) return "未更新";
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", hour12: false });
}

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
  return data;
}

function setNav() {
  navs.forEach((button) => button.classList.toggle("on", button.dataset.view === view && !coin));
}

async function show() {
  setNav();
  if (coin) return renderDetail();
  if (view === "guide") return renderGuide();
  if (view === "settings") return renderSettings();
  return renderList();
}

async function renderList() {
  const data = await api("/api/ranking");
  const status = data.status || {};
  app.innerHTML = `
    <div class="toolbar">
      <p class="status">${escapeHtml(status.message || "")}<br><span class="muted">${when(data.recorded_at)} 時点の上位 ${data.items.length} 銘柄</span></p>
      <button class="primary" id="update" ${status.running ? "disabled" : ""}>データを更新</button>
    </div>
    <div class="list" id="list"></div>
    <div class="ad">広告枠（この版では空です）</div>`;
  const list = document.querySelector("#list");
  if (!data.items.length) {
    list.innerHTML = `<p class="empty">まだ日足がありません。更新が終わると、出来高上位の銘柄が並びます。</p>`;
  }
  data.items.forEach((item) => {
    const button = document.createElement("button");
    button.className = "card";
    button.innerHTML = `
      <div class="card-head"><span><span class="rank">${item.rank}</span><span class="coin">${escapeHtml(item.coin)}</span></span><span class="muted">${money(item.volume_24h)}</span></div>
      <div class="badges"></div>`;
    const badges = button.querySelector(".badges");
    (item.badges || []).forEach((text) => {
      const span = document.createElement("span");
      span.className = "badge";
      span.textContent = text;
      badges.appendChild(span);
    });
    if (!item.badges || !item.badges.length) {
      const span = document.createElement("span");
      span.className = "badge";
      span.textContent = "点灯・発生・確定はありません";
      badges.appendChild(span);
    }
    button.addEventListener("click", () => {
      coin = item.coin;
      timeframe = "1d";
      show();
    });
    list.appendChild(button);
  });
  document.querySelector("#update").addEventListener("click", update);
  watch(status.running);
}

function watch(running) {
  clearInterval(poll);
  if (!running) return;
  poll = setInterval(async () => {
    const status = await api("/api/status");
    const el = document.querySelector(".status");
    if (el) {
      const progress = status.total ? ` ${status.current}/${status.total}` : "";
      el.firstChild.textContent = `${status.message || ""}${progress}`;
    }
    if (!status.running) {
      clearInterval(poll);
      if (view === "list" && !coin) show();
    }
  }, 1200);
}

async function update() {
  await api("/api/update", { method: "POST" });
  show();
}

function renderGuide() {
  app.innerHTML = `<div class="guides"></div><p class="guide-note muted">16種はチャートでも線を引きます。ソーサーの2種は図解だけです。境界の反対側は目安であり、注文ではありません。</p><div class="ad">広告枠（この版では空です）</div>`;
  const root = app.querySelector(".guides");
  GUIDE.forEach((item) => {
    const card = document.createElement("article");
    card.className = "guide";
    const titleTone = item.tone ? ` class="tone-${item.tone}"` : "";
    const text = item.parts.map((part) => {
      const tone = part.tone ? ` class="tone-${part.tone}"` : "";
      return `<span${tone}>${escapeHtml(part.text)}</span>`;
    }).join("");
    card.innerHTML = `${patternFigure(item.name)}<div class="guide-copy"><h2${titleTone}>${escapeHtml(item.name)}</h2><p>${text}</p></div>`;
    const copy = card.querySelector(".guide-copy");
    copy.addEventListener("pointerenter", () => card.classList.add("mark"));
    copy.addEventListener("pointerleave", () => card.classList.remove("mark"));
    root.appendChild(card);
  });
}

let figureSeq = 0;

function patternFigure(name) {
  const spec = FIGURES[name];
  if (!spec) return "";
  const markerId = `fig-arrow-${figureSeq}`;
  figureSeq += 1;
  const bars = spec.bars.map(([x, o, h, l, c]) => ({ x, o, h, l, c }));
  const prices = bars.flatMap((bar) => [bar.h, bar.l]);
  (spec.lines || []).forEach((line) => line.forEach((point) => prices.push(point[1])));
  const low = Math.min(...prices) - 6;
  const high = Math.max(...prices) + 8;
  const X = (x) => 18 + (x / 100) * 284;
  const Y = (y) => 14 + (1 - (y - low) / (high - low)) * 100;
  const span = SPANS[name] || [8, 92];
  const bodies = bars.map((bar) => {
    const up = bar.c >= bar.o;
    const color = up ? "#3dbe8b" : "#ef6b78";
    const top = Y(Math.max(bar.o, bar.c));
    const height = Math.max(2, Math.abs(Y(bar.o) - Y(bar.c)));
    const inside = bar.x >= span[0] - 0.5 && bar.x <= span[1] + 0.5;
    return `<g class="bar${inside ? " in" : ""}"><line x1="${X(bar.x)}" y1="${Y(bar.h)}" x2="${X(bar.x)}" y2="${Y(bar.l)}" stroke="${color}" stroke-width="1.4"/><rect x="${X(bar.x) - 4}" y="${top}" width="8" height="${height}" fill="${color}"/></g>`;
  }).join("");
  const lines = (spec.lines || []).map((line) => {
    const points = line.map((point) => `${X(point[0])},${Y(point[1])}`).join(" ");
    return `<polyline points="${points}" fill="none" stroke="#e2b656" stroke-width="1.6" stroke-dasharray="4 3"/>`;
  }).join("");
  let arrow = "";
  if (spec.arrow) {
    const [x1, y1, x2, y2] = spec.arrow;
    const color = spec.arrowUp ? "#3dbe8b" : "#ef6b78";
    arrow = `<defs><marker id="${markerId}" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="${color}"/></marker></defs><line x1="${X(x1)}" y1="${Y(y1)}" x2="${X(x2)}" y2="${Y(y2)}" stroke="${color}" stroke-width="1.8" marker-end="url(#${markerId})"/>`;
  }
  const x1 = X(span[0]);
  const x2 = X(span[1]);
  const width = Math.max(8, x2 - x1);
  const band = `<g class="span"><rect x="${x1}" y="6" width="${width}" height="100" rx="4" fill="rgba(226,182,86,0.18)" stroke="#e2b656" stroke-dasharray="3 2"/><text x="${x1 + 3}" y="122" fill="#e2b656" font-size="13" font-family="Segoe UI, Hiragino Sans, Noto Sans JP, sans-serif">ここから</text><text x="${x2 - 3}" y="122" text-anchor="end" fill="#e2b656" font-size="13" font-family="Segoe UI, Hiragino Sans, Noto Sans JP, sans-serif">ここまで</text></g>`;
  return `<svg class="figure" viewBox="0 0 320 132" role="img" aria-label="${escapeHtml(name)}の参考図"><rect width="320" height="132" rx="10" fill="#121820"/>${band}${arrow}${lines}${bodies}</svg>`;
}

const SPANS = {
  "ダブルボトム": [32, 80],
  "ダブルトップ": [32, 80],
  "トリプルボトム": [16, 78],
  "トリプルトップ": [16, 78],
  "逆ヘッド＆ショルダー": [16, 76],
  "ヘッド＆ショルダー": [16, 76],
  "上昇フラッグ": [8, 82],
  "下降フラッグ": [8, 82],
  "上昇ペナント": [8, 76],
  "下降ペナント": [8, 76],
  "上昇三角保ち合い": [8, 80],
  "下降三角保ち合い": [8, 80],
  "上昇レクタングル": [18, 80],
  "下降レクタングル": [18, 80],
  "上昇ウェッジ": [8, 80],
  "下降ウェッジ": [8, 80],
  "ソーサーボトム": [8, 90],
  "ソーサートップ": [8, 90],
};

const FIGURES = {
  "ダブルボトム": { bars: [[8,64,68,58,60],[20,60,62,36,40],[32,40,44,22,26],[44,26,58,24,54],[56,54,58,36,40],[68,40,44,24,28],[80,28,70,26,66],[92,66,82,64,78]], lines: [[[32,56],[80,56]]], arrow: [74,40,90,74], arrowUp: true },
  "ダブルトップ": { bars: [[8,36,42,32,40],[20,40,64,38,60],[32,60,78,56,74],[44,74,76,42,46],[56,46,52,40,44],[68,44,76,48,72],[80,72,74,30,34],[92,34,36,18,22]], lines: [[[32,44],[80,44]]], arrow: [74,60,90,26], arrowUp: false },
  "トリプルボトム": { bars: [[6,62,66,56,58],[16,58,60,28,32],[26,32,54,30,50],[36,50,54,28,32],[46,32,56,30,52],[56,52,56,26,30],[66,30,62,28,58],[78,58,74,56,70],[90,70,84,68,80]], lines: [[[16,54],[66,54]]], arrow: [70,42,90,76], arrowUp: true },
  "トリプルトップ": { bars: [[6,38,44,34,42],[16,42,72,40,68],[26,68,72,46,50],[36,50,72,48,68],[46,68,72,46,50],[56,50,74,48,70],[66,70,72,38,42],[78,42,44,26,30],[90,30,32,16,20]], lines: [[[16,46],[66,46]]], arrow: [70,58,90,24], arrowUp: false },
  "逆ヘッド＆ショルダー": { bars: [[6,70,74,62,64],[16,64,66,40,44],[28,44,58,42,54],[40,54,56,22,26],[52,26,58,24,54],[64,54,56,42,46],[76,46,72,44,68],[88,68,86,66,82]], lines: [[[16,58],[76,56]]], arrow: [78,50,94,80], arrowUp: true },
  "ヘッド＆ショルダー": { bars: [[6,30,38,26,36],[16,36,60,34,56],[28,56,58,42,46],[40,46,78,44,74],[52,74,76,42,46],[64,46,58,40,54],[76,54,56,28,32],[88,32,34,14,18]], lines: [[[16,42],[76,44]]], arrow: [78,50,94,20], arrowUp: false },
  "上昇フラッグ": { bars: [[8,24,30,20,28],[18,28,46,26,44],[28,44,64,42,62],[38,62,78,60,74],[50,74,76,66,68],[60,68,70,60,62],[70,62,66,56,58],[82,58,84,56,80],[92,80,92,78,90]], lines: [[[48,76],[78,66]],[[48,64],[78,54]]], arrow: [80,62,96,88], arrowUp: true },
  "下降フラッグ": { bars: [[8,76,80,70,72],[18,72,74,54,56],[28,56,58,36,38],[38,38,40,22,26],[50,26,34,24,32],[60,32,40,30,38],[70,38,44,34,42],[82,42,44,20,24],[92,24,26,10,12]], lines: [[[48,24],[78,34]],[[48,36],[78,46]]], arrow: [80,38,96,14], arrowUp: false },
  "上昇ペナント": { bars: [[8,22,28,18,26],[18,26,48,24,46],[28,46,68,44,66],[40,66,74,58,62],[52,62,66,56,58],[64,58,62,54,56],[76,56,78,54,74],[88,74,90,72,86]], lines: [[[40,74],[72,60]],[[40,56],[72,54]]], arrow: [76,60,94,86], arrowUp: true },
  "下降ペナント": { bars: [[8,78,82,72,74],[18,74,76,52,54],[28,54,56,32,34],[40,34,42,26,38],[52,38,44,32,36],[64,36,42,34,40],[76,40,42,18,22],[88,22,24,10,14]], lines: [[[40,26],[72,36]],[[40,44],[72,40]]], arrow: [76,40,94,16], arrowUp: false },
  "上昇三角保ち合い": { bars: [[8,40,48,28,34],[20,34,62,32,58],[32,58,64,40,44],[44,44,63,46,60],[56,60,64,50,54],[68,54,63,56,62],[80,62,82,60,78],[92,78,90,76,86]], lines: [[[18,63],[78,63]],[[10,28],[78,56]]], arrow: [80,64,96,86], arrowUp: true },
  "下降三角保ち合い": { bars: [[8,60,72,52,66],[20,66,68,38,42],[32,42,56,36,52],[44,52,54,37,40],[56,40,48,36,44],[68,44,46,37,38],[80,38,40,18,22],[92,22,24,10,14]], lines: [[[18,37],[78,37]],[[10,72],[78,44]]], arrow: [80,36,96,14], arrowUp: false },
  "上昇レクタングル": { bars: [[8,42,50,36,46],[20,46,64,40,60],[32,60,62,40,44],[44,44,64,42,60],[56,60,63,41,46],[68,46,64,42,62],[80,62,80,60,76],[92,76,88,74,84]], lines: [[[18,64],[74,64]],[[18,40],[74,40]]], arrow: [76,58,96,84], arrowUp: true },
  "下降レクタングル": { bars: [[8,58,64,50,54],[20,54,60,36,40],[32,40,58,38,56],[44,56,60,38,42],[56,42,58,37,54],[68,54,60,38,40],[80,40,42,20,24],[92,24,26,12,16]], lines: [[[18,60],[74,60]],[[18,36],[74,36]]], arrow: [76,42,96,16], arrowUp: false },
  "上昇ウェッジ": { bars: [[8,28,36,22,32],[20,32,48,30,46],[32,46,58,44,54],[44,54,66,52,62],[56,62,72,60,68],[68,68,76,66,72],[80,72,74,48,52],[92,52,54,34,38]], lines: [[[16,36],[74,76]],[[16,22],[74,64]]], arrow: [78,60,94,36], arrowUp: false },
  "下降ウェッジ": { bars: [[8,72,78,66,68],[20,68,70,52,54],[32,54,56,42,46],[44,46,48,34,38],[56,38,40,28,32],[68,32,34,24,28],[80,28,52,26,48],[92,48,66,46,62]], lines: [[[16,64],[74,24]],[[16,78],[74,36]]], arrow: [78,40,94,64], arrowUp: true },
  "ソーサーボトム": { bars: saucerBars(true), lines: [[[8,62],[92,62]]], arrow: [78,62,96,82], arrowUp: true },
  "ソーサートップ": { bars: saucerBars(false), lines: [[[8,38],[92,38]]], arrow: [78,38,96,18], arrowUp: false },
};

function saucerBars(bottom) {
  const bars = [];
  for (let i = 0; i <= 10; i += 1) {
    const t = i / 10;
    const mid = bottom ? 62 - Math.sin(t * Math.PI) * 34 : 38 + Math.sin(t * Math.PI) * 34;
    const open = mid - 2;
    const close = mid + (i > 7 ? 6 : 2);
    bars.push([8 + i * 8.2, open, Math.max(open, close) + 3, Math.min(open, close) - 3, close]);
  }
  return bars;
}

async function renderSettings() {
  const settings = await api("/api/settings");
  app.innerHTML = `<form class="settings" id="form"><div class="grid"></div><button class="primary" type="submit">保存</button></form>`;
  const grid = app.querySelector(".grid");
  FIELDS.forEach(([key, label]) => {
    const wrap = document.createElement("label");
    wrap.textContent = label;
    const input = document.createElement("input");
    input.name = key;
    input.type = "number";
    input.step = "any";
    input.value = settings[key];
    wrap.appendChild(input);
    grid.appendChild(wrap);
  });
  app.querySelector("#form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {};
    new FormData(event.target).forEach((value, key) => {
      body[key] = Number(value);
    });
    await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
    view = "list";
    show();
  });
}

async function renderDetail() {
  app.innerHTML = `<p class="muted">読み込み中</p>`;
  const data = await api(`/api/coin?coin=${encodeURIComponent(coin)}&tf=${encodeURIComponent(timeframe)}`);
  app.innerHTML = `
    <div class="detail-head">
      <div>
        <button class="ghost" id="back">一覧へ</button>
        <h2 style="display:inline;margin-left:8px">${escapeHtml(data.coin)}</h2>
        <p class="muted">順位 ${data.rank ?? "—"} · 24時間出来高 ${money(data.volume_24h)} · 判定に使った確定足 ${escapeHtml(data.judged_on || "—")}${timeframe === "1w" ? " の週" : timeframe === "1M" ? " の月" : ""}</p>
      </div>
      <div class="tfs">
        ${["1d", "1w", "1M"].map((tf) => `<button class="nav ${tf === timeframe ? "on" : ""}" data-tf="${tf}">${tf === "1d" ? "日足" : tf === "1w" ? "週足" : "月足"}</button>`).join("")}
      </div>
    </div>
    <div class="layout">
      <section>
        <div id="price" class="chart-wrap"></div>
        <div class="chart-resize" id="price-resize" role="separator" aria-orientation="horizontal" title="ドラッグでチャートの高さを変える"></div>
        <div id="macd" class="pane"></div>
        <div id="rsi" class="pane"></div>
        <div id="rci" class="pane"></div>
        <div id="stoch" class="pane"></div>
        <div id="adx" class="pane"></div>
        <div class="ad">広告枠（この版では空です）</div>
      </section>
      <section class="signals" id="signals">
        <h2>インジケーター</h2>
        <div id="indicator-list"></div>
        <h2>オブジェクト</h2>
        <div id="object-list"></div>
      </section>
    </div>`;
  document.querySelector("#back").addEventListener("click", () => {
    coin = "";
    show();
  });
  app.querySelectorAll("[data-tf]").forEach((button) => {
    button.addEventListener("click", () => {
      timeframe = button.dataset.tf;
      renderDetail();
    });
  });
  draw(data);
  const indicators = document.querySelector("#indicator-list");
  const objects = document.querySelector("#object-list");
  data.items.forEach((item) => {
    const key = layerKey(item.name);
    const on = showLayer(key);
    const card = document.createElement("article");
    card.className = `signal${on ? "" : " is-off"}`;
    card.innerHTML = `<div class="signal-top"><strong>${escapeHtml(item.name)}</strong><span class="signal-actions"><span class="state ${escapeHtml(item.state)}">${escapeHtml(item.state)}</span><button type="button" class="switch${on ? "" : " off"}" data-layer="${escapeHtml(key)}" aria-pressed="${on ? "true" : "false"}">${on ? "オン" : "オフ"}</button></span></div><p>${escapeHtml(item.value)}　${escapeHtml(item.text)}</p>`;
    card.querySelector(".switch").addEventListener("click", () => {
      layerOn[key] = !showLayer(key);
      syncSwitches(key);
      applyVisibility();
    });
    if (key.startsWith("obj:")) {
      card.addEventListener("pointerenter", () => {
        patternHold = item.name;
        highlightPattern(item.name);
      });
      card.addEventListener("pointerleave", () => {
        patternHold = null;
        highlightPattern(null);
      });
    }
    (key.startsWith("obj:") ? objects : indicators).appendChild(card);
  });
  if (!objects.children.length) {
    objects.innerHTML = `<p class="muted empty-object">検出されたオブジェクトはありません</p>`;
  }
}

function chartOptions(height) {
  return {
    autoSize: true,
    height,
    layout: { background: { color: "#1a212c" }, textColor: "#c9d4e4" },
    grid: { vertLines: { color: "#2c3646" }, horzLines: { color: "#2c3646" } },
    rightPriceScale: { borderColor: "#2c3646" },
    timeScale: { borderColor: "#2c3646", rightOffset: 8 },
    localization: { locale: "ja-JP" },
  };
}

function cloudFill(chart, series, spanA, spanB) {
  const upper = new Map(spanA.map((point) => [point.time, point.value]));
  const lower = new Map(spanB.map((point) => [point.time, point.value]));
  const times = [...upper.keys()].filter((time) => lower.has(time)).sort((a, b) => a - b);
  const source = { visible: true, requestUpdate() {} };
  const gaps = times.slice(1).map((time, index) => time - times[index]).filter((gap) => gap > 0);
  const step = gaps.length ? gaps.slice().sort((a, b) => a - b)[Math.floor(gaps.length / 2)] : 0;
  Object.assign(source, {
    points: [],
    updateAllViews() {
      const scale = chart.timeScale();
      const next = [];
      times.forEach((time) => {
        const x = scale.timeToCoordinate(time);
        const yA = series.priceToCoordinate(upper.get(time));
        const yB = series.priceToCoordinate(lower.get(time));
        if (x == null || yA == null || yB == null) return;
        if (!source.visible) return;
        next.push({ time, x, yA, yB, bull: upper.get(time) >= lower.get(time) });
      });
      source.points = next;
    },
    attached(param) {
      source.requestUpdate = param.requestUpdate;
    },
    paneViews() {
      return [{
        zOrder: () => "bottom",
        renderer: () => ({
          draw(target) {
            const points = source.points;
            if (points.length < 2) return;
            target.useBitmapCoordinateSpace((scope) => {
              const ctx = scope.context;
              const hx = scope.horizontalPixelRatio;
              const vy = scope.verticalPixelRatio;
              const bull = "rgba(73, 168, 154, 0.28)";
              const bear = "rgba(217, 138, 98, 0.28)";
              for (let i = 0; i < points.length - 1; i += 1) {
                const left = points[i];
                const right = points[i + 1];
                if (step && right.time - left.time > step * 1.5) continue;
                paintCloud(ctx, left, right, hx, vy, left.bull ? bull : bear, right.bull ? bull : bear);
              }
            });
          },
        }),
      }];
    },
  });
  return source;
}

function paintCloud(ctx, left, right, hx, vy, leftColor, rightColor) {
  if (leftColor === rightColor) {
    fillCloud(ctx, left, right, hx, vy, leftColor);
    return;
  }
  const denom = (right.yA - left.yA) - (right.yB - left.yB);
  const ratio = denom === 0 ? 0.5 : (left.yB - left.yA) / denom;
  const cut = Math.min(1, Math.max(0, ratio));
  const mid = {
    x: left.x + (right.x - left.x) * cut,
    yA: left.yA + (right.yA - left.yA) * cut,
    yB: left.yB + (right.yB - left.yB) * cut,
  };
  fillCloud(ctx, left, mid, hx, vy, leftColor);
  fillCloud(ctx, mid, right, hx, vy, rightColor);
}

function fillCloud(ctx, left, right, hx, vy, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(left.x * hx, left.yA * vy);
  ctx.lineTo(right.x * hx, right.yA * vy);
  ctx.lineTo(right.x * hx, right.yB * vy);
  ctx.lineTo(left.x * hx, left.yB * vy);
  ctx.closePath();
  ctx.fill();
}

const layerOn = {};
let chartLayers = null;
let patternHold = null;

function patternBand(chart) {
  const source = {
    active: null,
    box: null,
    requestUpdate() {},
    attached(param) {
      source.requestUpdate = param.requestUpdate;
    },
    updateAllViews() {
      if (!source.active) {
        source.box = null;
        return;
      }
      const scale = chart.timeScale();
      const left = scale.timeToCoordinate(source.active.start);
      const right = scale.timeToCoordinate(source.active.end);
      if (left == null || right == null) {
        source.box = null;
        return;
      }
      source.box = { x1: Math.min(left, right), x2: Math.max(left, right) };
    },
    paneViews() {
      return [
        { zOrder: () => "bottom", renderer: () => ({ draw: (target) => paintBand(target, source.box, false) }) },
        { zOrder: () => "top", renderer: () => ({ draw: (target) => paintBand(target, source.box, true) }) },
      ];
    },
  };
  return source;
}

function paintBand(target, box, labels) {
  if (!box) return;
  target.useBitmapCoordinateSpace((scope) => {
    const ctx = scope.context;
    const hx = scope.horizontalPixelRatio;
    const vy = scope.verticalPixelRatio;
    const x = box.x1 * hx;
    const width = Math.max(1, (box.x2 - box.x1) * hx);
    const height = scope.bitmapSize.height * 0.78;
    if (!labels) {
      ctx.fillStyle = "rgba(226, 182, 86, 0.16)";
      ctx.fillRect(x, 0, width, height);
      ctx.strokeStyle = "#e2b656";
      ctx.lineWidth = Math.max(1, hx);
      ctx.setLineDash([5 * hx, 4 * hx]);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.moveTo(x + width, 0);
      ctx.lineTo(x + width, height);
      ctx.stroke();
      ctx.setLineDash([]);
      return;
    }
    ctx.fillStyle = "#e2b656";
    ctx.font = `${Math.round(12 * vy)}px "Segoe UI", "Hiragino Sans", sans-serif`;
    const from = "ここから";
    const to = "ここまで";
    const fromW = ctx.measureText(from).width;
    const toW = ctx.measureText(to).width;
    const y = 16 * vy;
    const tight = width < fromW + toW + 12 * hx;
    const fromX = tight ? x - fromW - 6 * hx : x + 6 * hx;
    const toX = tight ? x + width + 6 * hx : x + width - toW - 6 * hx;
    ctx.fillText(from, Math.max(4 * hx, fromX), y);
    ctx.fillText(to, toX, y);
  });
}

function highlightPattern(name) {
  if (!chartLayers || !chartLayers.band) return;
  const group = name
    ? chartLayers.patterns.find((item) => item.name === name && showLayer(item.layer))
    : null;
  const next = group ? group.name : "";
  const prev = chartLayers.band.active ? chartLayers.band.active.name : "";
  if (next === prev) return;
  chartLayers.band.active = group
    ? { name: group.name, start: group.spanStart ?? group.start, end: group.spanEnd ?? group.end }
    : null;
  chartLayers.band.requestUpdate();
  chartLayers.patterns.forEach((item) => {
    const hot = group && item.name === group.name;
    item.items.forEach((line) => {
      line.series.applyOptions({
        lineWidth: hot ? 3 : 2,
        color: hot ? "#ffe08a" : line.baseColor,
      });
    });
  });
}

function layerKey(name) {
  if (name === "移動平均乖離率") return "gap";
  if (name === "移動平均" || name.startsWith("移動平均 ")) return "ma";
  if (name === "出来高") return "volume";
  if (name === "一目均衡表") return "ichi";
  if (name === "ボリンジャーバンド") return "bb";
  if (name.startsWith("MACD")) return "macd";
  if (name === "RSI") return "rsi";
  if (name.startsWith("RCI")) return "rci";
  if (name === "ストキャスティクス") return "stoch";
  if (name.startsWith("DMI")) return "adx";
  return `obj:${name}`;
}

function showLayer(key) {
  return layerOn[key] !== false;
}

function syncSwitches(key) {
  const on = showLayer(key);
  document.querySelectorAll(".switch").forEach((button) => {
    if (button.dataset.layer !== key) return;
    button.classList.toggle("off", !on);
    button.textContent = on ? "オン" : "オフ";
    button.setAttribute("aria-pressed", on ? "true" : "false");
    button.closest(".signal").classList.toggle("is-off", !on);
  });
}

function applyVisibility() {
  if (!chartLayers) return;
  chartLayers.series.forEach((item) => {
    item.series.applyOptions({ visible: showLayer(item.layer) });
  });
  chartLayers.cloud.visible = showLayer("ichi");
  if (chartLayers.cloud.requestUpdate) chartLayers.cloud.requestUpdate();
  chartLayers.blocks.forEach((block) => {
    const hide = !showLayer(block.layer);
    block.nodes.forEach((node) => { node.hidden = hide; });
  });
  chartLayers.candles.setMarkers(chartLayers.markers.filter((marker) => showLayer(marker.layer)));
  if (chartLayers.band && chartLayers.band.active && !showLayer(`obj:${chartLayers.band.active.name}`)) {
    highlightPattern(null);
  }
  if (chartLayers.placeTags) chartLayers.placeTags();
}

function savedPriceHeight() {
  if (window.innerWidth <= 800) return null;
  const raw = localStorage.getItem("trainer-price-height");
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;
  return Math.min(1400, Math.max(320, Math.round(value)));
}

function bindPriceResize(host) {
  const handle = document.querySelector("#price-resize");
  if (!handle) return;
  const saved = savedPriceHeight();
  if (saved) host.style.height = `${saved}px`;
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    try { handle.setPointerCapture(event.pointerId); } catch (err) { /* 合成イベントでは捕捉できない */ }
    handle.classList.add("is-drag");
    const move = (ev) => {
      const next = Math.min(1400, Math.max(320, ev.clientY - host.getBoundingClientRect().top));
      host.style.height = `${Math.round(next)}px`;
    };
    const end = () => {
      handle.classList.remove("is-drag");
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
      if (window.innerWidth > 800) localStorage.setItem("trainer-price-height", String(host.clientHeight));
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  });
}

function draw(data) {
  const priceEl = document.querySelector("#price");
  bindPriceResize(priceEl);
  const price = LightweightCharts.createChart(priceEl, chartOptions(priceEl.clientHeight || 460));
  const candles = price.addCandlestickSeries({
    upColor: "#3dbe8b", downColor: "#ef6b78", borderUpColor: "#3dbe8b", borderDownColor: "#ef6b78", wickUpColor: "#3dbe8b", wickDownColor: "#ef6b78",
  });
  candles.setData(data.candles.map((bar) => ({
    time: bar.time, open: bar.open, high: bar.high, low: bar.low, close: bar.close,
  })));
  const volume = price.addHistogramSeries({
    priceScaleId: "vol",
    priceFormat: { type: "volume" },
    color: "#6e7c90",
    priceLineVisible: false,
    lastValueVisible: false,
  });
  price.priceScale("vol").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
  volume.setData(data.candles.map((bar) => ({
    time: bar.time,
    value: bar.volume,
    color: bar.close >= bar.open ? "rgba(61,190,139,0.45)" : "rgba(239,107,120,0.45)",
  })));
  const tracked = [];
  const blocks = [];
  tracked.push({ series: volume, layer: "volume" });
  const ma = maNames();
  const lineLayer = {
    sma_short: "ma", sma_mid: "ma", sma_long: "ma",
    bb_up2: "bb", bb_dn2: "bb", bb_up1: "bb", bb_dn1: "bb", bb_up3: "bb", bb_dn3: "bb",
    tenkan: "ichi", kijun: "ichi", span_a: "ichi", span_b: "ichi", chikou: "ichi",
  };
  const lines = [
    ["sma_short", ma[0], "#e2b656", 2],
    ["sma_mid", ma[1], "#8eb6de", 2],
    ["sma_long", ma[2], "#d0d7e2", 2],
    ["bb_up2", "ボリンジャー +2σ", "#9aa8bd", 1],
    ["bb_dn2", "ボリンジャー −2σ", "#9aa8bd", 1],
    ["bb_up1", "ボリンジャー +1σ", "#66758b", 1],
    ["bb_dn1", "ボリンジャー −1σ", "#66758b", 1],
    ["bb_up3", "ボリンジャー +3σ", "#465266", 1],
    ["bb_dn3", "ボリンジャー −3σ", "#465266", 1],
    ["tenkan", "転換線", "#3dbe8b", 1],
    ["kijun", "基準線", "#ef6b78", 1],
    ["span_a", "先行スパンA", "#49a89a", 1],
    ["span_b", "先行スパンB", "#d98a62", 1],
    ["chikou", "遅行スパン", "#c084fc", 1],
  ];
  const priceLines = [];
  lines.forEach(([key, name, color, width]) => {
    const item = addNamedLine(price, data.overlays[key] || [], name, { color, lineWidth: width }, lineLayer[key]);
    priceLines.push(item);
    tracked.push(item);
  });
  const cloud = cloudFill(price, candles, data.overlays.span_a || [], data.overlays.span_b || []);
  candles.attachPrimitive(cloud);
  const band = patternBand(price);
  candles.attachPrimitive(band);
  const patterns = [];
  (data.patterns || []).forEach((pattern) => {
    const color = pattern.color || (pattern.state === "確定" ? "#e2b656" : "#93a0b5");
    const group = {
      name: pattern.name,
      layer: `obj:${pattern.name}`,
      start: Infinity,
      end: -Infinity,
      spanStart: pattern.span ? pattern.span[0] : null,
      spanEnd: pattern.span ? pattern.span[1] : null,
      items: [],
    };
    (pattern.lines || []).forEach((line) => {
      if (!line.points || line.points.length < 2) return;
      line.points.forEach((point) => {
        group.start = Math.min(group.start, point.time);
        group.end = Math.max(group.end, point.time);
      });
      const lineColor = line.color || color;
      const item = addNamedLine(price, line.points, line.name || `${pattern.name}（${pattern.state}）`, {
        color: lineColor,
        lineWidth: line.width || 2,
        lineStyle: line.style == null ? 2 : line.style,
      }, group.layer);
      item.patternName = pattern.name;
      item.baseColor = lineColor;
      if (line.label) item.tag = true;
      group.items.push(item);
      priceLines.push(item);
      tracked.push(item);
    });
    if (!group.items.length) return;
    let label = null;
    group.items.forEach((item) => {
      item.points.forEach((point) => {
        const next = { time: point.time, value: point.value, series: item.series, tag: Boolean(item.tag) };
        if (!label || (next.tag && !label.tag) || (next.tag === label.tag && (point.time > label.time || (point.time === label.time && point.value < label.value)))) {
          label = next;
        }
      });
    });
    group.label = label;
    group.color = color;
    patterns.push(group);
  });
  const placeTags = mountPatternTags(price, priceEl, patterns);
  bindLineTip(price, priceEl, priceLines, true);
  const patternNames = new Set(patterns.map((group) => group.name));
  const markers = (data.markers || []).filter((marker) => !patternNames.has(marker.text)).map((marker) => ({
    time: marker.time,
    position: marker.position,
    color: "#e2b656",
    shape: "circle",
    text: marker.text,
    layer: layerKey(marker.text),
  }));

  const panes = [
    ["macd", [["macd", "MACD", "#8eb6de"], ["signal", "MACDシグナル", "#e2b656"]], "hist"],
    ["rsi", [["rsi", "RSI", "#8eb6de"]]],
    ["rci", [["rci_short", "RCI短期", "#e2b656"], ["rci_mid", "RCI中期", "#8eb6de"], ["rci_long", "RCI長期", "#d0d7e2"]]],
    ["stoch", [["stoch_k", "ストキャスティクス %K", "#e2b656"], ["stoch_d", "ストキャスティクス %D", "#8eb6de"]]],
    ["adx", [["adx", "ADX", "#e2b656"], ["plus_di", "+DI", "#3dbe8b"], ["minus_di", "−DI", "#ef6b78"]]],
  ];
  const charts = [price];
  panes.forEach(([id, seriesList, histKey]) => {
    const el = document.querySelector(`#${id}`);
    const title = document.createElement("h3");
    title.textContent = { macd: "MACD", rsi: "RSI", rci: "RCI", stoch: "ストキャスティクス", adx: "DMI / ADX" }[id];
    el.before(title);
    const chart = LightweightCharts.createChart(el, chartOptions(120));
    charts.push(chart);
    let hist = null;
    if (histKey) {
      hist = chart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
      hist.setData(data.panes[histKey] || []);
    }
    const named = seriesList.map(([key, name, color]) => {
      const item = addNamedLine(chart, data.panes[key] || [], name, { color, lineWidth: 1 }, id);
      tracked.push(item);
      return item;
    });
    if (histKey) tracked.push({ series: hist, layer: id });
    blocks.push({ layer: id, nodes: [title, el] });
    bindLineTip(chart, el, named);
  });
  let syncing = false;
  price.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    if (syncing || !range) return;
    syncing = true;
    charts.slice(1).forEach((chart) => chart.timeScale().setVisibleLogicalRange(range));
    syncing = false;
  });
  const fitted = price.timeScale().getVisibleLogicalRange();
  if (fitted && fitted.to - fitted.from > 180) {
    price.timeScale().setVisibleLogicalRange({ from: fitted.to - 180, to: fitted.to });
  }
  chartLayers = { series: tracked, cloud, blocks, candles, markers, patterns, band, placeTags };
  applyVisibility();
}

function maNames() {
  if (timeframe === "1w") return ["13本移動平均", "26本移動平均", "52本移動平均"];
  if (timeframe === "1M") return ["6本移動平均", "12本移動平均", "36本移動平均"];
  return ["5本移動平均", "25本移動平均", "75本移動平均"];
}

function addNamedLine(chart, points, name, options, layer) {
  const series = chart.addLineSeries({
    priceLineVisible: false,
    lastValueVisible: false,
    ...options,
  });
  series.setData(points);
  return { series, name, points, layer };
}

function valueOnLine(points, time) {
  if (!points || points.length < 2 || time == null) return null;
  const sorted = points.slice().sort((a, b) => a.time - b.time);
  for (let i = 1; i < sorted.length; i += 1) {
    const left = sorted[i - 1];
    const right = sorted[i];
    if (time < left.time || time > right.time) continue;
    const span = right.time - left.time;
    if (!span) return left.value;
    const ratio = (time - left.time) / span;
    return left.value + (right.value - left.value) * ratio;
  }
  return null;
}

function mountPatternTags(chart, host, groups) {
  const tags = groups.map((group) => {
    const tag = document.createElement("span");
    tag.className = "pattern-tag";
    tag.textContent = group.name;
    tag.style.color = group.color;
    tag.addEventListener("pointerenter", () => {
      patternHold = group.name;
      highlightPattern(group.name);
    });
    tag.addEventListener("pointerleave", () => {
      if (patternHold !== group.name) return;
      patternHold = null;
      highlightPattern(null);
    });
    host.appendChild(tag);
    return { tag, group };
  });
  const place = () => {
    tags.forEach(({ tag, group }) => {
      const label = group.label;
      if (!label || !showLayer(group.layer)) {
        tag.hidden = true;
        return;
      }
      const x = chart.timeScale().timeToCoordinate(label.time);
      const y = label.series.priceToCoordinate(label.value);
      if (x == null || y == null || y < 0 || y > host.clientHeight) {
        tag.hidden = true;
        return;
      }
      tag.hidden = false;
      tag.style.left = `${Math.round(x + 6)}px`;
      tag.style.top = `${Math.round(y - tag.offsetHeight / 2)}px`;
    });
  };
  chart.timeScale().subscribeVisibleLogicalRangeChange(place);
  host.addEventListener("wheel", () => requestAnimationFrame(place), { passive: true });
  host.addEventListener("pointerup", () => requestAnimationFrame(place));
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(place).observe(host);
  requestAnimationFrame(place);
  return place;
}

function lineDistance(chart, item, point, time, padX, padY) {
  if (item.layer && !showLayer(item.layer)) return null;
  if (item.points.length <= 8) {
    const xs = item.points
      .map((row) => chart.timeScale().timeToCoordinate(row.time))
      .filter((x) => x != null);
    if (!xs.length || point.x < Math.min(...xs) - 12 || point.x > Math.max(...xs) + padX) return null;
  }
  const row = item.points.find((entry) => entry.time === time);
  let value = row ? row.value : valueOnLine(item.points, time);
  if (value == null && item.patternName && item.points.length) {
    const sorted = item.points.slice().sort((a, b) => a.time - b.time);
    const right = sorted[sorted.length - 1];
    if (time == null || time > right.time) value = right.value;
    else if (time < sorted[0].time) value = sorted[0].value;
  }
  if (value == null) return null;
  const y = item.series.priceToCoordinate(value);
  if (y == null) return null;
  const dist = Math.abs(y - point.y);
  if (dist > padY) return null;
  return { name: item.name, patternName: item.patternName || "", dist, y };
}

function bindLineTip(chart, host, named, trackPatterns) {
  const tip = document.createElement("div");
  tip.className = "line-tip";
  tip.hidden = true;
  host.appendChild(tip);
  chart.subscribeCrosshairMove((param) => {
    const point = param.point;
    if (!point || point.x < 0 || point.y < 0) {
      tip.hidden = true;
      if (trackPatterns && !patternHold) highlightPattern(null);
      return;
    }
    let best = null;
    let patternHit = null;
    named.forEach((item) => {
      const hit = lineDistance(chart, item, point, param.time, item.patternName ? 120 : 8, item.patternName ? 36 : 10);
      if (!hit) return;
      if (!best || hit.dist < best.dist) best = hit;
      if (item.patternName && (!patternHit || hit.dist < patternHit.dist)) patternHit = hit;
    });
    if (trackPatterns && !patternHold) highlightPattern(patternHit ? patternHit.patternName : null);
    const shown = patternHit && (!best || patternHit.dist <= best.dist + 6) ? patternHit : best;
    if (!shown) {
      tip.hidden = true;
      return;
    }
    tip.hidden = false;
    tip.textContent = shown.name;
    const left = Math.min(Math.max(8, point.x + 14), host.clientWidth - tip.offsetWidth - 8);
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(6, shown.y - 26)}px`;
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

show();
