#!/usr/bin/env python3
"""
老铺黄金 · 全球买金专员手册  ·  自动数据更新脚本

数据来源：
  市场数据  → yfinance（金价 / 汇率 / 6181.HK）
  财经新闻  → yfinance 6181.HK + 东方财富 API + 新浪财经搜索
  社媒动态  → 微博搜索 + 搜狗微信（公众号索引）+ 小红书（Playwright 无头浏览器）

定时运行：
  .github/workflows/update-intel.yml  每日 18:00 CST（10:00 UTC）自动触发
  手动运行：python generate_intel.py
"""

import os
import re
import html as html_lib
from datetime import datetime, timezone, timedelta

# ── 全局常量 ──────────────────────────────────────────────────────────────────

CST = timezone(timedelta(hours=8))

KEYWORDS_ADJUST  = ["调价", "涨价", "提价", "降价", "价格调整", "上调", "下调"]
KEYWORDS_PROMO   = ["促销", "大促", "优惠", "折扣", "满减", "活动", "专场", "限时", "秒杀"]
KEYWORDS_FINANCE = ["财报", "业绩", "营收", "利润", "IPO", "股东", "股权", "分红", "回购", "评级"]

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# ════════════════════════════════════════════════════════════════════════════
#  一、市场数据
# ════════════════════════════════════════════════════════════════════════════

def fetch_market_data() -> dict:
    """通过 yfinance 获取金价、汇率、6181.HK 股价"""
    try:
        import yfinance as yf

        def _close(ticker_str, period="5d"):
            h = yf.Ticker(ticker_str).history(period=period)
            if h.empty:
                raise ValueError(f"{ticker_str} 无数据")
            return h["Close"].dropna()

        gold_s   = _close("GC=F")
        cny_s    = _close("USDCNY=X")
        hk_s     = _close("6181.HK")

        gold_price  = gold_s.iloc[-1]
        gold_prev   = gold_s.iloc[-2] if len(gold_s) >= 2 else gold_price
        gold_change = (gold_price - gold_prev) / gold_prev * 100

        usdcny = cny_s.iloc[-1]

        hk_price  = hk_s.iloc[-1]
        hk_prev   = hk_s.iloc[-2] if len(hk_s) >= 2 else hk_price
        hk_change = (hk_price - hk_prev) / hk_prev * 100

        return {
            "gold_spot":   f"{gold_price:,.0f}",
            "gold_change": gold_change,
            "gold_note":   ("本周持续上涨" if gold_change >= 1 else
                            "小幅上涨"     if gold_change >= 0 else
                            "小幅回调"     if gold_change >= -1 else "明显回调"),
            "gold_cny":    f"{gold_price * usdcny / 31.1035:,.0f}",
            "usd_cny":     f"{usdcny:.4f}",
            "hk_price":    f"{hk_price:,.1f}",
            "hk_change":   f"{hk_change:+.2f}",
            "hk_color":    "green" if hk_change >= 0 else "red",
            "error":       None,
        }

    except Exception as e:
        print(f"  [WARN] 市场数据获取失败：{e}")
        return {
            "gold_spot": "获取中", "gold_change": 0, "gold_note": "请稍后刷新",
            "gold_cny": "—", "usd_cny": "—", "hk_price": "—",
            "hk_change": "—", "hk_color": "neutral", "error": str(e),
        }


# ════════════════════════════════════════════════════════════════════════════
#  二、财经新闻（3 个来源 → 注入「价格情报」和「门店促销」Tab）
# ════════════════════════════════════════════════════════════════════════════

def _make_news_item(title, source, link, pub_dt, channel) -> dict:
    return {"title": title, "source": source, "link": link,
            "pub_dt": pub_dt, "channel": channel, "category": classify_text(title)}


def fetch_yfinance_news() -> list:
    try:
        import yfinance as yf
        raw = yf.Ticker("6181.HK").news or []
        items = []
        for n in raw[:15]:
            title = n.get("title", "").strip()
            if not title:
                continue
            ts = n.get("providerPublishTime", 0)
            pub = datetime.fromtimestamp(ts, tz=CST) if ts else None
            items.append(_make_news_item(title, n.get("publisher", "Yahoo Finance"),
                                         n.get("link", ""), pub, "yfinance"))
        print(f"  yfinance 新闻：{len(items)} 条")
        return items
    except Exception as e:
        print(f"  [WARN] yfinance 新闻：{e}")
        return []


def fetch_eastmoney_news() -> list:
    try:
        import requests
        url = ("https://np-listapi.eastmoney.com/comm/web/getListInfo"
               "?client=web&type=1&mTypeAndCode=128.6181&pageSize=10&pageIndex=1")
        data = requests.get(url, headers={"User-Agent": HEADERS_BROWSER["User-Agent"],
                                          "Referer": "https://quote.eastmoney.com/"},
                            timeout=10).json()
        items = []
        for art in (data.get("data", {}) or {}).get("list", []):
            title = art.get("title", "").strip()
            if not title:
                continue
            pub_str = art.get("publishTime", "") or art.get("ctime", "")
            try:
                pub = datetime.fromisoformat(pub_str.replace("T", " ").split("+")[0])
                pub = pub.replace(tzinfo=CST)
            except Exception:
                pub = None
            items.append(_make_news_item(title, art.get("mediaName", "东方财富"),
                                         art.get("url", ""), pub, "eastmoney"))
        print(f"  东方财富 新闻：{len(items)} 条")
        return items
    except Exception as e:
        print(f"  [WARN] 东方财富：{e}")
        return []


def fetch_sina_finance_news() -> list:
    try:
        import requests
        from bs4 import BeautifulSoup
        url = ("https://search.sina.com.cn/?q=%E8%80%81%E9%93%BA%E9%BB%84%E9%87%91"
               "&range=all&c=news&sort=time&num=10")
        resp = requests.get(url, headers=HEADERS_BROWSER, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []
        for div in soup.select(".box-result")[:10]:
            a = div.select_one("h2 a") or div.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            link  = a.get("href", "")
            t_tag = div.select_one(".fgray_time")
            pub_str = t_tag.get_text(strip=True) if t_tag else ""
            try:
                pub = datetime.strptime(pub_str[:16], "%Y年%m月%d日%H:%M").replace(tzinfo=CST)
            except Exception:
                pub = None
            items.append(_make_news_item(title, "新浪财经", link, pub, "sina"))
        print(f"  新浪财经 新闻：{len(items)} 条")
        return items
    except Exception as e:
        print(f"  [WARN] 新浪财经：{e}")
        return []


# ════════════════════════════════════════════════════════════════════════════
#  三、社媒动态（3 个来源 → 注入「社媒动态」Tab）
# ════════════════════════════════════════════════════════════════════════════

def _make_social_item(platform, title, preview, source, link, pub_dt,
                      stats=None) -> dict:
    return {
        "platform": platform,       # "xhs" | "weibo" | "weixin"
        "title":    title,
        "preview":  preview,
        "source":   source,
        "link":     link,
        "pub_dt":   pub_dt,
        "stats":    stats or {},
        "category": classify_text(title + " " + preview),
    }


# ── 微博 ──────────────────────────────────────────────────────────────────────

def fetch_weibo(keyword: str = "老铺黄金", max_items: int = 10) -> list:
    """
    微博搜索（无需登录，结果有限）
    - 有效内容：热门讨论、买家晒单、调价话题
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        import urllib.parse

        url = (f"https://s.weibo.com/weibo?q={urllib.parse.quote(keyword)}"
               "&typeall=1&suball=1&Refer=g")
        headers = {**HEADERS_BROWSER,
                   "Referer": "https://weibo.com/",
                   "Cookie":  ""}  # 无 Cookie 仍可获取部分公开帖
        resp = requests.get(url, headers=headers, timeout=12)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        items = []
        for card in soup.select(".card-wrap")[:max_items]:
            txt_el = card.select_one(".txt")
            if not txt_el:
                continue
            content = txt_el.get_text(separator=" ", strip=True)
            from_el = card.select_one(".from a")
            link    = ""
            pub     = None
            if from_el:
                raw_link = from_el.get("href", "")
                link = ("https:" + raw_link) if raw_link.startswith("//") else raw_link
                # 时间文本通常是 "X分钟前" / "X月X日"
            # 作者
            author_el = card.select_one(".name")
            author = author_el.get_text(strip=True) if author_el else "微博用户"
            # 转发/赞
            reposts = card.select_one(".pos .morepop_count")
            stats = {}

            title   = content[:40] + ("…" if len(content) > 40 else "")
            preview = content[:120]

            items.append(_make_social_item(
                "weibo", title, preview, f"@{author}", link, pub, stats
            ))

        print(f"  微博：{len(items)} 条")
        return items
    except Exception as e:
        print(f"  [WARN] 微博：{e}")
        return []


# ── 搜狗微信（公众号文章索引）────────────────────────────────────────────────

def fetch_sogou_weixin(keyword: str = "老铺黄金", max_items: int = 10) -> list:
    """
    搜狗微信搜索——索引微信公众号文章，品牌官方公告 / KOL 测评均在此
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        import urllib.parse

        url = (f"https://weixin.sogou.com/weixin?type=2"
               f"&query={urllib.parse.quote(keyword)}&ie=utf8")
        headers = {**HEADERS_BROWSER, "Referer": "https://weixin.sogou.com/"}
        resp = requests.get(url, headers=headers, timeout=12)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        items = []
        for art in soup.select(".news-box .news-list li")[:max_items]:
            title_el   = art.select_one("h3 a")
            preview_el = art.select_one("p.txt-info")
            account_el = art.select_one(".account")
            time_el    = art.select_one(".s-p ~ span") or art.select_one("span.s-p")
            if not title_el:
                continue
            title   = title_el.get_text(strip=True)
            raw_link = title_el.get("href", "")
            # 搜狗微信链接为相对路径 /link?url=...，补全为绝对 URL
            if raw_link.startswith("/link?"):
                link = "https://weixin.sogou.com" + raw_link
            elif raw_link.startswith("http"):
                link = raw_link
            else:
                link = ""   # 无效链接直接丢弃
            preview = smart_summary(preview_el.get_text(strip=True) if preview_el else "", 50)
            account = account_el.get_text(strip=True) if account_el else "微信公众号"
            pub_str = time_el.get_text(strip=True) if time_el else ""
            try:
                pub = datetime.strptime(pub_str[:10], "%Y-%m-%d").replace(tzinfo=CST)
            except Exception:
                pub = None

            items.append(_make_social_item(
                "weixin", title, preview, account, link, pub
            ))

        print(f"  搜狗微信：{len(items)} 条")
        return items
    except Exception as e:
        print(f"  [WARN] 搜狗微信：{e}")
        return []


# ── 小红书（Playwright + 弹窗关闭，GitHub Actions 专用）────────────────────

def fetch_xiaohongshu(keyword: str = "老铺黄金", max_items: int = 10) -> list:
    """
    小红书笔记搜索（Playwright 无头浏览器）
    策略：加载搜索页 → 强制关掉登录弹窗 → 提取已渲染的卡片
    在 GitHub Actions（US IP）环境下可获取初始搜索结果。
    本地中国 IP 受限时自动降级，返回空列表。
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        import urllib.parse

        search_url = (
            "https://www.xiaohongshu.com/search_result"
            f"?keyword={urllib.parse.quote(keyword)}&type=51&source=web_search_result_notes"
        )

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=VizDisplayCompositor",
                    "--lang=zh-CN",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
            )
            # 屏蔽 webdriver 特征
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
                window.chrome = {runtime: {}};
            """)
            page = context.new_page()

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=25000)

                # 等一会儿让内容加载
                page.wait_for_timeout(3000)

                # 关闭登录弹窗（多种 selector 兼容）
                for close_sel in [
                    ".login-container .close",
                    "[class*='login'] [class*='close']",
                    "[class*='modal'] [class*='close']",
                    ".close-button",
                    "button[aria-label='Close']",
                    ".overlay .close",
                    "[data-v-close]",
                ]:
                    try:
                        btn = page.query_selector(close_sel)
                        if btn and btn.is_visible():
                            btn.click()
                            page.wait_for_timeout(800)
                            break
                    except Exception:
                        pass

                # 按 Escape 也能关掉部分弹窗
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)

                # 等待笔记卡片
                card_sel = None
                for sel in ["section.note-item", "div.note-item",
                            "[class*='NoteItem']", ".feeds-page .note-item",
                            ".search-feed-item", "[data-note-id]"]:
                    try:
                        page.wait_for_selector(sel, timeout=5000)
                        card_sel = sel
                        break
                    except PWTimeout:
                        pass

                if not card_sel:
                    print("  小红书：未找到笔记卡片（可能需要登录）")
                    return []

                # 抓更多卡片，过滤后仍能保留足够数量
                cards = page.query_selector_all(card_sel)[:max_items * 4]
                items = []
                for card in cards:
                    if len(items) >= max_items:
                        break
                    try:
                        title_el = (
                            card.query_selector("span.title")
                            or card.query_selector(".footer span.title")
                            or card.query_selector("[class*='title']")
                        )
                        title = title_el.inner_text().strip() if title_el else ""
                        if not title:
                            continue

                        link_el = (card.query_selector("a[href*='/explore/']")
                                   or card.query_selector("a"))
                        raw_link = link_el.get_attribute("href") if link_el else ""
                        link = ("https://www.xiaohongshu.com" + raw_link
                                if raw_link.startswith("/") else raw_link)

                        author_el = (card.query_selector(".author span")
                                     or card.query_selector(".nickname"))
                        author = author_el.inner_text().strip() if author_el else ""

                        like_el = (card.query_selector(".like-wrapper .count")
                                   or card.query_selector("[class*='like'] [class*='count']"))
                        likes = like_el.inner_text().strip() if like_el else ""

                        # 关键词过滤：确保内容与老铺黄金相关
                        combined = title + " " + author
                        if not any(kw in combined for kw in ["老铺黄金", "老铺", "黄金", "古法金"]):
                            continue

                        summary = smart_summary(title, 50)
                        items.append(_make_social_item(
                            "xhs", title, summary,
                            "小红书", link, None,
                            {"likes": likes} if likes else {},
                        ))
                    except Exception:
                        continue

                # 按热门（点赞数）降序排列，取 top6
                items.sort(key=lambda x: parse_likes(x["stats"].get("likes", "")), reverse=True)
                items = items[:6]
                print(f"  小红书：{len(items)} 条（过滤+热门排序）")
                return items

            finally:
                browser.close()

    except ImportError:
        print("  [INFO] 小红书：playwright 未安装，跳过")
        return []
    except Exception as e:
        print(f"  [WARN] 小红书：{e}")
        return []


# ── 小红书备用：搜狗搜索 XHS 相关内容 ─────────────────────────────────────

def fetch_xhs_via_sogou(keyword: str = "老铺黄金 小红书", max_items: int = 6) -> list:
    """
    当 Playwright 抓不到 XHS 内容时的备用方案：
    搜狗网页搜索 '老铺黄金 小红书'，返回提到小红书的文章
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        import urllib.parse

        url = f"https://www.sogou.com/web?query={urllib.parse.quote(keyword)}&num=10"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.sogou.com/",
        }
        resp = requests.get(url, headers=headers, timeout=12)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        items = []
        for r in soup.select(".vrwrap"):
            if len(items) >= max_items:
                break
            a = r.select_one("h3 a") or r.select_one("a[href]")
            snippet_el = r.select_one(".str_info") or r.select_one("p")
            if not a:
                continue
            title   = a.get_text(strip=True)
            raw_link = a.get("href", "")
            if raw_link.startswith("/link?"):
                link = "https://www.sogou.com" + raw_link
            elif raw_link.startswith("http"):
                link = raw_link
            else:
                continue   # ?user_ip=... 等无效链接直接跳过
            raw_preview = snippet_el.get_text(strip=True) if snippet_el else ""
            if not title:
                continue
            # 过滤：标题或摘要必须包含「老铺黄金」
            if "老铺黄金" not in title and "老铺黄金" not in raw_preview:
                continue
            # 50 字以内精炼摘要；若搜索摘要为空则从标题提取
            preview = smart_summary(raw_preview, 50) or smart_summary(title, 50)
            items.append(_make_social_item(
                "xhs", title, preview, "小红书·搜狗索引", link, None
            ))

        print(f"  小红书备用（搜狗）：{len(items)} 条")
        return items

    except Exception as e:
        print(f"  [WARN] 小红书备用：{e}")
        return []


# ════════════════════════════════════════════════════════════════════════════
#  四、通用工具
# ════════════════════════════════════════════════════════════════════════════

def parse_likes(s: str) -> int:
    """将 '8.9万' / '475' / '2.9万' 统一转为整数，用于热门排序"""
    if not s:
        return 0
    s = s.strip().replace(",", "")
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        return int(s)
    except ValueError:
        return 0


def smart_summary(text: str, max_len: int = 50) -> str:
    """
    从文章摘要/标题中提取不超过 max_len 个汉字的关键信息：
    - 去除日期前缀（"6天前 -"、"2年前 -"、"2025年3月2日 -" 等）
    - 去除尾部来源标签（"_品牌_市场"、"|腾讯新闻" 等）
    - 尽量在句号/逗号处截断，保持语义完整
    """
    if not text:
        return ""
    text = text.strip()
    # 去除时间前缀（支持 天/小时/分钟/月/年 前）
    text = re.sub(r"^\d{4}年\d+月\d+日\s*[-·]\s*", "", text)
    text = re.sub(r"^\d+\s*[天小时分钟月年]+前\s*[-·]\s*", "", text)
    # 去除尾部所有 _xxx 或 |xxx 式来源/分类标签（可能有多个）
    text = re.sub(r"[_|][^_|。！？，\n]+$", "", text)
    text = re.sub(r"([_|][^_|。！？，\n]+)+$", "", text)
    # 去除末尾 "-来源" 形式（如 "-今日头条"）
    text = re.sub(r"\s*[-–—]\s*[\u4e00-\u9fa5a-zA-Z]{2,10}$", "", text)
    # 去除省略号末尾
    text = re.sub(r"\.{3,}$|…+$", "", text)
    text = text.strip("_|… \t")
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    # 优先在标点处截断，保持句意完整（含英文逗号/句号）
    for punct in ["。", "！", "？", "；", "，", "、", ",", "."]:
        idx = text[:max_len].rfind(punct)
        if idx > max_len // 3:
            return text[: idx + 1]
    return text[:max_len] + "…"


def classify_text(text: str) -> str:
    t = text.lower()
    if any(kw in t for kw in KEYWORDS_ADJUST):  return "adjust"
    if any(kw in t for kw in KEYWORDS_PROMO):   return "promo"
    if any(kw in t for kw in KEYWORDS_FINANCE): return "finance"
    return "general"


def merge_dedupe(sources: list[list], key_len: int = 20) -> list:
    """合并多源、按标题前N字去重、按时间倒序"""
    seen, merged = set(), []
    for src in sources:
        for item in src:
            key = item["title"][:key_len]
            if key not in seen:
                seen.add(key)
                merged.append(item)
    merged.sort(
        key=lambda x: x.get("pub_dt") or datetime.min.replace(tzinfo=CST),
        reverse=True,
    )
    return merged


def esc(text: str) -> str:
    """HTML 转义（防 XSS）"""
    return html_lib.escape(str(text))


def rel_time(dt) -> str:
    """将 datetime 转为相对时间字符串"""
    if not dt:
        return "—"
    now = datetime.now(CST)
    diff = now - dt.astimezone(CST)
    minutes = int(diff.total_seconds() / 60)
    if minutes < 1:   return "刚刚"
    if minutes < 60:  return f"{minutes}分钟前"
    hours = minutes // 60
    if hours < 24:    return f"{hours}小时前"
    days = hours // 24
    if days < 7:      return f"{days}天前"
    return dt.astimezone(CST).strftime("%m-%d")


# ════════════════════════════════════════════════════════════════════════════
#  五、HTML 片段构建
# ════════════════════════════════════════════════════════════════════════════

# ── 财经新闻 → 价格/促销 Tab ──────────────────────────────────────────────

TAG_MAP = {
    "adjust":  '<span class="news-tag news-tag-adjust">⚡ 调价</span>',
    "promo":   '<span class="news-tag news-tag-promo">🎁 促销</span>',
    "finance": '<span class="news-tag news-tag-finance">📊 财务</span>',
    "general": '<span class="news-tag news-tag-general">📰 资讯</span>',
}


def build_alert_bar_text(news: list) -> str:
    adj   = [n for n in news if n["category"] == "adjust"]
    promo = [n for n in news if n["category"] == "promo"]
    if adj:
        return f"⚡ {esc(adj[0]['title'][:30])} · 点击「价格情报」查看详情"
    if promo:
        return f"🎁 {esc(promo[0]['title'][:30])} · 点击「门店促销」查看详情"
    if news:
        return f"📰 最新：{esc(news[0]['title'][:28])}"
    return f"金价数据已更新 · {datetime.now(CST).strftime('%Y-%m-%d %H:%M')} CST"


def build_price_alert_card(news: list, market: dict) -> str:
    adj = [n for n in news if n["category"] == "adjust"]
    now = datetime.now(CST)
    if adj:
        rows = []
        for n in adj[:3]:
            dt_str = n["pub_dt"].strftime("%m-%d %H:%M") if n["pub_dt"] else "—"
            link   = esc(n.get("link", ""))
            t      = (f'<a href="{link}" target="_blank" style="color:#E74C3C;'
                      f'text-decoration:none">{esc(n["title"])}</a>'
                      if link else esc(n["title"]))
            rows.append(f'<strong>⚡ {t}</strong><br>'
                        f'<span style="font-size:10px;color:rgba(231,76,60,0.7)">'
                        f'来源：{esc(n["source"])} · {dt_str}</span>')
        return ('<div class="alert-card">' + "<br><br>".join(rows) + '</div>')

    gc = market.get("gold_change", 0)
    if abs(gc) >= 2:
        msg = (f'金价今日{"上涨" if gc > 0 else "下跌"} {abs(gc):.1f}%，'
               f'{"关注是否触发品牌调价。" if gc > 0 else "暂无调价信号。"}')
        return (f'<div class="alert-card"><strong>📊 金价动态</strong><br>{msg}<br>'
                f'<span style="font-size:10px;color:rgba(231,76,60,0.7)">'
                f'自动监测 · {now.strftime("%Y-%m-%d %H:%M")} CST</span></div>')
    return ""


def build_promo_alert_block(news: list) -> str:
    adj     = [n for n in news if n["category"] == "adjust"]
    promo   = [n for n in news if n["category"] == "promo"]
    others  = [n for n in news if n["category"] in ("finance", "general")][:8]
    now     = datetime.now(CST)
    cards   = []

    def _news_card(items, color_hex, bg_alpha, title_emoji, label):
        if not items:
            return ""
        rows = []
        for n in items[:2]:
            dt = n["pub_dt"].strftime("%m-%d %H:%M") if n["pub_dt"] else "—"
            lnk = esc(n.get("link", ""))
            t   = (f'<a href="{lnk}" target="_blank" style="color:{color_hex};'
                   f'text-decoration:none">{esc(n["title"])}</a>'
                   if lnk else esc(n["title"]))
            rows.append(f'{t}<br><span style="font-size:10px;color:rgba'
                        f'({color_hex[1:3]},{color_hex[3:5]},{color_hex[5:]},0.55);">'
                        f'来源：{esc(n["source"])} · {dt}</span>')
        return (
            f'<div style="margin:0 16px 10px;background:rgba{bg_alpha};'
            f'border:1px solid rgba{bg_alpha.replace("0.07","0.25")};'
            f'border-radius:10px;padding:13px 15px;font-size:13px;'
            f'color:{color_hex};line-height:1.85">'
            f'<strong>{title_emoji} {label}</strong><br>'
            + "<br><br>".join(rows) + '</div>'
        )

    cards.append(_news_card(adj,   "#E74C3C", "(192,57,43,0.07)",  "⚡", "调价动态"))
    cards.append(_news_card(promo, "#2ECC71", "(46,204,113,0.07)", "🎁", "促销动态"))

    if others:
        rows_html = ""
        for n in others:
            dt  = n["pub_dt"].strftime("%m-%d %H:%M") if n["pub_dt"] else "—"
            tag = TAG_MAP.get(n["category"], TAG_MAP["general"])
            lnk = esc(n.get("link", ""))
            t   = (f'<a href="{lnk}" target="_blank">{esc(n["title"])}</a>'
                   if lnk else esc(n["title"]))
            rows_html += (
                f'<div class="news-item">'
                f'<div class="news-item-head">'
                f'<div class="news-item-title">{tag}{t}</div>'
                f'<div class="news-item-meta">{dt}</div>'
                f'</div>'
                f'<div style="font-size:10px;color:var(--gold-dim)">{esc(n["source"])}</div>'
                f'</div>'
            )
        cards.append(
            f'<div class="news-feed">'
            f'<div class="news-feed-title">📡 自动追踪 · 老铺黄金最新资讯 '
            f'<span style="float:right;font-weight:400">{now.strftime("%m-%d %H:%M")} 更新</span></div>'
            + rows_html + '</div>'
        )

    result = "\n".join(c for c in cards if c)
    return result or (
        '<div style="margin:0 16px 10px;padding:12px 15px;background:rgba(154,143,126,0.07);'
        'border-radius:10px;font-size:12px;color:var(--gold-dim);text-align:center">'
        '暂未获取到最新资讯，请稍后刷新</div>'
    )


# ── 社媒动态 → 社媒 Tab ──────────────────────────────────────────────────

PLATFORM_META = {
    "xhs":    ("📕 小红书", "xhs"),
    "weibo":  ("🔵 微博",   "weibo"),
    "weixin": ("💚 微信",   "weixin"),
}

SP_TAG_MAP = {
    "adjust":  '<span class="sp-tag sp-tag-adjust">⚡ 调价</span>',
    "promo":   '<span class="sp-tag sp-tag-promo">🎁 促销</span>',
    "general": "",
    "finance": "",
}


def build_social_tab_html(social_items: list) -> str:
    if not social_items:
        return (
            '<div class="social-empty">'
            '暂未抓取到社媒内容<br>'
            '<span style="font-size:10px">可能原因：网络超时 / 平台访问限制</span>'
            '</div>'
        )

    parts = []
    now   = datetime.now(CST)

    for item in social_items:
        platform = item.get("platform", "weibo")
        label, css_cls = PLATFORM_META.get(platform, ("📰", "weibo"))
        title   = esc(item.get("title", ""))
        preview = esc(item.get("preview", ""))
        source  = esc(item.get("source", ""))
        link    = esc(item.get("link", ""))
        stats   = item.get("stats", {})
        cat_tag = SP_TAG_MAP.get(item.get("category", "general"), "")
        time_str = rel_time(item.get("pub_dt"))

        title_html = (
            f'<a class="sp-title" href="{link}" target="_blank">{cat_tag}{title}</a>'
            if link else f'<span class="sp-title">{cat_tag}{title}</span>'
        )
        likes_html = (f'❤️ {esc(stats["likes"])}' if stats.get("likes") else "")
        link_html  = (f'<a class="sp-link" href="{link}" target="_blank">查看原文 →</a>'
                      if link else "")

        parts.append(
            f'<div class="social-post" data-platform="{css_cls}">'
            f'<div class="sp-header">'
            f'<span class="sp-platform {css_cls}">{label}</span>'
            f'<span class="sp-time">{time_str}</span>'
            f'</div>'
            f'{title_html}'
            + (f'<div class="sp-preview">{preview}</div>' if preview else "")
            + f'<div class="sp-footer">'
            f'<div class="sp-stats">'
            + (likes_html if likes_html else f'<span style="opacity:.5">{source}</span>')
            + f'</div>'
            + link_html
            + f'</div>'
            f'</div>'
        )

    update_str = now.strftime("%m-%d %H:%M")
    header = (
        f'<div style="margin:0 16px 8px;font-size:10px;color:var(--gold-dim)">'
        f'共 {len(social_items)} 条 · {update_str} 更新 · '
        f'来源：小红书 / 微博 / 微信公众号</div>'
    )
    return header + "\n".join(parts)


# ════════════════════════════════════════════════════════════════════════════
#  六、HTML 最终生成
# ════════════════════════════════════════════════════════════════════════════

def generate_html(market: dict, news: list, social: list) -> str:
    tpl_path = os.path.join(os.path.dirname(__file__), "laopu-intel.html")
    with open(tpl_path, "r", encoding="utf-8") as f:
        page = f.read()

    now_cst = datetime.now(CST)
    replacements = {
        "{{GOLD_SPOT}}":   f"${market['gold_spot']}",
        "{{GOLD_NOTE}}":   market["gold_note"],
        "{{GOLD_CNY}}":    market["gold_cny"],
        "{{USD_CNY}}":     market["usd_cny"],
        "{{HK_PRICE}}":    market["hk_price"],
        "{{HK_CHANGE}}":   market["hk_change"],
        "{{HK_COLOR}}":    market["hk_color"],
        "{{UPDATE_DATE}}": now_cst.strftime("%Y-%m-%d"),
        "{{UPDATE_TIME}}": now_cst.strftime("%H:%M"),
        "{{ALERT_BAR_TEXT}}":    build_alert_bar_text(news),
        "{{PRICE_ALERT_CARD}}":  build_price_alert_card(news, market),
        "{{PROMO_ALERT_BLOCK}}": build_promo_alert_block(news),
        "{{SOCIAL_TAB_CONTENT}}": build_social_tab_html(social),
    }
    for k, v in replacements.items():
        page = page.replace(k, str(v))

    page = re.sub(r"\{\{[A-Z_]+\}\}", "—", page)
    return page


# ════════════════════════════════════════════════════════════════════════════
#  七、主流程
# ════════════════════════════════════════════════════════════════════════════

def main():
    now_cst = datetime.now(CST)
    print(f"[{now_cst.strftime('%Y-%m-%d %H:%M:%S')} CST] 开始生成老铺黄金情报页面...")

    # ── 1. 市场数据 ──────────────────────────────────────────────────────────
    print("\n[1/4] 获取市场价格数据...")
    market = fetch_market_data()
    if not market["error"]:
        print(f"  伦敦金    : ${market['gold_spot']}/oz  ({market['gold_change']:+.2f}%)")
        print(f"  上海金估算 : ¥{market['gold_cny']}/g")
        print(f"  USD/CNY   : {market['usd_cny']}")
        print(f"  6181.HK   : HK${market['hk_price']}  ({market['hk_change']}%)")

    # ── 2. 财经新闻 ──────────────────────────────────────────────────────────
    print("\n[2/4] 抓取财经新闻...")
    news = merge_dedupe([
        fetch_yfinance_news(),
        fetch_eastmoney_news(),
        fetch_sina_finance_news(),
    ])
    cats = {k: sum(1 for n in news if n["category"] == k)
            for k in ("adjust", "promo", "finance", "general")}
    print(f"  合并去重后 {len(news)} 条：调价 {cats['adjust']} | 促销 {cats['promo']} | "
          f"财务 {cats['finance']} | 资讯 {cats['general']}")

    # ── 3. 社媒动态 ──────────────────────────────────────────────────────────
    print("\n[3/4] 抓取社媒动态...")
    xhs_items = fetch_xiaohongshu()
    if not xhs_items:
        print("  小红书 Playwright 未获取到内容，切换备用搜狗索引...")
        xhs_items = fetch_xhs_via_sogou()
    social = merge_dedupe([
        fetch_weibo(),
        fetch_sogou_weixin(),
        xhs_items,
    ])
    by_platform = {p: sum(1 for s in social if s["platform"] == p)
                   for p in ("xhs", "weibo", "weixin")}
    print(f"  合并去重后 {len(social)} 条："
          f"小红书 {by_platform['xhs']} | 微博 {by_platform['weibo']} | 微信 {by_platform['weixin']}")

    # ── 4. 生成 HTML ─────────────────────────────────────────────────────────
    print("\n[4/4] 生成 index.html...")
    page = generate_html(market, news, social)
    out  = os.path.join(os.path.dirname(__file__), "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"  ✅ index.html 已生成（{len(page):,} 字节）")
    print(f"\n[完成] {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} CST")


if __name__ == "__main__":
    main()
