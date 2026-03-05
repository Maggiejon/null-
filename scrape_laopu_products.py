#!/usr/bin/env python3
"""
老铺黄金 · 天猫 & 京东旗舰店产品数据爬虫

【运行方式】
  python3 scrape_laopu_products.py              # 爬取两平台
  python3 scrape_laopu_products.py --jd-only    # 仅爬取京东
  python3 scrape_laopu_products.py --tmall-only # 仅爬取天猫

【说明】
  脚本会打开一个可见的 Chrome 窗口。如未登录，请在窗口内完成登录，
  脚本将等待最多 90 秒后自动继续爬取商品列表。
  登录成功后请勿关闭窗口。

【输出】
  products.json  — 结构化产品数据
  products.html  — 美观的产品价格对比表格
"""

import re
import json
import os
import sys
import time
import tempfile
import shutil
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
OUT_JSON = os.path.join(os.path.dirname(__file__), "products.json")
OUT_HTML = os.path.join(os.path.dirname(__file__), "products.html")

CHROME_EXECUTABLE = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# ── 系列分类 ─────────────────────────────────────────────────────────────────
SERIES_KEYWORDS = [
    ("手镯手串系列",   ["手镯", "手链", "手串"]),
    ("素金吊坠系列",   ["吊坠"]),
    ("项链颈饰系列",   ["项链", "颈链", "锁骨链"]),
    ("戒指系列",       ["戒指", "指环"]),
    ("耳饰系列",       ["耳环", "耳坠", "耳钉", "耳饰"]),
    ("发饰系列",       ["发簪", "发钗", "发夹", "发饰", "发箍"]),
    ("摆件挂件系列",   ["摆件", "摆饰", "挂件", "玉佩", "平安扣"]),
    ("金条金币系列",   ["金条", "金币", "金块", "投资金"]),
    ("生肖系列",       ["生肖", "蛇年", "龙年", "马年", "生肖链", "生肖戒", "生肖坠"]),
]


def classify_series(name: str) -> str:
    for series, kws in SERIES_KEYWORDS:
        if any(kw in name for kw in kws):
            return series
    return "其他系列"


def extract_weight(text: str) -> float | None:
    patterns = [
        r'(\d+\.?\d*)\s*克重',
        r'重\s*(\d+\.?\d*)\s*克',
        r'(\d+\.?\d*)\s*g重',
        r'净重\s*[：:]\s*(\d+\.?\d*)',
        r'金重\s*[：:]\s*(\d+\.?\d*)',
        r'(\d+\.?\d*)\s*克(?![金价率])',
        r'(\d+\.?\d*)\s*g(?!r|ram|\w)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            w = float(m.group(1))
            if 0.3 <= w <= 3000:
                return w
    return None


def calc_metrics(price: float, weight: float | None) -> dict:
    if weight and weight > 0:
        price_per_g = round(price / weight)
        d875_price  = round(price * 0.875)
        d875_per_g  = round(d875_price / weight)
    else:
        price_per_g = d875_price = d875_per_g = None
    return {"price_per_g": price_per_g,
            "d875_price":  d875_price,
            "d875_per_g":  d875_per_g}


# ════════════════════════════════════════════════════════════════════════════
#  浏览器工厂 — 可见 Chrome，带 Cookie 复用
# ════════════════════════════════════════════════════════════════════════════

def _launch_browser(pw, headless: bool = False):
    """启动 Chrome。先尝试复用本地 Chrome 配置（含已有登录 Cookie）。"""
    tmp_dir = None
    profile_src = os.path.expanduser(
        "~/Library/Application Support/Google/Chrome/Default"
    )

    if os.path.exists(profile_src):
        # 复制关键文件到临时目录，避免与运行中的 Chrome 冲突
        tmp_dir = tempfile.mkdtemp(prefix="laopu-chrome-")
        tmp_default = os.path.join(tmp_dir, "Default")
        os.makedirs(tmp_default, exist_ok=True)
        for fname in ["Cookies", "Preferences", "Secure Preferences"]:
            src = os.path.join(profile_src, fname)
            if os.path.exists(src):
                try:
                    shutil.copy2(src, os.path.join(tmp_default, fname))
                except Exception:
                    pass
        # 复制 Local State（含加密密钥元数据）
        ls_src = os.path.expanduser(
            "~/Library/Application Support/Google/Chrome/Local State"
        )
        if os.path.exists(ls_src):
            shutil.copy2(ls_src, os.path.join(tmp_dir, "Local State"))

    chrome_path = (CHROME_EXECUTABLE
                   if os.path.exists(CHROME_EXECUTABLE) else None)

    launch_kwargs = dict(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--profile-directory=Default",
        ],
    )
    if chrome_path:
        launch_kwargs["executable_path"] = chrome_path

    if tmp_dir:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=tmp_dir,
            **launch_kwargs,
        )
    else:
        browser = pw.chromium.launch(**launch_kwargs)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
        )

    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
    )
    return ctx, tmp_dir


def _wait_for_login(page, domain: str, timeout_s: int = 90) -> bool:
    """等待用户登录（最多 timeout_s 秒）。返回 True 表示已登录。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        url = page.url
        if "login" not in url and "captcha" not in url.lower() and domain in url:
            return True
        time.sleep(2)
    return False


# ════════════════════════════════════════════════════════════════════════════
#  天猫爬虫
# ════════════════════════════════════════════════════════════════════════════

TMALL_STORE_URL = "https://laopuhuangjin.world.tmall.com/"
TMALL_SEARCH_URL = "https://laopuhuangjin.world.tmall.com/search.htm?q="


def _parse_tmall_items(page) -> list:
    """从当前天猫页面提取商品数据。"""
    items_data = []

    # 尝试多种商品容器选择器（不同版本 Tmall 店铺结构不同）
    ITEM_SELECTORS = [
        ".J_TItems li",
        ".item",
        "[class*='ItemCard']",
        "[class*='item-card']",
        "[class*='ItemWrap']",
        "[class*='productCard']",
        ".items li",
        ".shop-hesper-pc-product-card",
    ]

    items = []
    for sel in ITEM_SELECTORS:
        try:
            found = page.query_selector_all(sel)
            if len(found) > items:
                items = found
                if len(found) > 3:
                    break
        except Exception:
            pass

    if not items:
        # 备用：从页面 JSON 中提取
        html = page.content()
        json_items = re.findall(
            r'"itemId"\s*:\s*"?(\d+)"?[^}]{0,200}"title"\s*:\s*"([^"]+)"'
            r'[^}]{0,100}"price"\s*:\s*"?(\d+\.?\d*)"?',
            html,
        )
        for item_id, title, price_str in json_items[:60]:
            price  = float(price_str)
            weight = extract_weight(title)
            series = classify_series(title)
            items_data.append({
                "platform": "tmall",
                "series":   series,
                "name":     title,
                "weight":   weight,
                "price":    price,
                "link":     f"https://detail.tmall.com/item.htm?id={item_id}",
                **calc_metrics(price, weight),
            })
        return items_data

    for item in items:
        try:
            name_el = (
                item.query_selector("[class*='title']")
                or item.query_selector("[class*='name']:not([class*='shop'])")
                or item.query_selector("span.title")
                or item.query_selector("a[title]")
            )
            name = ""
            if name_el:
                name = name_el.inner_text().strip()
                if not name and name_el.get_attribute("title"):
                    name = name_el.get_attribute("title").strip()
            if len(name) < 2:
                continue

            price_el = (
                item.query_selector("[class*='price']")
                or item.query_selector("[class*='Price']")
            )
            if not price_el:
                continue
            price_m = re.search(r'[\d,]+\.?\d*', price_el.inner_text().replace(",", ""))
            if not price_m:
                continue
            price = float(price_m.group().replace(",", ""))
            if price < 50:
                continue

            link_el = item.query_selector("a[href]")
            link = ""
            if link_el:
                link = link_el.get_attribute("href") or ""
                if link.startswith("//"):
                    link = "https:" + link

            weight  = extract_weight(name)
            series  = classify_series(name)
            items_data.append({
                "platform": "tmall",
                "series":   series,
                "name":     name,
                "weight":   weight,
                "price":    price,
                "link":     link,
                **calc_metrics(price, weight),
            })
        except Exception:
            continue
    return items_data


def scrape_tmall(headless: bool = False, max_pages: int = 10) -> list:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("  [SKIP] playwright 未安装")
        return []

    products = []

    with sync_playwright() as pw:
        ctx, tmp_dir = _launch_browser(pw, headless=headless)
        try:
            page = ctx.new_page()
            print(f"  天猫: 打开旗舰店 {TMALL_STORE_URL}")
            page.goto(TMALL_STORE_URL, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(3000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

            # 检查是否需要登录
            if "login" in page.url or "captcha" in page.url.lower():
                print("  天猫: 需要登录，请在弹出窗口中完成登录（等待最多 90 秒）...")
                if not headless:
                    logged = _wait_for_login(page, "tmall.com")
                    if not logged:
                        print("  天猫: 登录超时，跳过")
                        return []
                else:
                    print("  天猫: 无头模式下需要登录，无法自动完成，请以可见模式运行")
                    return []

            # 进入全部商品搜索页
            page.goto(TMALL_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

            if "login" in page.url or "captcha" in page.url.lower():
                print("  天猫: 商品页需要登录")
                if not headless:
                    logged = _wait_for_login(page, "tmall.com")
                    if not logged:
                        return []
                else:
                    return []

            # 滚动加载商品
            for _ in range(20):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(350)

            batch = _parse_tmall_items(page)
            products.extend(batch)
            print(f"  天猫第1页: {len(batch)} 件")

            # 分页
            for pg in range(2, max_pages + 1):
                next_el = page.query_selector(
                    ".next:not(.disabled), [class*='next']:not([class*='disable'])"
                )
                if not next_el:
                    break
                try:
                    next_el.click()
                    page.wait_for_timeout(3000)
                    for _ in range(15):
                        page.evaluate("window.scrollBy(0, 600)")
                        page.wait_for_timeout(300)
                    batch = _parse_tmall_items(page)
                    products.extend(batch)
                    print(f"  天猫第{pg}页: {len(batch)} 件")
                except Exception:
                    break

        except Exception as e:
            print(f"  [WARN] 天猫: {e}")
        finally:
            ctx.close()
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    # 去重
    seen, result = set(), []
    for p in products:
        key = f"{p['name']}_{p['price']}"
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


# ════════════════════════════════════════════════════════════════════════════
#  京东爬虫
# ════════════════════════════════════════════════════════════════════════════

JD_SEARCH_URL = (
    "https://search.jd.com/Search"
    "?keyword=%E8%80%81%E9%93%BA%E9%BB%84%E9%87%91%E6%97%97%E8%88%B0%E5%BA%97"
    "&enc=utf-8&psort=3&click=0"
)
JD_HOME_URL = "https://www.jd.com"
JD_OFFICIAL_KEYWORDS = ["老铺黄金", "老铺", "LaoPoHuangJin", "laopuhuangjin"]


def _parse_jd_items(page) -> list:
    items_data = []
    try:
        page.wait_for_selector(".gl-item", timeout=10000)
    except Exception:
        return items_data

    for item in page.query_selector_all(".gl-item"):
        try:
            shop_el = (
                item.query_selector(".p-shop a")
                or item.query_selector(".p-shop span")
            )
            shop_name = shop_el.inner_text().strip() if shop_el else ""
            if shop_name and not any(kw in shop_name for kw in JD_OFFICIAL_KEYWORDS):
                continue

            name_el = (
                item.query_selector(".p-name em")
                or item.query_selector(".p-name a")
            )
            price_el = (
                item.query_selector(".p-price i")
                or item.query_selector(".p-price strong i")
            )
            if not name_el or not price_el:
                continue

            name      = name_el.inner_text().strip()
            price_raw = price_el.inner_text().strip().replace(",", "")
            price     = float(price_raw)
            if price < 50:
                continue

            link_el = (
                item.query_selector("a[href*='item.jd.com']")
                or item.query_selector(".p-name a")
            )
            link = ""
            if link_el:
                link = link_el.get_attribute("href") or ""
                if link.startswith("//"):
                    link = "https:" + link

            weight  = extract_weight(name)
            series  = classify_series(name)
            items_data.append({
                "platform": "jd",
                "series":   series,
                "name":     name,
                "weight":   weight,
                "price":    price,
                "link":     link,
                **calc_metrics(price, weight),
            })
        except Exception:
            continue
    return items_data


def scrape_jd(headless: bool = False, max_pages: int = 8) -> list:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("  [SKIP] playwright 未安装")
        return []

    products = []

    with sync_playwright() as pw:
        ctx, tmp_dir = _launch_browser(pw, headless=headless)
        try:
            page = ctx.new_page()

            # 先访问京东主页（建立 Cookie）
            print(f"  JD: 访问主页 {JD_HOME_URL}")
            page.goto(JD_HOME_URL, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2000)

            # 检查是否重定向到登录
            if "login" in page.url or "passport" in page.url:
                print("  JD: 需要登录，请在弹出窗口中完成登录（等待最多 90 秒）...")
                if not headless:
                    _wait_for_login(page, "jd.com")
                else:
                    print("  JD: 无头模式需要登录，请以可见模式运行")
                    return []

            # 搜索老铺黄金
            print(f"  JD: 搜索旗舰店商品...")
            page.goto(JD_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            if "login" in page.url or "passport" in page.url or "risk" in page.url:
                print("  JD: 搜索页需要登录或触发风控")
                if not headless:
                    print("  JD: 请在浏览器窗口手动搜索'老铺黄金旗舰店'后等待...")
                    time.sleep(15)  # 等用户手动处理
                else:
                    return []

            for pg in range(1, max_pages + 1):
                # 滚动加载
                for _ in range(5):
                    page.evaluate("window.scrollBy(0, 900)")
                    page.wait_for_timeout(400)

                batch = _parse_jd_items(page)
                products.extend(batch)
                print(f"  JD 第{pg}页: {len(batch)} 件（官方旗舰店）")

                # 翻页
                next_el = page.query_selector(".pager-next:not(.disabled)")
                if not next_el:
                    break
                next_el.click()
                page.wait_for_timeout(2500)

        except Exception as e:
            print(f"  [WARN] JD: {e}")
        finally:
            ctx.close()
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    # 去重
    seen, result = set(), []
    for p in products:
        key = f"{p['name']}_{p['price']}"
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


# ════════════════════════════════════════════════════════════════════════════
#  HTML 表格生成
# ════════════════════════════════════════════════════════════════════════════

def fmt_num(v, suffix="") -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and v == int(v):
        v = int(v)
    if isinstance(v, (int, float)):
        return f"{v:,}{suffix}"
    return f"{v}{suffix}"


def build_html(products: list, generated_at: str) -> str:
    jd_prods    = [p for p in products if p["platform"] == "jd"]
    tmall_prods = [p for p in products if p["platform"] == "tmall"]

    def make_rows(prods: list) -> str:
        prods_sorted = sorted(prods, key=lambda x: (x["series"], x["name"]))
        rows = ""
        prev_series = None
        series_counts = {}
        for p in prods_sorted:
            series_counts[p["series"]] = series_counts.get(p["series"], 0) + 1

        for p in prods_sorted:
            series      = p["series"]
            name        = p["name"]
            weight      = fmt_num(p["weight"])
            price       = fmt_num(p["price"])
            price_per_g = fmt_num(p.get("price_per_g"))
            d875_price  = fmt_num(p.get("d875_price"))
            d875_per_g  = fmt_num(p.get("d875_per_g"))
            link        = p.get("link", "")
            no_weight   = p["weight"] is None

            name_html = (
                f'<a href="{link}" target="_blank" '
                f'style="color:inherit;text-decoration:none">{name}</a>'
                if link else name
            )

            series_td = ""
            if series != prev_series:
                span = series_counts.get(series, 1)
                series_td = (
                    f'<td class="series-cell" rowspan="{span}">'
                    f'{series}</td>'
                )
                prev_series = series

            warn_cls = ' class="warn-row"' if no_weight else ""
            rows += (
                f'<tr{warn_cls}>'
                f'{series_td}'
                f'<td class="name-cell">{name_html}</td>'
                f'<td class="num">{weight}</td>'
                f'<td class="num">{price}</td>'
                f'<td class="num">{price_per_g}</td>'
                f'<td class="num d875">{d875_price}</td>'
                f'<td class="num d875">{d875_per_g}</td>'
                f'</tr>\n'
            )
        return rows

    def make_table(prods: list, label: str, pid: str) -> str:
        if not prods:
            return (
                f'<div class="no-data">'
                f'<div class="no-data-icon">⚠️</div>'
                f'{label} 暂未获取到产品数据<br>'
                f'<small>请确保已登录平台后重新运行脚本，'
                f'或参见 README 了解使用方法</small>'
                f'</div>'
            )
        rows = make_rows(prods)
        return f"""
<div class="table-wrap" id="{pid}">
  <div class="table-header">
    <span class="platform-badge {pid}">{label}</span>
    <span class="count-badge">共 {len(prods)} 件商品</span>
  </div>
  <div class="scroll-x">
  <table class="products-table">
    <thead>
      <tr>
        <th>系列</th>
        <th>名称</th>
        <th>克重</th>
        <th>标价</th>
        <th>标价折合克</th>
        <th>875折价</th>
        <th>875折后折合克</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  </div>
</div>"""

    jd_table    = make_table(jd_prods,    "🛒 京东旗舰店", "jd")
    tmall_table = make_table(tmall_prods, "🛍 天猫旗舰店",  "tmall")
    total = len(products)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>老铺黄金 · 产品价格手册</title>
  <style>
    :root {{
      --gold:      #C9A84C;
      --gold-light:#E8C96A;
      --gold-dim:  #8B6914;
      --black:     #0A0A0A;
      --card:      #181818;
      --border:    rgba(201,168,76,0.18);
      --text:      #E8E0D0;
      --muted:     #9A8F7E;
      --jd:        #E1251B;
      --tmall:     #FF4400;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--black);
      color: var(--text);
      font-family: -apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
      font-size: 13px;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }}
    .header {{
      background: linear-gradient(160deg,#0d0d0d 0%,#1a1205 60%,#0d0a00 100%);
      border-bottom: 1px solid var(--border);
      padding: 28px 20px 22px;
      text-align: center;
    }}
    .header h1 {{
      font-size: 22px;
      font-weight: 700;
      color: var(--gold-light);
      letter-spacing: 3px;
      margin-bottom: 6px;
    }}
    .header .sub {{ color: var(--muted); font-size: 11px; letter-spacing: 1px; }}
    .header .update {{ margin-top: 8px; font-size: 10px; color: var(--gold-dim); }}
    .tabs {{
      display: flex;
      gap: 8px;
      padding: 16px 16px 0;
      border-bottom: 1px solid var(--border);
    }}
    .tab-btn {{
      background: transparent;
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 12px;
      padding: 6px 16px;
      border-radius: 6px 6px 0 0;
      cursor: pointer;
      transition: all .2s;
    }}
    .tab-btn.active {{
      background: var(--card);
      border-bottom-color: var(--card);
      color: var(--gold);
    }}
    .tab-pane {{ display: none; padding: 16px; }}
    .tab-pane.active {{ display: block; }}
    .table-wrap {{ margin-bottom: 20px; }}
    .table-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }}
    .platform-badge {{
      font-size: 12px;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 4px;
    }}
    .platform-badge.jd    {{ background:rgba(225,37,27,.15); color:var(--jd); }}
    .platform-badge.tmall {{ background:rgba(255,68,0,.15);  color:var(--tmall); }}
    .count-badge {{ font-size: 11px; color: var(--muted); }}
    .scroll-x {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    .products-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      min-width: 640px;
    }}
    .products-table th {{
      background: rgba(201,168,76,0.08);
      color: var(--gold);
      font-weight: 600;
      font-size: 11px;
      letter-spacing: .5px;
      padding: 8px 10px;
      text-align: left;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}
    .products-table td {{
      padding: 7px 10px;
      border-bottom: 1px solid rgba(201,168,76,0.06);
      vertical-align: middle;
    }}
    .products-table tr:hover td {{ background: rgba(201,168,76,0.04); }}
    .series-cell {{
      color: var(--gold-dim);
      font-size: 11px;
      font-weight: 600;
      white-space: nowrap;
      border-right: 1px solid var(--border);
      background: rgba(201,168,76,0.03);
    }}
    .name-cell {{ max-width: 260px; word-break: break-all; }}
    .num {{
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      color: var(--muted);
    }}
    .d875 {{ color: var(--gold); font-weight: 600; }}
    .warn-row .num {{ color: rgba(154,143,126,0.45); }}
    .note {{
      margin: 12px 0;
      padding: 10px 14px;
      background: rgba(201,168,76,0.06);
      border-left: 2px solid var(--gold-dim);
      border-radius: 0 6px 6px 0;
      font-size: 11px;
      color: var(--muted);
      line-height: 1.9;
    }}
    .no-data {{
      padding: 32px 24px;
      text-align: center;
      color: var(--muted);
      font-size: 13px;
      background: rgba(201,168,76,0.04);
      border: 1px dashed var(--border);
      border-radius: 8px;
      line-height: 1.8;
    }}
    .no-data-icon {{ font-size: 24px; margin-bottom: 8px; }}
    .no-data small {{ font-size: 11px; opacity: .7; }}
  </style>
</head>
<body>
<div class="header">
  <h1>老铺黄金 · 产品价格手册</h1>
  <div class="sub">天猫旗舰店 &amp; 京东旗舰店 · 在线商品汇总</div>
  <div class="update">📅 {generated_at} 更新 · 共 {total} 件商品</div>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('jd',this)">🛒 京东旗舰店</button>
  <button class="tab-btn" onclick="switchTab('tmall',this)">🛍 天猫旗舰店</button>
</div>

<div id="pane-jd" class="tab-pane active">
  <div class="note">
    💡 <strong>875折</strong>：老铺黄金官方会员折扣（8.75折），即标价 × 0.875。&nbsp;
    <strong>折合克</strong>：价格 ÷ 克重，用于横向对比性价比。<br>
    克重标注「—」表示商品名称中未检测到克重信息，可前往商品页手动确认。
  </div>
  {jd_table}
</div>

<div id="pane-tmall" class="tab-pane">
  <div class="note">
    💡 <strong>875折</strong>：老铺黄金官方会员折扣（8.75折），即标价 × 0.875。&nbsp;
    <strong>折合克</strong>：价格 ÷ 克重，用于横向对比性价比。<br>
    克重标注「—」表示商品名称中未检测到克重信息，可前往商品页手动确认。
  </div>
  {tmall_table}
</div>

<script>
function switchTab(id, btn) {{
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('pane-' + id).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════════
#  主流程
# ════════════════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    do_jd      = "--tmall-only" not in args
    do_tmall   = "--jd-only"    not in args
    headless   = "--headless"   in args   # 默认可见模式，更兼容

    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    print(f"[{now_str} CST] 老铺黄金产品爬虫启动")
    if not headless:
        print("  [模式] 可见浏览器 — 如平台需要登录，请在弹出的 Chrome 窗口完成操作\n")

    products: list = []

    if do_jd:
        print("[1] 爬取京东旗舰店...")
        jd = scrape_jd(headless=headless)
        print(f"    → 京东：去重后 {len(jd)} 件商品")
        products += jd

    if do_tmall:
        step = "2" if do_jd else "1"
        print(f"\n[{step}] 爬取天猫旗舰店...")
        tm = scrape_tmall(headless=headless)
        print(f"    → 天猫：去重后 {len(tm)} 件商品")
        products += tm

    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M")

    if not products:
        print(
            "\n⚠️  未获取到任何产品数据。\n"
            "原因：天猫/京东检测到自动化访问，要求用户登录。\n\n"
            "解决方案：\n"
            "  1. 确保您已在 Chrome 中登录淘宝/天猫账号\n"
            "  2. 确保您已在 Chrome 中登录京东账号\n"
            "  3. 重新运行此脚本（默认可见模式，可在弹窗中手动登录）\n"
            "  4. 或手动将商品数据填写到 products.json 后运行 python3 scrape_laopu_products.py --generate-html\n"
        )
    else:
        payload = {
            "generated_at": now_str,
            "total":        len(products),
            "products":     products,
        }
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n✅ JSON 已保存至 {OUT_JSON}")

    # 无论是否有数据，都生成 HTML（有数据则显示，无数据则显示提示）
    html = build_html(products, now_str)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML 已保存至 {OUT_HTML}")

    if products:
        # 终端预览
        print(f"\n── 产品摘要 {'─'*40}")
        print(f"{'系列':<16} {'名称':<30} {'克重':>6}  {'标价':>8}  {'克价':>6}")
        print("─" * 74)
        for p in sorted(products, key=lambda x: (x["series"], x["name"]))[:30]:
            w  = f"{p['weight']}g" if p["weight"] else "—"
            pg = str(p.get("price_per_g") or "—")
            print(
                f"{p['series']:<16} {p['name'][:28]:<30} {w:>6}  "
                f"{int(p['price']):>8,}  {pg:>6}"
            )
        if len(products) > 30:
            print(f"  ... 还有 {len(products)-30} 件，见 {OUT_HTML}")

    print(f"\n[完成] {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} CST")


if __name__ == "__main__":
    # 如果只是生成 HTML（已有 products.json）
    if "--generate-html" in sys.argv:
        try:
            with open(OUT_JSON, encoding="utf-8") as f:
                data = json.load(f)
            products = data.get("products", [])
            now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
            html = build_html(products, now_str)
            with open(OUT_HTML, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"✅ HTML 已从 {OUT_JSON} 重新生成，保存至 {OUT_HTML}")
        except FileNotFoundError:
            print(f"❌ {OUT_JSON} 不存在，请先运行爬虫")
    else:
        main()
