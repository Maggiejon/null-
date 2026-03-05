#!/usr/bin/env python3
"""
从 laopu_price_list.csv 和 laopu_price_list_sheet2.csv 生成
老铺黄金产品价格对比 HTML 表格（products.html）
"""

import csv
import json
import os
from datetime import datetime, timezone, timedelta

CST     = timezone(timedelta(hours=8))
DIR     = os.path.dirname(__file__)
CSV1    = os.path.join(DIR, "laopu_price_list.csv")
CSV2    = os.path.join(DIR, "laopu_price_list_sheet2.csv")
OUT     = os.path.join(DIR, "products.html")
OUT_JSON = os.path.join(DIR, "products.json")

# ── CSV 读取 ─────────────────────────────────────────────────────────────────

def load_csv1(path: str) -> list:
    """格式：系列,名称,克重,标价,标价折合克,875折价,875折后折合克"""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                weight = float(r["克重"])
                price  = float(r["标价"])
                ppg    = round(price / weight) if weight else None
                d875   = round(price * 0.875)
                d875pg = round(d875 / weight) if weight else None
                rows.append({
                    "series":      r["系列"].strip(),
                    "name":        r["名称"].strip(),
                    "weight":      weight,
                    "price":       price,
                    "price_per_g": ppg,
                    "d875_price":  d875,
                    "d875_per_g":  d875pg,
                    "source":      "天猫旗舰店",
                })
            except (ValueError, KeyError):
                pass
    return rows


def load_csv2(path: str) -> list:
    """格式：系列,名称,克重,原价,875折价,每克单价"""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                weight = float(r["克重"])
                price  = float(r["原价"])
                ppg    = round(price / weight) if weight else None
                d875   = round(price * 0.875)
                d875pg = round(d875 / weight) if weight else None
                rows.append({
                    "series":      r["系列"].strip(),
                    "name":        r["名称"].strip(),
                    "weight":      weight,
                    "price":       price,
                    "price_per_g": ppg,
                    "d875_price":  d875,
                    "d875_per_g":  d875pg,
                    "source":      "京东旗舰店",
                })
            except (ValueError, KeyError):
                pass
    return rows


# ── 辅助格式化 ────────────────────────────────────────────────────────────────

def n(v) -> str:
    """数字格式化，千分位"""
    if v is None:
        return "—"
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return f"{v:,}" if isinstance(v, (int, float)) else str(v)


# ── HTML 生成 ─────────────────────────────────────────────────────────────────

# 系列排序权重（越小越靠前）
SERIES_ORDER = {
    "手镯手串系列": 1, "手镯系列": 1, "手链系列": 2,
    "素金吊坠系列": 3, "点钻吊坠系列": 4,
    "戒指系列": 5, "耳饰系列": 6, "胸针系列": 7,
    "典藏系列": 8, "其他系列": 99,
}


def series_key(s: str) -> int:
    return SERIES_ORDER.get(s, 50)


def build_table_html(rows: list, table_id: str) -> str:
    """生成单个表格（带系列行合并）。"""
    if not rows:
        return '<div class="no-data">暂无数据</div>'

    # 按系列 → 克价 排序
    rows_sorted = sorted(rows, key=lambda x: (series_key(x["series"]), x.get("price_per_g") or 0))

    # 预计算每个系列的行数（用于 rowspan）
    from collections import Counter
    series_cnt = Counter(r["series"] for r in rows_sorted)

    tbody = ""
    prev_series = None
    for r in rows_sorted:
        s         = r["series"]
        w         = f"{r['weight']}" if r["weight"] else "—"
        price     = n(r["price"])
        ppg       = n(r["price_per_g"])
        d875      = n(r["d875_price"])
        d875pg    = n(r["d875_per_g"])
        name      = r["name"]

        # 系列列（合并）
        series_td = ""
        if s != prev_series:
            series_td = (
                f'<td class="series-cell" rowspan="{series_cnt[s]}">'
                f'<span class="series-tag">{s}</span></td>'
            )
            prev_series = s

        # 克价着色（对比突出）
        ppg_cls = ""
        if r.get("price_per_g"):
            if r["price_per_g"] <= 1400:
                ppg_cls = " val-low"
            elif r["price_per_g"] >= 2000:
                ppg_cls = " val-high"

        tbody += (
            f'<tr>'
            f'{series_td}'
            f'<td class="name-cell">{name}</td>'
            f'<td class="num">{w}</td>'
            f'<td class="num price">{price}</td>'
            f'<td class="num ppg{ppg_cls}">{ppg}</td>'
            f'<td class="num d875">{d875}</td>'
            f'<td class="num d875pg">{d875pg}</td>'
            f'</tr>\n'
        )

    return f"""
<div class="tbl-container" id="{table_id}">
  <div class="scroll-x">
  <table class="ptable">
    <thead>
      <tr>
        <th class="th-series">系列</th>
        <th class="th-name">名称</th>
        <th class="th-num">克重</th>
        <th class="th-num">标价</th>
        <th class="th-num">标价折合克</th>
        <th class="th-num">875折价</th>
        <th class="th-num">875折后折合克</th>
      </tr>
    </thead>
    <tbody>
      {tbody}
    </tbody>
  </table>
  </div>
</div>"""


def generate_html(tmall_rows: list, jd_rows: list, generated_at: str) -> str:
    total = len(tmall_rows) + len(jd_rows)

    # 统计各系列数量
    def series_summary(rows):
        from collections import Counter
        c = Counter(r["series"] for r in rows)
        return " · ".join(f"{s} {cnt}件" for s, cnt in sorted(c.items(), key=lambda x: series_key(x[0])))

    tmall_summary = series_summary(tmall_rows)
    jd_summary    = series_summary(jd_rows)

    tmall_table = build_table_html(tmall_rows, "tmall-tbl")
    jd_table    = build_table_html(jd_rows,    "jd-tbl")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>老铺黄金 · 产品价格手册</title>
  <style>
    /* ── 基础变量 ── */
    :root {{
      --gold:      #C9A84C;
      --gold-l:    #E8C96A;
      --gold-pale: #F5E6B8;
      --gold-dim:  #8B6914;
      --gold-b:    rgba(201,168,76,0.18);
      --bg:        #0A0A0A;
      --card:      #141414;
      --card2:     #1a1a1a;
      --text:      #E8E0D0;
      --muted:     #9A8F7E;
      --red:       #C0392B;
      --green:     #27AE60;
      --blue:      #2980B9;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, 'PingFang SC', 'Hiragino Sans GB',
                   'Microsoft YaHei', sans-serif;
      font-size: 13px;
      line-height: 1.65;
      -webkit-font-smoothing: antialiased;
    }}

    /* ── 顶部标题 ── */
    .header {{
      background: linear-gradient(160deg, #0d0d0d 0%, #1a1205 60%, #0d0a00 100%);
      border-bottom: 1px solid var(--gold-b);
      padding: 32px 24px 24px;
      text-align: center;
      position: relative;
      overflow: hidden;
    }}
    .header::before {{
      content: '';
      position: absolute;
      top: -80px; left: 50%;
      transform: translateX(-50%);
      width: 320px; height: 320px;
      background: radial-gradient(circle, rgba(201,168,76,0.08) 0%, transparent 70%);
      pointer-events: none;
    }}
    .badge {{
      display: inline-block;
      border: 1px solid var(--gold-dim);
      color: var(--gold);
      font-size: 9px;
      letter-spacing: 3px;
      padding: 3px 14px;
      border-radius: 2px;
      margin-bottom: 14px;
      text-transform: uppercase;
    }}
    .header h1 {{
      font-size: 24px;
      font-weight: 700;
      color: var(--gold-l);
      letter-spacing: 4px;
      margin-bottom: 6px;
    }}
    .header .sub {{
      color: var(--muted);
      font-size: 11px;
      letter-spacing: 1px;
    }}
    .header .update {{
      margin-top: 10px;
      font-size: 10px;
      color: var(--gold-dim);
    }}

    /* ── 说明条 ── */
    .legend {{
      display: flex;
      gap: 20px;
      align-items: center;
      flex-wrap: wrap;
      padding: 10px 20px;
      background: rgba(201,168,76,0.04);
      border-bottom: 1px solid var(--gold-b);
      font-size: 11px;
      color: var(--muted);
    }}
    .legend-item {{ display: flex; align-items: center; gap: 6px; }}
    .dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
    .dot-low  {{ background: var(--green); }}
    .dot-high {{ background: var(--red); }}
    .dot-875  {{ background: var(--gold); }}

    /* ── 标签页 ── */
    .tabs {{
      display: flex;
      gap: 0;
      padding: 16px 16px 0;
      border-bottom: 2px solid var(--gold-b);
    }}
    .tab-btn {{
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      margin-bottom: -2px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 500;
      padding: 8px 20px;
      cursor: pointer;
      transition: all .2s;
      letter-spacing: .5px;
    }}
    .tab-btn:hover {{ color: var(--gold); }}
    .tab-btn.active {{
      color: var(--gold-l);
      border-bottom-color: var(--gold);
      font-weight: 600;
    }}
    .tab-meta {{
      font-size: 10px;
      color: var(--muted);
      margin-left: 6px;
      font-weight: 400;
    }}
    .tab-pane {{ display: none; padding: 20px 16px; }}
    .tab-pane.active {{ display: block; }}

    /* ── 表格 ── */
    .tbl-container {{ margin-bottom: 20px; }}
    .scroll-x {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    .ptable {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      min-width: 680px;
    }}
    .ptable th {{
      background: rgba(201,168,76,0.10);
      color: var(--gold);
      font-weight: 600;
      font-size: 11px;
      letter-spacing: .5px;
      padding: 9px 12px;
      text-align: left;
      border-bottom: 1px solid var(--gold-b);
      white-space: nowrap;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    .th-num {{ text-align: right !important; }}
    .th-series {{ width: 110px; }}
    .th-name {{ min-width: 200px; }}
    .ptable td {{
      padding: 8px 12px;
      border-bottom: 1px solid rgba(201,168,76,0.05);
      vertical-align: middle;
    }}
    .ptable tbody tr:hover td {{ background: rgba(201,168,76,0.04); }}
    .series-cell {{
      vertical-align: middle;
      border-right: 1px solid rgba(201,168,76,0.12);
      background: rgba(201,168,76,0.025);
    }}
    .series-tag {{
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      color: var(--gold-dim);
      letter-spacing: .3px;
      line-height: 1.4;
    }}
    .name-cell {{
      color: var(--text);
      font-size: 12.5px;
      max-width: 280px;
    }}
    .num {{
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }}
    .price {{ color: var(--text); }}
    .ppg   {{ color: var(--muted); }}
    .ppg.val-low  {{ color: var(--green); font-weight: 600; }}
    .ppg.val-high {{ color: var(--red);   font-weight: 600; }}
    .d875   {{ color: var(--gold); font-weight: 600; }}
    .d875pg {{ color: rgba(201,168,76,0.75); }}

    /* ── 摘要卡片 ── */
    .stats-bar {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }}
    .stat-card {{
      flex: 1;
      min-width: 120px;
      background: var(--card2);
      border: 1px solid var(--gold-b);
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .stat-card .label {{ font-size: 10px; color: var(--muted); margin-bottom: 4px; }}
    .stat-card .value {{ font-size: 18px; font-weight: 700; color: var(--gold-l); }}
    .stat-card .unit  {{ font-size: 10px; color: var(--muted); margin-left: 2px; }}

    /* ── 响应式 ── */
    @media (max-width: 640px) {{
      .header h1 {{ font-size: 18px; letter-spacing: 2px; }}
      .tab-btn   {{ padding: 7px 12px; font-size: 12px; }}
      .ptable    {{ font-size: 11px; }}
    }}
  </style>
</head>
<body>

<!-- ── 标题 ───────────────────────────────────────────────────────────────── -->
<div class="header">
  <div class="badge">Laopu Gold · Price Reference</div>
  <h1>老铺黄金 · 产品价格手册</h1>
  <div class="sub">天猫旗舰店 &amp; 京东旗舰店 · 在线商品汇总</div>
  <div class="update">📅 更新于 {generated_at} · 共 {total} 件商品</div>
</div>

<!-- ── 图例 ───────────────────────────────────────────────────────────────── -->
<div class="legend">
  <div class="legend-item">
    <div class="dot dot-875"></div>
    <span><strong>875折价 / 875折后折合克</strong> — 会员折扣（8.75折 = 标价 × 0.875）</span>
  </div>
  <div class="legend-item">
    <div class="dot dot-low"></div>
    <span>折合克 ≤ 1400 元（性价比较高）</span>
  </div>
  <div class="legend-item">
    <div class="dot dot-high"></div>
    <span>折合克 ≥ 2000 元（含钻、工艺溢价）</span>
  </div>
</div>

<!-- ── 标签页 ──────────────────────────────────────────────────────────────── -->
<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('tmall', this)">
    🛍 天猫旗舰店 <span class="tab-meta">{len(tmall_rows)} 件</span>
  </button>
  <button class="tab-btn" onclick="switchTab('jd', this)">
    🛒 京东旗舰店 <span class="tab-meta">{len(jd_rows)} 件</span>
  </button>
</div>

<!-- ── 天猫 ───────────────────────────────────────────────────────────────── -->
<div id="pane-tmall" class="tab-pane active">
  {_stats_bar(tmall_rows)}
  <p style="font-size:10px;color:var(--muted);margin-bottom:12px">{tmall_summary}</p>
  {tmall_table}
</div>

<!-- ── 京东 ───────────────────────────────────────────────────────────────── -->
<div id="pane-jd" class="tab-pane">
  {_stats_bar(jd_rows)}
  <p style="font-size:10px;color:var(--muted);margin-bottom:12px">{jd_summary}</p>
  {jd_table}
</div>

<script>
function switchTab(id, btn) {{
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('pane-' + id).classList.add('active');
  btn.classList.add('active');
}}
// 列排序
document.querySelectorAll('.ptable th').forEach((th, ci) => {{
  th.style.cursor = 'pointer';
  th.title = '点击排序';
  let asc = true;
  th.addEventListener('click', () => {{
    const tbody = th.closest('table').querySelector('tbody');
    const rows  = [...tbody.querySelectorAll('tr')];
    rows.sort((a, b) => {{
      const av = a.cells[ci]?.innerText.trim().replace(/,/g,'') || '';
      const bv = b.cells[ci]?.innerText.trim().replace(/,/g,'') || '';
      const an = parseFloat(av), bn = parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
      return asc ? av.localeCompare(bv, 'zh') : bv.localeCompare(av, 'zh');
    }});
    rows.forEach(r => tbody.appendChild(r));
    asc = !asc;
  }});
}});
</script>
</body>
</html>"""


def _stats_bar(rows: list) -> str:
    """生成统计卡片"""
    if not rows:
        return ""
    prices = [r["price"] for r in rows if r.get("price")]
    ppgs   = [r["price_per_g"] for r in rows if r.get("price_per_g")]
    if not prices:
        return ""
    avg_ppg = round(sum(ppgs) / len(ppgs)) if ppgs else 0
    min_ppg = min(ppgs) if ppgs else 0
    max_ppg = max(ppgs) if ppgs else 0
    count   = len(rows)
    return f"""
<div class="stats-bar">
  <div class="stat-card">
    <div class="label">商品总数</div>
    <div class="value">{count}<span class="unit">件</span></div>
  </div>
  <div class="stat-card">
    <div class="label">平均标价折合克</div>
    <div class="value">{avg_ppg:,}<span class="unit">元/克</span></div>
  </div>
  <div class="stat-card">
    <div class="label">最低折合克（素金）</div>
    <div class="value" style="color:var(--green)">{min_ppg:,}<span class="unit">元/克</span></div>
  </div>
  <div class="stat-card">
    <div class="label">最高折合克（含工艺）</div>
    <div class="value" style="color:var(--red)">{max_ppg:,}<span class="unit">元/克</span></div>
  </div>
</div>"""


# ════════════════════════════════════════════════════════════════════════════
#  主函数
# ════════════════════════════════════════════════════════════════════════════

def main():
    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M")

    tmall_rows = []
    jd_rows    = []

    if os.path.exists(CSV1):
        tmall_rows = load_csv1(CSV1)
        print(f"✅ 天猫数据（{CSV1.split('/')[-1]}）：{len(tmall_rows)} 件")
    else:
        print(f"⚠️  未找到 {CSV1}")

    if os.path.exists(CSV2):
        jd_rows = load_csv2(CSV2)
        print(f"✅ 京东数据（{CSV2.split('/')[-1]}）：{len(jd_rows)} 件")
    else:
        print(f"⚠️  未找到 {CSV2}")

    # 保存合并 JSON
    all_rows = [{"platform": "tmall", **r} for r in tmall_rows] + \
               [{"platform": "jd",    **r} for r in jd_rows]
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now_str,
                   "total": len(all_rows),
                   "products": all_rows}, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 已保存：{OUT_JSON}")

    # 生成 HTML
    html = generate_html(tmall_rows, jd_rows, now_str)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML 已生成：{OUT}")

    # 终端摘要
    print(f"\n{'系列':<14} {'名称':<28} {'克重':>6}  {'标价':>8}  {'克价':>6}")
    print("─" * 68)
    for r in sorted(tmall_rows + jd_rows,
                    key=lambda x: (series_key(x["series"]), x.get("price_per_g") or 0))[:20]:
        w  = f"{r['weight']}g" if r["weight"] else "—"
        pg = str(r.get("price_per_g") or "—")
        print(f"{r['series']:<14} {r['name'][:26]:<28} {w:>6}  "
              f"{int(r['price']):>8,}  {pg:>6}")
    total = len(tmall_rows) + len(jd_rows)
    if total > 20:
        print(f"  ...共 {total} 件，详见 {OUT}")


if __name__ == "__main__":
    main()
