#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
from urllib.parse import quote


PAGE_SIZE = 100


HTML_HEAD = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Album Assetizer Demo Review</title>
  <style>
    :root {
      --bg: #f4efe8;
      --panel: rgba(255, 252, 246, 0.95);
      --line: #d7cab8;
      --text: #1f1a15;
      --muted: #6f6457;
      --accent: #ab5634;
      --tag: #efe2d2;
      --tag-line: #e0cfbb;
      --active: #f3d9c7;
      --shadow: 0 14px 36px rgba(57, 38, 23, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font: 15px/1.5 "Noto Serif SC", "Source Han Serif SC", "PingFang SC", serif;
      background:
        radial-gradient(circle at top left, rgba(255,255,255,0.75), transparent 28%),
        radial-gradient(circle at bottom right, rgba(171,86,52,0.09), transparent 26%),
        linear-gradient(180deg, #faf5ed 0%, #f1e7d8 100%);
    }
    .wrap {
      max-width: 1500px;
      margin: 0 auto;
      padding: 22px;
    }
    .hero, .toolbar, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: var(--shadow);
    }
    .hero {
      padding: 22px 26px;
      margin-bottom: 16px;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 31px;
      line-height: 1.1;
    }
    .meta {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 14px;
    }
    .toolbar {
      padding: 16px;
      margin-bottom: 16px;
      display: grid;
      grid-template-columns: minmax(280px, 1.3fr) repeat(2, minmax(160px, 0.7fr)) auto auto auto auto;
      gap: 10px;
      align-items: center;
    }
    input, select, button, a.linkbtn {
      font: inherit;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.92);
      color: var(--text);
      padding: 11px 13px;
      text-decoration: none;
    }
    button, a.linkbtn {
      cursor: pointer;
    }
    button:disabled { cursor: not-allowed; opacity: 0.48; }
    .panel { padding: 16px; }
    .viewer {
      display: grid;
      grid-template-columns: minmax(480px, 1.15fr) minmax(360px, 0.85fr);
      gap: 16px;
      margin-bottom: 16px;
    }
    .stage, .detail {
      min-height: 720px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.75);
    }
    .stage {
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .imagebox {
      flex: 1;
      min-height: 0;
      border: 1px solid var(--line);
      border-radius: 16px;
      background:
        linear-gradient(135deg, rgba(255,255,255,0.8), rgba(238,228,214,0.9)),
        repeating-linear-gradient(
          45deg,
          rgba(200,180,160,0.08) 0,
          rgba(200,180,160,0.08) 18px,
          rgba(255,255,255,0.10) 18px,
          rgba(255,255,255,0.10) 36px
        );
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      position: relative;
    }
    .imagebox img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }
    .fallback {
      max-width: 70%;
      color: var(--muted);
      text-align: center;
      font-size: 16px;
      line-height: 1.7;
      padding: 24px;
    }
    .navline {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .status { color: var(--muted); font-size: 14px; }
    .detail { padding: 18px; overflow: auto; }
    .path {
      font-size: 12px;
      color: var(--muted);
      word-break: break-all;
      margin-bottom: 8px;
    }
    .title {
      margin: 0 0 10px;
      font-size: 24px;
      line-height: 1.35;
    }
    .scene {
      color: var(--accent);
      font-size: 17px;
      font-weight: 700;
      margin-bottom: 12px;
    }
    .lead { margin: 0 0 14px; color: #352b23; font-size: 15px; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
    .chip {
      background: var(--tag);
      border: 1px solid var(--tag-line);
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 12px;
      color: #43352a;
    }
    .section {
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px dashed var(--line);
    }
    .section h3 {
      margin: 0 0 8px;
      font-size: 14px;
      color: var(--muted);
    }
    .textblock {
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(255,255,255,0.7);
      border: 1px solid #eadfce;
      border-radius: 12px;
      padding: 12px;
    }
    .stats {
      display: grid;
      grid-template-columns: 110px 1fr;
      gap: 8px 12px;
      font-size: 14px;
      margin-top: 12px;
    }
    .stats .k { color: var(--muted); }
    .listpanel {
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.72);
      overflow: hidden;
    }
    .listhead {
      padding: 14px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      border-bottom: 1px solid var(--line);
    }
    .listmeta { color: var(--muted); font-size: 14px; }
    .jumppicker { min-width: 320px; max-width: 100%; }
    .list { max-height: 520px; overflow: auto; }
    .row {
      width: 100%;
      text-align: left;
      padding: 12px 16px;
      border: 0;
      border-bottom: 1px solid rgba(215,202,184,0.7);
      border-radius: 0;
      background: transparent;
      display: grid;
      grid-template-columns: 64px 1fr;
      gap: 10px;
    }
    .row.active { background: var(--active); }
    .rownum { color: var(--muted); font-size: 12px; padding-top: 2px; }
    .rowtitle { font-size: 14px; line-height: 1.35; margin-bottom: 4px; }
    .rowsub { color: var(--muted); font-size: 12px; line-height: 1.4; word-break: break-all; }
    .empty { padding: 36px 20px; text-align: center; color: var(--muted); }
    .hidden { display: none !important; }
    @media (max-width: 1120px) {
      .toolbar { grid-template-columns: 1fr 1fr; }
      .viewer { grid-template-columns: 1fr; }
      .stage, .detail { min-height: auto; }
    }
    @media (max-width: 720px) {
      .wrap { padding: 12px; }
      .toolbar { grid-template-columns: 1fr; }
      .jumppicker { min-width: 0; width: 100%; }
      .row { grid-template-columns: 48px 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Album Assetizer Demo</h1>
      <div class="meta">
        <span id="metaTotal"></span>
        <span id="metaPage"></span>
        <span>每页 100 张</span>
      </div>
    </section>

    <section class="toolbar">
      <input id="q" placeholder="搜索路径、caption、scene、tag、OCR">
      <select id="style">
        <option value="">全部风格</option>
      </select>
      <select id="textFlag">
        <option value="">全部文本类型</option>
        <option value="with_text">仅含文字</option>
        <option value="without_text">仅无文字</option>
      </select>
      <button id="prevPage">上一页 100</button>
      <button id="nextPage">下一页 100</button>
      <button id="prevItem">上一张</button>
      <button id="nextItem">下一张</button>
    </section>

    <section class="panel">
      <div class="viewer">
        <div class="stage">
          <div class="imagebox">
            <img id="mainImage" alt="">
            <div id="imageFallback" class="fallback hidden"></div>
          </div>
          <div class="navline">
            <span class="status" id="itemStatus"></span>
            <a id="openOriginal" class="linkbtn" target="_blank" rel="noopener noreferrer">打开原图</a>
          </div>
        </div>
        <div class="detail">
          <div class="path" id="detailPath"></div>
          <h2 class="title" id="detailTitle"></h2>
          <div class="scene" id="detailScene"></div>
          <p class="lead" id="detailLong"></p>
          <div class="chips" id="tagChips"></div>
          <div class="section">
            <h3>主体</h3>
            <div class="chips" id="subjectChips"></div>
          </div>
          <div class="section">
            <h3>活动</h3>
            <div class="chips" id="activityChips"></div>
          </div>
          <div class="section">
            <h3>风格与质量</h3>
            <div class="chips" id="styleChips"></div>
            <div class="chips" id="qualityChips"></div>
          </div>
          <div class="section">
            <h3>OCR</h3>
            <div class="textblock" id="ocrBlock"></div>
          </div>
          <div class="section">
            <h3>信息</h3>
            <div class="stats">
              <div class="k">asset_id</div><div id="statAssetId"></div>
              <div class="k">source</div><div id="statSource"></div>
              <div class="k">contains_text</div><div id="statContainsText"></div>
              <div class="k">people_count</div><div id="statPeopleCount"></div>
              <div class="k">confidence</div><div id="statConfidence"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="listpanel">
        <div class="listhead">
          <div class="listmeta" id="listMeta"></div>
          <select id="itemPicker" class="jumppicker"></select>
        </div>
        <div class="list" id="list"></div>
      </div>
    </section>
  </div>
  <script>
"""


HTML_TAIL = """
  </script>
</body>
</html>
"""


def choose_result(payload: dict) -> tuple[dict, str]:
    original = payload.get("first_pass_result") or payload.get("original_result") or {}
    if original:
        return original, "first_pass"
    result = payload.get("result") or {}
    return result, "result"


def build_item(payload: dict, image_root: Path, html_dir: Path) -> dict:
    result, source_from = choose_result(payload)
    rel_path = str(payload.get("rel_path", "")).replace("\\", "/")
    image_path = image_root / rel_path
    image_url = os.path.relpath(image_path, start=html_dir).replace("\\", "/")
    return {
        "asset_id": payload.get("asset_id"),
        "rel_path": rel_path,
        "image_url": quote(image_url, safe="/"),
        "source_from": source_from,
        "caption_short": result.get("caption_short", ""),
        "caption_long": result.get("caption_long", ""),
        "scene": result.get("scene", ""),
        "tags": result.get("tags", []) or [],
        "main_subjects": result.get("main_subjects", []) or [],
        "activities": result.get("activities", []) or [],
        "style_labels": result.get("style_labels", []) or [],
        "quality_flags": result.get("quality_flags", []) or [],
        "contains_text": bool(result.get("contains_text", False)),
        "ocr_text": result.get("ocr_text", ""),
        "people_count": result.get("people_count", -1),
        "confidence": result.get("confidence", 0),
        "source_format": payload.get("source_format", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a static review HTML from exported album results.")
    parser.add_argument("--jsonl", required=True, help="Path to first-pass or results JSONL")
    parser.add_argument("--image-root", required=True, help="Album root directory for resolving images")
    parser.add_argument("--output", default="docs/demo/review.html", help="Output HTML path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    jsonl_path = Path(args.jsonl).resolve()
    image_root = Path(args.image_root).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
      for line in f:
        line = line.strip()
        if not line:
          continue
        payload = json.loads(line)
        items.append(build_item(payload, image_root, output_path.parent))

    styles = sorted({style for item in items for style in item["style_labels"]})
    script = (
        f"const ITEMS = {json.dumps(items, ensure_ascii=False)};\n"
        f"const STYLES = {json.dumps(styles, ensure_ascii=False)};\n"
        f"const PAGE_SIZE = {PAGE_SIZE};\n"
        """
const qEl = document.getElementById('q');
const styleEl = document.getElementById('style');
const textFlagEl = document.getElementById('textFlag');
const prevPageEl = document.getElementById('prevPage');
const nextPageEl = document.getElementById('nextPage');
const prevItemEl = document.getElementById('prevItem');
const nextItemEl = document.getElementById('nextItem');
const metaTotalEl = document.getElementById('metaTotal');
const metaPageEl = document.getElementById('metaPage');
const itemStatusEl = document.getElementById('itemStatus');
const mainImageEl = document.getElementById('mainImage');
const imageFallbackEl = document.getElementById('imageFallback');
const openOriginalEl = document.getElementById('openOriginal');
const detailPathEl = document.getElementById('detailPath');
const detailTitleEl = document.getElementById('detailTitle');
const detailSceneEl = document.getElementById('detailScene');
const detailLongEl = document.getElementById('detailLong');
const tagChipsEl = document.getElementById('tagChips');
const subjectChipsEl = document.getElementById('subjectChips');
const activityChipsEl = document.getElementById('activityChips');
const styleChipsEl = document.getElementById('styleChips');
const qualityChipsEl = document.getElementById('qualityChips');
const ocrBlockEl = document.getElementById('ocrBlock');
const statAssetIdEl = document.getElementById('statAssetId');
const statSourceEl = document.getElementById('statSource');
const statContainsTextEl = document.getElementById('statContainsText');
const statPeopleCountEl = document.getElementById('statPeopleCount');
const statConfidenceEl = document.getElementById('statConfidence');
const listMetaEl = document.getElementById('listMeta');
const itemPickerEl = document.getElementById('itemPicker');
const listEl = document.getElementById('list');

let filteredItems = ITEMS.slice();
let currentIndex = 0;
let currentPage = 0;

for (const style of STYLES) {
  const op = document.createElement('option');
  op.value = style;
  op.textContent = style;
  styleEl.appendChild(op);
}

function escapeHtml(text) {
  return String(text || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function makeChips(values) {
  if (!values || !values.length) return '<span class="chip">无</span>';
  return values.map(value => `<span class="chip">${escapeHtml(value)}</span>`).join('');
}

function getSearchText(item) {
  return [
    item.rel_path, item.caption_short, item.caption_long, item.scene, item.ocr_text,
    ...(item.tags || []), ...(item.main_subjects || []), ...(item.activities || []),
    ...(item.style_labels || []), ...(item.quality_flags || [])
  ].join('\\n').toLowerCase();
}

function applyFilters() {
  const keyword = qEl.value.trim().toLowerCase();
  const styleValue = styleEl.value;
  const textFlag = textFlagEl.value;
  filteredItems = ITEMS.filter(item => {
    if (keyword && !getSearchText(item).includes(keyword)) return false;
    if (styleValue && !(item.style_labels || []).includes(styleValue)) return false;
    if (textFlag === 'with_text' && !item.contains_text) return false;
    if (textFlag === 'without_text' && item.contains_text) return false;
    return true;
  });
  currentPage = 0;
  currentIndex = 0;
  render();
}

function getTotalPages() {
  return Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE));
}

function clampState() {
  const totalPages = getTotalPages();
  if (currentPage >= totalPages) currentPage = totalPages - 1;
  if (currentPage < 0) currentPage = 0;
  if (!filteredItems.length) { currentPage = 0; currentIndex = 0; return; }
  if (currentIndex < 0) currentIndex = 0;
  if (currentIndex >= filteredItems.length) currentIndex = filteredItems.length - 1;
  const pageStart = currentPage * PAGE_SIZE;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, filteredItems.length);
  if (currentIndex < pageStart || currentIndex >= pageEnd) currentIndex = pageStart;
}

function getPageItems() {
  const start = currentPage * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, filteredItems.length);
  return filteredItems.slice(start, end);
}

function showFallback(message) {
  imageFallbackEl.textContent = message;
  imageFallbackEl.classList.remove('hidden');
  mainImageEl.classList.add('hidden');
  mainImageEl.removeAttribute('src');
}

function renderViewer() {
  if (!filteredItems.length) {
    showFallback('当前筛选条件下没有结果。');
    detailPathEl.textContent = '';
    detailTitleEl.textContent = '没有匹配结果';
    detailSceneEl.textContent = '';
    detailLongEl.textContent = '';
    tagChipsEl.innerHTML = '';
    subjectChipsEl.innerHTML = '';
    activityChipsEl.innerHTML = '';
    styleChipsEl.innerHTML = '';
    qualityChipsEl.innerHTML = '';
    ocrBlockEl.textContent = '';
    statAssetIdEl.textContent = '';
    statSourceEl.textContent = '';
    statContainsTextEl.textContent = '';
    statPeopleCountEl.textContent = '';
    statConfidenceEl.textContent = '';
    itemStatusEl.textContent = '0 / 0';
    openOriginalEl.removeAttribute('href');
    return;
  }
  const item = filteredItems[currentIndex];
  detailPathEl.textContent = item.rel_path;
  detailTitleEl.textContent = item.caption_short || '(无标题描述)';
  detailSceneEl.textContent = item.scene || '';
  detailLongEl.textContent = item.caption_long || '';
  tagChipsEl.innerHTML = makeChips(item.tags);
  subjectChipsEl.innerHTML = makeChips(item.main_subjects);
  activityChipsEl.innerHTML = makeChips(item.activities);
  styleChipsEl.innerHTML = makeChips(item.style_labels);
  qualityChipsEl.innerHTML = makeChips(item.quality_flags);
  ocrBlockEl.textContent = item.ocr_text || '无';
  statAssetIdEl.textContent = item.asset_id;
  statSourceEl.textContent = `${item.source_from} | ${item.source_format}`;
  statContainsTextEl.textContent = item.contains_text ? 'true' : 'false';
  statPeopleCountEl.textContent = item.people_count;
  statConfidenceEl.textContent = item.confidence;
  itemStatusEl.textContent = `第 ${currentIndex + 1} / ${filteredItems.length} 张`;
  openOriginalEl.href = item.image_url;
  imageFallbackEl.classList.add('hidden');
  mainImageEl.classList.remove('hidden');
  mainImageEl.alt = item.rel_path;
  mainImageEl.onload = () => { imageFallbackEl.classList.add('hidden'); mainImageEl.classList.remove('hidden'); };
  mainImageEl.onerror = () => { showFallback(`当前文件无法直接在浏览器中显示。\\n格式：${item.source_format}\\n路径：${item.rel_path}`); };
  mainImageEl.src = item.image_url;
}

function renderList() {
  const pageItems = getPageItems();
  const totalPages = getTotalPages();
  const start = currentPage * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, filteredItems.length);
  metaTotalEl.textContent = `当前筛选 ${filteredItems.length} / 全部 ${ITEMS.length} 张`;
  metaPageEl.textContent = `第 ${currentPage + 1} / ${totalPages} 页`;
  listMetaEl.textContent = `本页第 ${start + 1}${filteredItems.length ? ` - ${end}` : ''} 条`;
  itemPickerEl.innerHTML = '';
  for (let i = 0; i < pageItems.length; i++) {
    const item = pageItems[i];
    const globalIndex = start + i;
    const option = document.createElement('option');
    option.value = String(globalIndex);
    option.textContent = `${globalIndex + 1}. ${item.caption_short || '(无标题描述)'} | ${item.rel_path}`;
    if (globalIndex === currentIndex) option.selected = true;
    itemPickerEl.appendChild(option);
  }
  if (!pageItems.length) {
    listEl.innerHTML = '<div class="empty">当前筛选条件下没有条目。</div>';
    return;
  }
  listEl.innerHTML = pageItems.map((item, i) => {
    const globalIndex = start + i;
    const active = globalIndex === currentIndex ? ' active' : '';
    return `
      <button class="row${active}" data-index="${globalIndex}">
        <div class="rownum">${globalIndex + 1}</div>
        <div>
          <div class="rowtitle">${escapeHtml(item.caption_short || '(无标题描述)')}</div>
          <div class="rowsub">${escapeHtml(item.scene || '')}</div>
          <div class="rowsub">${escapeHtml(item.rel_path)}</div>
        </div>
      </button>
    `;
  }).join('');
}

function render() {
  clampState();
  renderViewer();
  renderList();
  prevItemEl.disabled = !filteredItems.length || currentIndex <= 0;
  nextItemEl.disabled = !filteredItems.length || currentIndex >= filteredItems.length - 1;
  prevPageEl.disabled = currentPage <= 0;
  nextPageEl.disabled = currentPage >= getTotalPages() - 1 || !filteredItems.length;
}

function setCurrentIndex(nextIndex) {
  if (!filteredItems.length) return;
  if (nextIndex < 0) nextIndex = 0;
  if (nextIndex >= filteredItems.length) nextIndex = filteredItems.length - 1;
  currentIndex = nextIndex;
  currentPage = Math.floor(currentIndex / PAGE_SIZE);
  render();
}

function setCurrentPage(nextPage) {
  if (!filteredItems.length) return;
  const totalPages = getTotalPages();
  if (nextPage < 0) nextPage = 0;
  if (nextPage >= totalPages) nextPage = totalPages - 1;
  currentPage = nextPage;
  currentIndex = currentPage * PAGE_SIZE;
  render();
}

qEl.addEventListener('input', applyFilters);
styleEl.addEventListener('change', applyFilters);
textFlagEl.addEventListener('change', applyFilters);
prevItemEl.addEventListener('click', () => setCurrentIndex(currentIndex - 1));
nextItemEl.addEventListener('click', () => setCurrentIndex(currentIndex + 1));
prevPageEl.addEventListener('click', () => setCurrentPage(currentPage - 1));
nextPageEl.addEventListener('click', () => setCurrentPage(currentPage + 1));
itemPickerEl.addEventListener('change', () => setCurrentIndex(Number(itemPickerEl.value)));
listEl.addEventListener('click', (event) => {
  const btn = event.target.closest('.row');
  if (!btn) return;
  setCurrentIndex(Number(btn.dataset.index));
});
document.addEventListener('keydown', (event) => {
  if (event.target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)) return;
  if (event.key === 'ArrowLeft') setCurrentIndex(currentIndex - 1);
  if (event.key === 'ArrowRight') setCurrentIndex(currentIndex + 1);
  if (event.key === 'PageUp') setCurrentPage(currentPage - 1);
  if (event.key === 'PageDown') setCurrentPage(currentPage + 1);
});
render();
"""
    )

    output_path.write_text(HTML_HEAD + script + HTML_TAIL, encoding="utf-8")
    print(json.dumps({"html": str(output_path), "count": len(items), "page_size": PAGE_SIZE}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
