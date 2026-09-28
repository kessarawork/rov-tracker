/* RoV Team Tracker — front-end
   อ่าน data/stats.json ที่สร้างจาก update.py แล้ว render เป็นแดชบอร์ด */

let D = null;
let currentTab = 'overview';

const el = document.getElementById('app');
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const cap = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
const pct = v => (v === null || v === undefined) ? '–' : v + '%';
const signed = v => (v > 0 ? '+' : '') + v;
const cls = v => v > 0 ? 'pos' : (v < 0 ? 'neg' : '');

/* ---------- small builders ---------- */
function card(title, hint, body, wide) {
  return `<section class="card${wide ? ' wide' : ''}">
    <h2>${title}</h2>${hint ? `<p class="hint">${hint}</p>` : ''}${body}</section>`;
}
function kpi(label, value, comment) {
  return `<div class="kpi"><span class="l">${label}</span>
    <span class="n">${value}</span>${comment ? `<div class="c">${comment}</div>` : ''}</div>`;
}
/** bar: value 0-100, ref = เส้นอ้างอิง (ค่าเฉลี่ยลีก) */
function bar(label, value, right, opts = {}) {
  const v = Math.max(0, Math.min(100, value || 0));
  let tone = opts.tone;
  if (!tone && opts.ref != null) tone = value >= opts.ref ? 'good' : 'bad';
  return `<div class="bar">
    <span class="lbl" title="${esc(label)}">${esc(label)}</span>
    <span class="track"><span class="fill ${tone || ''}" style="width:${v}%"></span>
      ${opts.ref != null ? `<span class="ref" style="left:${Math.min(99, opts.ref)}%" title="ค่าเฉลี่ยลีก ${opts.ref}%"></span>` : ''}
    </span>
    <span class="val">${right}</span></div>`;
}
function table(headers, rows) {
  return `<table><thead><tr>${headers.map(h =>
    `<th class="${h.r ? 'r' : ''}">${h.t}</th>`).join('')}</tr></thead>
    <tbody>${rows.join('')}</tbody></table>`;
}

/* ---------- tabs ---------- */
const TABS = {

  /* ======================= ภาพรวม ======================= */
  overview() {
    const me = D.standings.find(r => r.team === D.meta.team);
    const o = D.odds;
    const slots = D.meta.playoff_slots;

    const zone = r => r.rank <= slots ? 'up' : (r.rank <= slots + 2 ? 'mid' : 'out');
    const rows = D.standings.map(r => `<tr class="${r.team === D.meta.team ? 'me' : ''}">
      <td><span class="zone ${zone(r)}"></span>${r.rank}</td>
      <td>${esc(r.team)}</td>
      <td class="r">${r.w}–${r.l}</td>
      <td class="r">${r.gw}–${r.gl}</td>
      <td class="r ${cls(r.diff)}">${signed(r.diff)}</td>
      <td class="r">${r.remaining}</td>
      <td class="r muted">${r.max_points}</td></tr>`);

    const place = Object.entries(o.placement)
      .filter(([, v]) => v >= 0.5)
      .sort((a, b) => b[1] - a[1]);

    const mySchedule = D.schedule.filter(s => s.involves_team);

    return `
    <div class="grid">
      ${card('โอกาสเข้ารอบ', `จำลอง ${o.sims.toLocaleString()} รอบจากฟอร์มปัจจุบัน`, `
        <div class="stat"><span class="v">${o.top4}%</span><span class="u">เข้าท็อป ${slots}</span></div>
        <div class="kpis" style="margin-top:14px">
          ${kpi('ชนะที่เหลือครบ', o.win_out + '%', `${mySchedule.length} นัด`)}
          ${kpi('เข้ารอบถ้าชนะครบ', o.top4_if_win_out + '%', 'ต้องรอผลทีมอื่นด้วย')}
        </div>
        ${o.top4 < 1 ? `<div class="verdict">โอกาสเข้ารอบต่ำกว่า 1% แล้ว — เป้าที่วัดผลได้จริงตอนนี้คือ
          <b>${esc(o.goal_label)}</b> และการปิดฤดูกาลให้ดีที่สุด</div>` : ''}`)}

      ${card('อันดับที่น่าจะจบ', 'กระจายตามผลจำลอง', `<div class="bars">
        ${place.map(([rank, v]) => bar('อันดับ ' + rank, v, v + '%',
          { tone: +rank <= slots ? 'good' : 'info' })).join('')}</div>`)}

      ${card('สถานะทีม', `${D.meta.played} จาก ${D.meta.total} แมตช์ในลีกแข่งจบแล้ว`, `
        <div class="kpis">
          ${kpi('อันดับ', '#' + me.rank, me.w + '–' + me.l)}
          ${kpi('ผลต่างเกม', signed(me.diff), me.gw + '–' + me.gl)}
          ${kpi('เหลือ', me.remaining + ' นัด', 'เพดาน ' + me.max_points + ' แต้ม')}
          ${kpi('ค่าพลัง', signed(D.ratings[D.meta.team]),
            'อันดับ ' + (Object.values(D.ratings).filter(v => v > D.ratings[D.meta.team]).length + 1) + ' ของลีก')}
        </div>`)}
    </div>

    ${card('ตารางคะแนน', `แถบสีเขียว = โซนเข้ารอบ (${slots} ทีม)`, table(
      [{ t: '#' }, { t: 'ทีม' }, { t: 'แมตช์', r: 1 }, { t: 'เกม', r: 1 },
       { t: 'Diff', r: 1 }, { t: 'เหลือ', r: 1 }, { t: 'เพดาน', r: 1 }], rows), true)}

    <div class="grid">
      ${card('โปรแกรมที่เหลือของเรา', 'เวลาไทย', `<div class="flowlist">
        ${mySchedule.map(s => {
          const opp = s.a === D.meta.team ? s.b : s.a;
          return `<div class="flowrow"><span>${esc(opp)}</span>
            <span class="muted small">${esc(s.date.replace(' - ', ' • '))}</span><span></span></div>`;
        }).join('') || '<p class="muted small">ไม่มีแมตช์เหลือแล้ว</p>'}</div>`)}

      ${card('นัดที่ต้องลุ้น (เราไม่ได้ลงเล่น)', `ผลกระทบต่อเป้า "${esc(o.goal_label)}"`, `<div class="flowlist">
        ${o.swing.slice(0, 7).map(s => `<div class="flowrow">
          <span class="small">${esc(s.match)}</span>
          <span class="tag w">เชียร์ ${esc(s.root_for)}</span>
          <span class="val small num">${s.gap >= 0.1 ? '±' + s.gap + '%' : '~0'}</span></div>`).join('')}
        </div><p class="legend">ตัวเลขคือส่วนต่างของโอกาสระหว่างสองผลลัพธ์ ยิ่งสูงยิ่งสำคัญ</p>`)}

      ${card('โอกาสจบเหนือแต่ละทีม', 'จากผลจำลองทั้งฤดูกาล', `<div class="bars">
        ${o.finish_above.map(f => bar(f.team, f.pct, f.pct + '%',
          { tone: f.pct >= 50 ? 'good' : 'bad' })).join('')}</div>`)}
    </div>

    ${card('ผลแข่งล่าสุดของลีก', '', table(
      [{ t: 'วันที่' }, { t: 'คู่' }, { t: 'สกอร์', r: 1 }],
      D.recent.slice().reverse().map(r => `<tr class="${[r.a, r.b].includes(D.meta.team) ? 'me' : ''}">
        <td class="muted small">${esc(r.date)}</td>
        <td>${esc(r.a)} <span class="muted">vs</span> ${esc(r.b)}</td>
        <td class="r">${r.score}</td></tr>`)), true)}`;
  },

  /* ======================= วินิจฉัย ======================= */
  diagnosis() {
    const d = D.diagnostics;
    const g1 = d.by_game_no[0] || {};
    const long = d.by_length[d.by_length.length - 1] || {};

    return `
    <div class="grid">
      ${card('จุดรั่ว 4 อย่างที่วัดได้', 'เทียบกับค่าเฉลี่ยลีก 50%', `<div class="kpis">
        ${kpi('ชนะเกมแรกของซีรีส์', pct(g1.wr), `${g1.w}–${g1.n - g1.w} • ลีก ${pct(g1.league_wr)}`)}
        ${kpi('ปิดซีรีส์เมื่อมีโอกาส', pct(d.closeout.wr), `${d.closeout.w} จาก ${d.closeout.n} ครั้ง`)}
        ${kpi('เกมยาวเกิน 20 นาที', pct(long.wr), `${long.w}–${long.n - long.w}`)}
        ${kpi('เจอ 5 ทีมบน', pct(d.tiers.top.wr), `แมตช์ ${d.tiers.top.mw}–${d.tiers.top.ml}`)}
      </div>
      <div class="verdict">ถ้าจุดเหล่านี้กองอยู่ที่ <b>เกมแรก + การปิดเกม</b> แปลว่าปัญหาอยู่ชั้น
        การเตรียมตัวก่อนเกมและการตัดสินใจร่วมกัน ไม่ใช่ชั้นฝีมือรายคน</div>`, true)}
    </div>

    <div class="grid">
      ${card('อัตราชนะตามลำดับเกมในซีรีส์', 'เส้นขาว = ค่าเฉลี่ยลีก', `<div class="bars">
        ${d.by_game_no.map(r => bar('เกมที่ ' + r.game, r.wr,
          `${r.w}–${r.n - r.w}`, { ref: r.league_wr })).join('')}</div>
        <p class="legend">เกมแรกต่ำแต่เกมสองสูง = ทีมแก้ทางเก่ง แต่เข้าเกมโดยไม่มีแผนเปิดที่คม</p>`)}

      ${card('อัตราชนะตามความยาวเกม', 'บอกว่าทีมนี้ชนะในหน้าต่างเวลาไหน', `<div class="bars">
        ${d.by_length.map(r => bar(r.label, r.wr, r.n ? `${r.w}–${r.n - r.w}` : '–',
          { ref: r.league_wr })).join('')}</div>
        <p class="legend">หน้าต่างที่ชนะสูงสุดคือแผนเกมที่ควรเล็ง ส่วนช่วงที่ตกคือช่วงที่ต้องเลี่ยง</p>`)}

      ${card('สถานการณ์กดดัน', '', `<div class="kpis">
        ${kpi('เล่นตอนนำอยู่', pct(d.leading.wr), `${d.leading.w}/${d.leading.n} เกม`)}
        ${kpi('เล่นตอนตามหลัง', pct(d.trailing.wr), `${d.trailing.w}/${d.trailing.n} เกม`)}
        ${kpi('เกมตัดสิน (2–2)', `${d.deciders.w}/${d.deciders.n}`, 'เกมที่ 5')}
        ${kpi('ฝั่งน้ำเงิน / แดง', `${pct(d.sides.blue.wr)} / ${pct(d.sides.red.wr)}`,
          `ลีก ${pct(d.sides.blue.league_wr)} / ${pct(d.sides.red.league_wr)}`)}
      </div>
      <p class="legend">ถ้า "ตามหลัง" ใกล้ 50% แปลว่าใจสู้และการตีตื้นไม่ใช่ปัญหา</p>`)}

      ${card('เจอทีมบนกับทีมล่าง', `ทีมบน = ${d.tiers.top_teams.join(', ')}`, `<div class="bars">
        ${bar('เจอ 5 ทีมบน', d.tiers.top.wr, `${d.tiers.top.gw}–${d.tiers.top.gl}`, { tone: 'bad' })}
        ${bar('เจอทีมท้ายตาราง', d.tiers.bottom.wr, `${d.tiers.bottom.gw}–${d.tiers.bottom.gl}`, { tone: 'good' })}
        </div><p class="legend">ช่องว่างยิ่งกว้าง ยิ่งบอกว่าเป็นกำแพงเรื่องระดับ ไม่ใช่ความไม่สม่ำเสมอ</p>`)}
    </div>

    ${card('ผลทุกแมตช์แบบเกมต่อเกม', 'W = ชนะเกมนั้น', `<div class="flowlist">
      ${d.series.map(s => `<div class="flowrow">
        <span>${esc(s.opponent)} <span class="muted small">${esc(s.date)}</span></span>
        <span class="flow">${s.flow.split('').map(c =>
          `<span class="g ${c.toLowerCase()}">${c}</span>`).join('')}</span>
        <span class="tag ${s.won ? 'w' : 'l'}">${s.score}</span></div>`).join('')}
      </div>`, true)}

    ${D.mvps.length ? card('MVP รายเกม (เฉพาะเกมที่ทีมชนะ)', 'ดูว่าภาระกระจายหรือกระจุก', `<div class="chips">
      ${D.mvps.map(m => `<span class="chip">${esc(m.player)} <b>${m.n}</b></span>`).join('')}</div>`, true) : ''}`;
  },

  /* ======================= ดราฟท์ ======================= */
  draft() {
    const h = D.heroes;
    const good = h.pool.filter(p => p.n >= 4 && p.wr >= 60);
    const bad = h.pool.filter(p => p.n >= 4 && p.wr <= 40);
    const sum = arr => arr.reduce((a, p) => ({ n: a.n + p.n, w: a.w + p.w }), { n: 0, w: 0 });
    const G = sum(good), B = sum(bad);

    return `
    <div class="grid">
      ${card('พูลที่เวิร์ก vs พูลที่พัง', 'นับเฉพาะฮีโร่ที่ลงเล่นตั้งแต่ 4 เกมขึ้นไป', `
        <div class="kpis">
          ${kpi('พูลที่เวิร์ก', G.n ? Math.round(G.w / G.n * 100) + '%' : '–', `${G.w} จาก ${G.n} เกม`)}
          ${kpi('พูลที่พัง', B.n ? Math.round(B.w / B.n * 100) + '%' : '–', `${B.w} จาก ${B.n} เกม`)}
        </div>
        <div class="verdict">ถ้าช่องว่างสองก้อนนี้กว้างมาก แปลว่ามีแต้มฟรีรออยู่แค่ <b>เลิกดราฟท์จากพูลล่าง</b></div>`)}

      ${card('ฮีโร่ที่เล่นแล้วดีกว่าค่าเฉลี่ยลีกมากที่สุด', 'edge = ส่วนต่างจากลีก', `<div class="bars">
        ${h.pool.slice().sort((a, b) => b.edge - a.edge).slice(0, 8).map(p =>
          bar(cap(p.hero), p.wr, `${p.wr}% (${signed(p.edge)})`, { ref: p.league_wr })).join('')}
        </div><p class="legend">เส้นขาวคืออัตราชนะของฮีโร่นั้นทั้งลีก</p>`)}
    </div>

    <div class="grid">
      ${card('ทุกตัวที่ทีมใช้', 'เรียงจากดีไปแย่', table(
        [{ t: 'ฮีโร่' }, { t: 'เกม', r: 1 }, { t: 'W–L', r: 1 }, { t: 'ทีม', r: 1 }, { t: 'ลีก', r: 1 }, { t: 'ต่าง', r: 1 }],
        h.pool.map(p => `<tr><td>${cap(p.hero)}</td><td class="r">${p.n}</td>
          <td class="r">${p.w}–${p.n - p.w}</td><td class="r">${p.wr}%</td>
          <td class="r muted">${pct(p.league_wr)}</td>
          <td class="r ${cls(p.edge)}">${signed(p.edge)}</td></tr>`)), true)}
    </div>

    <div class="grid">
      ${card('ฮีโร่ที่ปล่อยแล้วโดนลงโทษ', 'คู่แข่งหยิบไปใช้กับเราแล้วชนะ', table(
        [{ t: 'ฮีโร่' }, { t: 'เกม', r: 1 }, { t: 'เขาชนะ', r: 1 }],
        h.punished.map(p => `<tr><td>${cap(p.hero)}</td><td class="r">${p.n}</td>
          <td class="r neg">${p.wr}%</td></tr>`)))}

      ${card('คู่แข่งแบนใส่เราเกินค่าเฉลี่ยลีก', 'gap สูง = ถูกเล็งจริง ไม่ใช่แบนตามเมต้า', table(
        [{ t: 'ฮีโร่' }, { t: 'ใส่เรา', r: 1 }, { t: 'ลีก', r: 1 }, { t: 'gap', r: 1 }],
        h.targeted.map(p => `<tr><td>${cap(p.hero)}</td><td class="r">${p.rate}%</td>
          <td class="r muted">${p.league_rate}%</td>
          <td class="r ${cls(p.gap)}">${signed(p.gap)}</td></tr>`)))}

      ${card('ของว่างในลีกที่ทีมยังไม่ใช้', 'ชนะสูงแต่ถูกแบนน้อย', table(
        [{ t: 'ฮีโร่' }, { t: 'ลีกชนะ', r: 1 }, { t: 'presence', r: 1 }, { t: 'เราใช้', r: 1 }],
        h.untapped.map(p => `<tr><td>${cap(p.hero)}</td>
          <td class="r pos">${p.league_wr}%</td><td class="r muted">${p.presence}%</td>
          <td class="r ${p.team_n === 0 ? 'neg' : ''}">${p.team_n}</td></tr>`)))}

      ${card('ตัวที่ทีมแบนบ่อยสุด', 'เทียบกับลิสต์ด้านซ้ายว่าแบนตรงจุดไหม', `<div class="chips">
        ${h.team_bans.map(b => `<span class="chip">${cap(b.hero)} <b>${b.n}</b></span>`).join('')}</div>`)}
    </div>`;
  },

  /* ======================= จังหวะเกม ======================= */
  tempo() {
    const t = D.tempo, h = D.heroes;
    const label = { faster: 'คอมเราเร็วกว่าเขา', even: 'จังหวะใกล้กัน', slower: 'คอมเราช้ากว่าเขา' };

    return `
    ${card('แนวคิด', '', `<p class="small muted" style="margin:0">
      ฮีโร่แต่ละตัวมี "จังหวะ" ของมัน วัดจากความยาวเฉลี่ยของเกมที่มันถูกใช้ เอาค่าของ 5 ตัวมาเฉลี่ยจะได้จังหวะของคอมนั้น
      แล้วเทียบกับคอมของคู่แข่งในเกมเดียวกัน ตัวเลขนี้บอกว่า <strong>ทีมถนัดเล่นเกมจังหวะไหน</strong>
      และเป็นเหตุผลที่ควรใช้ตัดสินใจแบน มากกว่าการดูว่าฮีโร่ตัวไหนคู่แข่งชนะเยอะ</p>`, true)}

    <div class="grid">
      ${card('ผลของทีมตามจังหวะคอม', 'เส้นขาว = ค่าเฉลี่ยของทั้งลีกในสถานการณ์เดียวกัน', `<div class="bars">
        ${['faster', 'even', 'slower'].map(k => bar(label[k], t.team[k].wr,
          `${t.team[k].w}–${t.team[k].n - t.team[k].w}`, { ref: t.league[k].wr })).join('')}</div>
        <div class="verdict">ถ้าช่อง "คอมเราช้ากว่า" ต่ำกว่าลีกชัดเจน แปลว่า
          <b>ทีมดราฟท์คอมที่ต้องการเวลา แต่ยังไม่มีมาโครรองรับ</b> — ทางแก้เร็วสุดคือเลิกดราฟท์แนวนั้น</div>`)}

      ${card('ทีมไหนเล่นคอมช้าได้จริง', 'เทียบกันทั้งลีก', `<div class="bars">
        ${t.slow_comp_by_team.map(r => bar(r.team, r.wr, `${r.w}–${r.n - r.w}`,
          { tone: r.team === D.meta.team ? 'bad' : 'info' })).join('')}</div>
        <p class="legend">คอมช้าไม่ใช่คอมแพ้ — ทีมที่ทำได้ดีในช่องนี้คือทีมที่เล่นเกมยาวเป็น</p>`)}
    </div>

    <div class="grid">
      ${card('ฮีโร่สายเกมเร็ว', 'ยิ่งเกมสั้นยิ่งชนะ — ถ้าคอมเราต้องการเวลา พวกนี้คือตัวที่ต้องแบน', table(
        [{ t: 'ฮีโร่' }, { t: '<16 นาที', r: 1 }, { t: '>16 นาที', r: 1 }, { t: 'ต่าง', r: 1 }],
        h.fast_heroes.map(f => `<tr><td>${cap(f.hero)}</td>
          <td class="r pos">${f.short_wr}%</td><td class="r">${f.long_wr}%</td>
          <td class="r">${signed(f.swing)}</td></tr>`)))}

      ${card('ฮีโร่สายเกมยาว', 'ต้องรอสเกล — หยิบได้เมื่อมั่นใจว่าจะรอดถึงนาทีนั้น', table(
        [{ t: 'ฮีโร่' }, { t: '<16 นาที', r: 1 }, { t: '>16 นาที', r: 1 }, { t: 'ต่าง', r: 1 }],
        h.slow_heroes.map(f => `<tr><td>${cap(f.hero)}</td>
          <td class="r">${f.short_wr}%</td><td class="r pos">${f.long_wr}%</td>
          <td class="r">${signed(f.swing)}</td></tr>`)))}
    </div>

    ${card('รายเกมของทีม', 'ค่าจังหวะคอมของเราเทียบของเขา และเกมนั้นยาวจริงเท่าไหร่', table(
      [{ t: 'คู่แข่ง' }, { t: 'คอมเรา', r: 1 }, { t: 'คอมเขา', r: 1 }, { t: 'แบบ' }, { t: 'นาที', r: 1 }, { t: 'ผล', r: 1 }],
      t.games.map(g => `<tr><td>${esc(g.opponent)}</td>
        <td class="r">${g.ours}</td><td class="r">${g.theirs}</td>
        <td class="small muted">${label[g.kind]}</td>
        <td class="r">${g.minutes ?? '–'}</td>
        <td class="r"><span class="tag ${g.won ? 'w' : 'l'}">${g.won ? 'ชนะ' : 'แพ้'}</span></td></tr>`)), true)}`;
  },

  /* ======================= เมต้า ======================= */
  meta() {
    if (!D.meta_shift) return card('ไม่มีข้อมูลเปรียบเทียบ', '', '<p class="muted small">ยังไม่มีข้อมูลสปลิตก่อนหน้าสำหรับเทียบเมต้า</p>', true);
    const m = D.meta_shift, a = m.adaptation;

    return `
    <div class="grid">
      ${card('ทีมตามเมต้าใหม่ทันไหม', `อัตราชนะบนฮีโร่ที่ presence พุ่งขึ้นจาก ${m.prev_label} มา ${m.cur_label}`, `
        <div class="bars">
          ${bar('ทีมของเรา', a.team_wr, `${a.team_wr}% (${a.team_n} ครั้ง)`, { ref: a.league_wr })}
          ${bar('ทีมอื่นทั้งลีก', a.league_wr, `${a.league_wr}% (${a.league_n} ครั้ง)`, { tone: 'info' })}
        </div>
        <div class="verdict">ช่องว่างตรงนี้คือ <b>ความเร็วในการปรับตัวเข้าแพตช์</b> ซึ่งเป็นเรื่องกระบวนการซ้อม
          ไม่ใช่ฝีมือ — ถ้าต่ำกว่าลีกเกิน 5 จุด แปลว่าต้องรื้อวิธีเตรียมพูลฮีโร่</div>`, true)}
    </div>

    <div class="grid">
      ${card('ตัวที่มาแรงในสปลิตนี้', 'presence = สัดส่วนเกมที่ถูกพิกหรือแบน', table(
        [{ t: 'ฮีโร่' }, { t: m.prev_label, r: 1 }, { t: m.cur_label, r: 1 }, { t: 'ทีมใช้', r: 1 }],
        m.risers.map(r => `<tr><td>${cap(r.hero)}</td>
          <td class="r muted">${r.prev}%</td><td class="r pos">${r.cur}%</td>
          <td class="r ${r.team_cur === 0 ? 'neg' : ''}">${r.team_cur} เกม</td></tr>`)))}

      ${card('ตัวที่ร่วงจากเมต้า', '', table(
        [{ t: 'ฮีโร่' }, { t: m.prev_label, r: 1 }, { t: m.cur_label, r: 1 }],
        m.fallers.map(r => `<tr><td>${cap(r.hero)}</td>
          <td class="r">${r.prev}%</td><td class="r neg">${r.cur}%</td></tr>`)))}

      ${card('ของถนัดเดิมที่หายไป', `ตัวที่ทีมใช้บ่อยใน ${m.prev_label} แต่แทบไม่ได้ใช้แล้ว`, table(
        [{ t: 'ฮีโร่' }, { t: m.prev_label, r: 1 }, { t: m.cur_label, r: 1 }],
        m.lost_tools.map(r => `<tr><td>${cap(r.hero)}</td>
          <td class="r">${r.prev} เกม</td><td class="r neg">${r.cur} เกม</td></tr>`)))}
    </div>`;
  },

  /* ======================= คู่ต่อไป ======================= */
  prep() {
    if (!D.prep.length) return card('จบฤดูกาลแล้ว', '', '<p class="muted small">ไม่มีแมตช์เหลือ</p>', true);
    return D.prep.map(p => card(
      `${esc(p.opponent)} <span class="muted small" style="font-weight:400">${esc(p.date.replace(' - ', ' • '))}</span>`,
      p.head_to_head.length
        ? 'เจอกันมาแล้ว: ' + p.head_to_head.map(h =>
            `${h.date} ${h.won ? 'ชนะ' : 'แพ้'} ${h.score}`).join(' | ')
        : 'ยังไม่เคยเจอกันในสปลิตนี้',
      `<p class="small muted" style="margin:0 0 8px">ตัวที่เขาเล่นแล้วแรงที่สุด (ตั้งแต่ 4 เกมขึ้นไป) — ใช้เป็นลิสต์ตั้งต้นในการแบน แล้วค่อยกรองด้วยว่าตัวไหนตีคอมที่เราจะเล่น</p>
       <div class="chips">${p.threats.map(t =>
         `<span class="chip ${t.wr >= 70 ? 'bad' : ''}">${cap(t.hero)} <b>${t.wr}%</b>
          <span class="muted small">${t.n} เกม</span></span>`).join('')}</div>`, true)).join('');
  },
};

/* ---------- boot ---------- */
function render() {
  el.innerHTML = TABS[currentTab]();
  window.scrollTo({ top: 0, behavior: 'instant' });
}

document.getElementById('tabs').addEventListener('click', e => {
  const btn = e.target.closest('button[data-tab]');
  if (!btn) return;
  currentTab = btn.dataset.tab;
  [...document.querySelectorAll('#tabs button')].forEach(b =>
    b.classList.toggle('active', b === btn));
  render();
});

/** ถ้าเป็นไฟล์ standalone ข้อมูลจะถูกฝังมาใน window.__STATS__ แล้ว ไม่ต้อง fetch */
const source = window.__STATS__
  ? Promise.resolve(window.__STATS__)
  : fetch('data/stats.json', { cache: 'no-store' })
      .then(r => { if (!r.ok) throw new Error('โหลด data/stats.json ไม่ได้ (' + r.status + ')'); return r.json(); });

source
  .then(data => {
    D = data;
    const me = D.standings.find(r => r.team === D.meta.team);
    document.title = `${D.meta.team} Tracker — ${D.meta.tournament}`;
    document.getElementById('teamName').textContent = D.meta.team;
    document.getElementById('subtitle').textContent =
      `RoV Pro League ${D.meta.tournament} • แข่งไปแล้ว ${D.meta.played}/${D.meta.total} แมตช์ของลีก`;
    document.getElementById('headline').innerHTML = `
      <span class="pill">อันดับ <b>#${me.rank}</b></span>
      <span class="pill">สถิติ <b>${me.w}–${me.l}</b></span>
      <span class="pill">Diff <b>${signed(me.diff)}</b></span>
      <span class="pill">เข้ารอบ <b>${D.odds.top4}%</b></span>`;
    document.getElementById('srcLink').href = D.meta.source_url;
    document.getElementById('updatedAt').textContent =
      'อัปเดตข้อมูลล่าสุด: ' + new Date(D.meta.updated_at).toLocaleString('th-TH');
    render();
  })
  .catch(err => {
    el.innerHTML = `<div class="card"><h2>โหลดข้อมูลไม่สำเร็จ</h2>
      <p class="hint">${esc(err.message)}</p>
      <p class="small">ให้รัน <code>python3 update.py</code> เพื่อสร้างไฟล์ data/stats.json ก่อน
      แล้วเปิดเว็บผ่าน <code>python3 -m http.server 8000</code> (เปิดไฟล์ตรง ๆ ด้วย file:// จะติด CORS)</p></div>`;
  });
