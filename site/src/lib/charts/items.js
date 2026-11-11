// 업그레이드 항목 한 건의 DOM. 서버 쪽 UpgradeItem.astro와 같은 마크업을 만든다(탐색기 더 보기, 팀 페이지 대회 고르기).
// 영어 원문은 번역하거나 고치지 않고 lang="en"으로 그대로 넣는다. 모든 글자는 textContent로 넣는다.
import { badge, catGlyph, el, icon } from "./core.js";

/** 설명이 이 글자 수를 넘으면 세 줄에서 줄이고 "전체 보기" 단추를 단다 */
export const CLAMP_CHARS = 260;

function h(tag, cls, text, attrs) {
  const n = el(tag, cls, text);
  if (attrs) for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

/**
 * item: upgrades.json의 항목(UpgradeItem). labels: labels.json(component_areas, reason_categories).
 * showTeam: 어디 칸에 팀 이름을 적는다(탐색기, 홈). 팀 페이지는 false.
 */
export function upgradeItemNode(item, labels, { showTeam = true } = {}) {
  const a = h("article", "item");
  const w = h("div", "item-where");
  w.append(h("b", null, `${item.season} ${item.round}라운드 ${item.event_short_ko}`), h("span", null, `${showTeam ? `${item.team} · ` : ""}항목 ${item.no}`));
  const c = h("div", "item-comp");
  c.append(h("b", null, item.component, { lang: "en" }), h("span", "area", labels.component_areas[item.area] || item.area));
  const rs = h("p", "item-reason");
  const cat = h("span", "cat");
  cat.append(catGlyph(item.category), document.createTextNode(labels.reason_categories[item.category]));
  rs.append(cat, h("span", null, item.reason, { lang: "en" }));
  c.append(rs);
  if (item.review) c.append(badge("review", "검수 대기 문서"));
  const t = h("div", "item-text");
  const p1 = h("p");
  p1.append(h("span", "lab", "형상 차이"), h("span", null, item.geometry || "", { lang: "en" }));
  const long = (item.description || "").length > CLAMP_CHARS;
  const p2 = h("p", long ? "clamp" : null);
  p2.append(h("span", "lab", "설명"), h("span", null, item.description || "", { lang: "en" }));
  const act = h("p", "item-actions");
  if (long) act.append(clampButton(t));
  const link = h("a", "ext", "FIA 원문 PDF", { href: item.url, rel: "noopener" });
  link.append(icon("external"), h("span", "sr-only", " (외부 문서)"));
  act.append(link);
  t.append(p1, p2, act);
  a.append(w, c, t);
  return a;
}

/** "전체 보기 / 줄여 보기" 단추. 누르면 item-text에 .open을 붙였다 뗀다. */
export function clampButton(textBox) {
  const b = h("button", "linkbtn", "전체 보기", { type: "button", "aria-expanded": "false" });
  b.addEventListener("click", () => toggleClamp(b, textBox));
  return b;
}

export function toggleClamp(button, textBox) {
  const open = !textBox.classList.contains("open");
  textBox.classList.toggle("open", open);
  button.textContent = open ? "줄여 보기" : "전체 보기";
  button.setAttribute("aria-expanded", String(open));
}
