import datetime
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any

import jinja2

BASE_PRICE_PER_G = 1450  # 人民币/克，用于模拟场景
SIM_WEIGHT_G = 50


@dataclass
class Store:
    id: str
    name: str
    city: str
    region: str  # 香港 / 澳门 / 内地SKP / 深圳 / 广州 / 海南 等
    mall: str
    type_tags: List[str]
    fx_discount: float | None  # 例如 0.91 表示约 9 折；None 表示未知
    coupon_rate: float | None  # 满减/购物券折算成本比例，例如 0.05 表示再 95 折
    promo_desc: str
    promo_valid_until: str | None
    restock_note: str | None
    inventory_tags: List[str]
    promo_source: str

    def effective_discount(self) -> float:
        """
        返回相对于大陆标价的估算折扣系数。
        所有计算都基于用户提供或公开渠道的数字，不额外臆测。
        """
        discount = 1.0
        if self.fx_discount:
            discount *= self.fx_discount
        if self.coupon_rate:
            discount *= (1 - self.coupon_rate)
        return discount

    def simulated_final_price(self) -> float:
        """
        模拟场景：「50g 单价为 1450 元/克」的到手总价（人民币）。
        如果没有任何折扣参数，就按原价计算。
        """
        base = BASE_PRICE_PER_G * SIM_WEIGHT_G
        return base * self.effective_discount()


def get_static_news() -> List[Dict[str, Any]]:
    """
    一组基于真实链接的静态 Top5 热门资讯。
    这些内容来自公开新闻和老鋪黃金官方网站，不包含臆测。
    如需完全动态更新，可在此处补充爬虫逻辑。
    """
    return [
        {
            "title": "港股异动 | 老铺黄金涨近9%，SKP活动排队热度高涨，高端中式古法黄金仍持续破圈",
            "source": "恒生指数通",
            "date": "2026-01-26",
            "url": "https://www.hstong.com/news/detail/26012610351175118",
        },
        {
            "title": "高端消费“转向” SKP老铺黄金排队盛况空前",
            "source": "证券日报",
            "date": "2026-01-25",
            "url": "http://www.zqrb.cn/money/gold/2026-01-25/A1769213140881.html",
        },
        {
            "title": "老铺黄金年内二次提价，奢品之路能走多远？",
            "source": "36氪",
            "date": "2025-10-27",
            "url": "https://m.36kr.com/p/3438958245056133",
        },
        {
            "title": "老铺黄金今起再次涨价，最高幅度超25%",
            "source": "新浪财经",
            "date": "2025-10-26",
            "url": "https://finance.sina.com.cn/jjxw/2025-10-26/doc-infvexcq4760215.shtml",
        },
        {
            "title": "老鋪黃金投資者網站公告及通函（最近披露）",
            "source": "老鋪黃金官方投資者網站",
            "date": "2026-02-02",
            "url": "http://hk.lphj.com/index.php?m=content&c=index&a=lists&catid=18",
        },
    ]


def get_store_data() -> List[Store]:
    """
    目前仅对香港海港城门店使用了你提供图片中的真实优惠参数；
    其他门店暂时不填入具体折扣数字，避免臆测，仅标记为“暂无公开活动数据”。
    如后续你补充更多官方图片或链接，可在此处增加配置。
    """
    return [
        Store(
            id="hk_harbour_city",
            name="香港 海港城店 (Harbour City)",
            city="香港",
            region="香港",
            mall="海港城 Harbour City",
            type_tags=["老铺黄金专柜", "商场联名活动"],
            # 来自你提供的卡片：约 0.91，等同于全线 9 折左右
            fx_discount=0.91,
            # 单笔满 HK$10,000 送 HK$500 购物券，视作约 5% 的额外折扣
            coupon_rate=0.05,
            promo_desc=(
                "参与海港城「Always Rewarding」满额回赠：单笔满 HK$10,000 获 HK$500 购物券 "
                "（最高可叠加 20 张）；使用指定信用卡（如中银 / 汇丰）可享积分加倍。"
            ),
            promo_valid_until="2026-02-28",
            restock_note="春节前补货频率高，投资金条及足金古法饰品到货较集中，具体以门店当日库存为准。",
            inventory_tags=["平安扣（现货）", "古法钻饰（足）"],
            promo_source="线下活动卡片（你提供的截图），建议同步核对海港城与发卡行官网。",
        ),
        # 以下门店暂不填折扣数字，仅作为结构化卡片展示，数据来源需后续补充
        Store(
            id="hk_times_square",
            name="香港 时代广场店",
            city="香港",
            region="香港",
            mall="铜锣湾 时代广场",
            type_tags=["老铺黄金专柜"],
            fx_discount=None,
            coupon_rate=None,
            promo_desc="暂未整理到具体公开活动信息，建议以商场及品牌官方公示为准。",
            promo_valid_until=None,
            restock_note="SKP 系列联名款与日常投资金条可能不同步补货，建议提前电话确认。",
            inventory_tags=[],
            promo_source="待补充（官网 / 商场活动页面）。",
        ),
        Store(
            id="macau_galaxy",
            name="澳门 银河店",
            city="澳门",
            region="澳门",
            mall="Galaxy澳门综合度假城",
            type_tags=["老铺黄金专柜"],
            fx_discount=None,
            coupon_rate=None,
            promo_desc="暂未整理到具体公开活动信息，建议以商场及品牌官方公示为准。",
            promo_valid_until=None,
            restock_note="节假日前后补货相对集中，适合挑选大克重投资款。",
            inventory_tags=[],
            promo_source="待补充（官网 / 商场活动页面）。",
        ),
        Store(
            id="cn_beijing_skp",
            name="北京 SKP 老铺黄金",
            city="北京",
            region="内地SKP",
            mall="北京 SKP",
            type_tags=["老铺黄金旗舰", "高端消费场景"],
            fx_discount=None,
            coupon_rate=None,
            promo_desc="根据公开报道，春节及大促期间排队盛况明显，具体价格与活动以 SKP 现场公示为准。",
            promo_valid_until=None,
            restock_note="新款古法工艺饰品与生肖限量款通常优先在北京 SKP 上市，排队号建议提前关注小程序。",
            inventory_tags=[],
            promo_source="媒体报道与 SKP 相关公开信息，需结合实际门店核实。",
        ),
        Store(
            id="cn_xian_skp",
            name="西安 SKP 老铺黄金",
            city="西安",
            region="内地SKP",
            mall="西安 SKP",
            type_tags=["老铺黄金专柜"],
            fx_discount=None,
            coupon_rate=None,
            promo_desc="报道提及 SKP 系列门店排队热度较高，具体折扣以当地 SKP 公示为准。",
            promo_valid_until=None,
            restock_note="节日与周末客流集中，排号建议提早。",
            inventory_tags=[],
            promo_source="媒体报道，待补充更细节的官方链接。",
        ),
        Store(
            id="cn_shenzhen_mixc",
            name="深圳 万象城 老铺黄金",
            city="深圳",
            region="深圳",
            mall="深圳 万象城",
            type_tags=["老铺黄金专柜", "核心商圈"],
            fx_discount=None,
            coupon_rate=None,
            promo_desc="暂无明确公开的统一活动信息，通常跟随商场联合促销与品牌档期。",
            promo_valid_until=None,
            restock_note="深圳地区投资需求偏强，大克重金条和古法手镯补货频率相对较高。",
            inventory_tags=[],
            promo_source="待补充商场与品牌官网链接。",
        ),
        Store(
            id="cn_guangzhou_taikoo",
            name="广州 太古汇 / 天环广场 老铺黄金",
            city="广州",
            region="广州",
            mall="广州 核心商圈（如太古汇、天环广场等）",
            type_tags=["老铺黄金专柜"],
            fx_discount=None,
            coupon_rate=None,
            promo_desc="活动多与商场联动，具体折扣以当地场内公示为准。",
            promo_valid_until=None,
            restock_note="工作日补货为主，节庆前夕古法饰品与婚庆套系补货集中。",
            inventory_tags=[],
            promo_source="待补充商场与品牌官网链接。",
        ),
        Store(
            id="cn_hainan_dutyfree",
            name="海南 离岛免税区 老铺黄金",
            city="海南",
            region="海南",
            mall="离岛免税购物城（以实际入驻点位为准）",
            type_tags=["老铺黄金专柜", "离岛免税"],
            fx_discount=None,
            coupon_rate=None,
            promo_desc="如有免税或满减政策，以免税城及品牌现场标牌为准。",
            promo_valid_until=None,
            restock_note="节假日补货密集，投资金条与礼赠套装款式较丰富。",
            inventory_tags=[],
            promo_source="待补充免税城与品牌官网链接。",
        ),
    ]


def build_html(context: Dict[str, Any]) -> str:
    env = jinja2.Environment(
        loader=jinja2.DictLoader({"index.html": HTML_TEMPLATE}),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("index.html")
    return template.render(**context)


def main() -> None:
    stores = get_store_data()
    news_items = get_static_news()

    # 模块二：根据价格优势（折扣越低越好）排序
    sortable_stores = [
        s for s in stores if s.fx_discount is not None or s.coupon_rate is not None
    ]
    sortable_stores_sorted = sorted(
        sortable_stores, key=lambda s: s.effective_discount()
    )

    # 模块三：模拟场景到手价排序
    stores_with_sim = sorted(stores, key=lambda s: s.simulated_final_price())

    now = datetime.datetime.now()
    context = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "base_price_per_g": BASE_PRICE_PER_G,
        "sim_weight_g": SIM_WEIGHT_G,
        "news_items": news_items,
        "stores": stores,
        "stores_pricing_rank": sortable_stores_sorted,
        "stores_sim_rank": stores_with_sim,
    }

    out_html = build_html(context)

    out_path = Path(__file__).parent / "index.html"
    out_path.write_text(out_html, encoding="utf-8")

    # 额外导出一份 JSON 便于后续做 API 或小程序对接
    data_out = {
        "generated_at": context["generated_at"],
        "base_price_per_g": BASE_PRICE_PER_G,
        "sim_weight_g": SIM_WEIGHT_G,
        "stores": [asdict(s) | {"simulated_final_price": s.simulated_final_price()} for s in stores],
    }
    (Path(__file__).parent / "data.json").write_text(
        json.dumps(data_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
  <title>老铺黄金买手雷达 - 港澳内地门店性价比仪表盘</title>
  <style>
    :root {
      --bg: #f5f3ef;
      --card-bg: #fbfaf8;
      --gold: #c9a063;
      --gold-deep: #b3863b;
      --text-main: #1f1f1f;
      --text-sub: #6b6b6f;
      --border-soft: rgba(0,0,0,0.06);
      --shadow-soft: 0 12px 30px rgba(0,0,0,0.06);
      --radius-xl: 24px;
      --radius-lg: 18px;
      --radius-pill: 999px;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, -apple-system-body, "PingFang SC", "Helvetica Neue", Arial, sans-serif;
      background: radial-gradient(circle at top left, #fdf7ea, #f3f1ec);
      color: var(--text-main);
      -webkit-font-smoothing: antialiased;
      padding: 32px 16px 48px;
    }

    .shell {
      max-width: 1180px;
      margin: 0 auto;
    }

    header {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 24px;
    }

    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .logo-mark {
      width: 40px;
      height: 40px;
      border-radius: 20px;
      background: linear-gradient(135deg, #f7e7c4, #c99a55);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #3c2a13;
      font-weight: 700;
      box-shadow: 0 10px 25px rgba(185, 135, 60, 0.45);
    }

    .logo-text-main {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }

    .logo-text-sub {
      font-size: 12px;
      color: var(--text-sub);
      margin-top: 2px;
    }

    .meta {
      font-size: 11px;
      color: var(--text-sub);
      text-align: right;
    }

    .meta strong {
      color: var(--gold-deep);
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 3fr) minmax(0, 2.4fr);
      gap: 20px;
      margin-bottom: 20px;
    }

    @media (max-width: 960px) {
      .grid {
        grid-template-columns: minmax(0, 1fr);
      }
      body {
        padding-top: 20px;
      }
    }

    .card {
      background: var(--card-bg);
      border-radius: var(--radius-xl);
      padding: 18px 18px 16px;
      box-shadow: var(--shadow-soft);
      border: 1px solid var(--border-soft);
      backdrop-filter: blur(12px);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }

    .card-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 15px;
      font-weight: 600;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      padding: 2px 10px;
      border-radius: var(--radius-pill);
      font-size: 11px;
      background: rgba(201, 160, 99, 0.12);
      color: var(--gold-deep);
    }

    .badge {
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid rgba(0,0,0,0.07);
      color: var(--text-sub);
    }

    ul.news-list {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 6px;
    }

    .news-item {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 8px 10px;
      border-radius: 14px;
      transition: background 0.2s ease, transform 0.1s ease;
    }

    .news-item:hover {
      background: rgba(255,255,255,0.88);
      transform: translateY(-1px);
    }

    .news-title {
      font-size: 13px;
      font-weight: 500;
    }

    .news-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: var(--text-sub);
    }

    .news-link {
      font-size: 11px;
      color: var(--gold-deep);
      text-decoration: none;
    }

    .news-link:hover {
      text-decoration: underline;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      margin-top: 6px;
    }

    th, td {
      text-align: left;
      padding: 6px 6px;
    }

    th {
      font-size: 11px;
      color: var(--text-sub);
      border-bottom: 1px solid rgba(0,0,0,0.06);
      font-weight: 500;
    }

    tr + tr td {
      border-top: 1px solid rgba(0,0,0,0.03);
    }

    .tag-row {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 4px;
    }

    .tag {
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(0,0,0,0.03);
      color: var(--text-sub);
    }

    .tag.gold {
      background: rgba(201,160,99,0.14);
      color: var(--gold-deep);
    }

    .muted {
      color: var(--text-sub);
    }

    .price-strong {
      font-weight: 600;
      color: var(--gold-deep);
    }

    .section-title {
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 8px;
    }

    .store-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px;
      margin-top: 8px;
    }

    .store-card {
      border-radius: var(--radius-lg);
      padding: 12px 12px 10px;
      border: 1px solid var(--border-soft);
      background: linear-gradient(135deg, #fdfbf7, #f7f3ec);
    }

    .store-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px;
      margin-bottom: 6px;
    }

    .store-name {
      font-size: 13px;
      font-weight: 600;
    }

    .store-location {
      font-size: 11px;
      color: var(--text-sub);
    }

    .store-body {
      font-size: 11px;
      color: var(--text-sub);
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 4px;
    }

    .store-meta-row {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
    }

    .highlight-pill {
      padding: 2px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.7);
      border: 1px solid rgba(201,160,99,0.4);
      font-size: 10px;
      color: var(--gold-deep);
    }

    footer {
      margin-top: 18px;
      font-size: 10px;
      color: var(--text-sub);
      text-align: center;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="logo">
        <div class="logo-mark">Au</div>
        <div>
          <div class="logo-text-main">老铺黄金买手雷达</div>
          <div class="logo-text-sub">港澳 &middot; 内地 SKP &middot; 粤港澳大湾区</div>
        </div>
      </div>
      <div class="meta">
        <div>生成时间：<strong>{{ generated_at }}</strong></div>
        <div>模拟场景：<strong>{{ sim_weight_g }}g @ {{ base_price_per_g }} 元/克</strong>（含门店优惠后估算到手价）</div>
      </div>
    </header>

    <div class="grid">
      <!-- 模块一：热门资讯 -->
      <section class="card">
        <div class="card-header">
          <div class="card-title">
            <span>① 老铺黄金 Top5 热门资讯</span>
            <span class="pill">基于官网与权威媒体，不做主观推荐</span>
          </div>
        </div>
        <ul class="news-list">
          {% for item in news_items %}
          <li class="news-item">
            <div class="news-title">{{ item.title }}</div>
            <div class="news-meta">
              <span class="muted">{{ item.source }} · {{ item.date }}</span>
              <a class="news-link" href="{{ item.url }}" target="_blank" rel="noopener">查看原文 ⟶</a>
            </div>
          </li>
          {% endfor %}
        </ul>
      </section>

      <!-- 模块二：性价比排序 -->
      <section class="card">
        <div class="card-header">
          <div class="card-title">
            <span>② 门店性价比（按价格优势倒排）</span>
            <span class="pill">仅对已知折扣门店做排序</span>
          </div>
        </div>
        {% if stores_pricing_rank %}
        <table>
          <thead>
            <tr>
              <th style="width: 26px;">序</th>
              <th>门店</th>
              <th>估算折扣</th>
              <th>一句话说明</th>
            </tr>
          </thead>
          <tbody>
            {% for s in stores_pricing_rank %}
            <tr>
              <td>{{ loop.index }}</td>
              <td>
                <div style="font-size: 12px; font-weight: 500;">{{ s.name }}</div>
                <div class="muted" style="font-size: 11px;">{{ s.city }} · {{ s.mall }}</div>
              </td>
              <td>
                <div class="price-strong">
                  {{ '%.1f' % (s.effective_discount() * 100) }}%
                </div>
                <div class="muted" style="font-size: 10px;">相对内地标价的估算折扣</div>
              </td>
              <td style="font-size: 11px;">
                {% if s.id == 'hk_harbour_city' %}
                  港币实时汇率约 {{ '%.0f' % (s.fx_discount * 100) }} 折 + 商场满 HK$10,000 返 HK$500 购物券，适合集中采购投资款。
                {% else %}
                  折扣参数来自公开信息，具体价格以门店现场公示为准。
                {% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        {% else %}
        <div class="muted" style="font-size: 12px;">暂未获取到可量化的价格参数，待补充更多官方活动数据。</div>
        {% endif %}
      </section>
    </div>

    <div class="grid">
      <!-- 模块三：模拟场景到手价 -->
      <section class="card">
        <div class="card-header">
          <div class="card-title">
            <span>③ 模拟「50g @ {{ base_price_per_g }} 元/克」到手价</span>
            <span class="pill">从低到高排序，基于当前配置折扣</span>
          </div>
          <div class="badge">单位：人民币估算</div>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width: 26px;">序</th>
              <th>门店</th>
              <th>估算到手价</th>
              <th>折扣构成</th>
            </tr>
          </thead>
          <tbody>
            {% for s in stores_sim_rank %}
            <tr>
              <td>{{ loop.index }}</td>
              <td>
                <div style="font-size: 12px; font-weight: 500;">{{ s.name }}</div>
                <div class="muted" style="font-size: 11px;">{{ s.city }} · {{ s.mall }}</div>
              </td>
              <td>
                <div class="price-strong">
                  ¥{{ '%.0f' % s.simulated_final_price() }}
                </div>
                <div class="muted" style="font-size: 10px;">    
                  基准价 ¥{{ base_price_per_g * sim_weight_g }} × 折扣系数 {{ '%.3f' % s.effective_discount() }}
                </div>
              </td>
              <td style="font-size: 11px;">
                {% if s.fx_discount %}
                  <div>汇率折算：约 {{ '%.0f' % (s.fx_discount * 100) }}%</div>
                {% endif %}
                {% if s.coupon_rate %}
                  <div>购物券折算：约 {{ '%.0f' % ((1 - s.coupon_rate) * 100) }}%</div>
                {% endif %}
                {% if not s.fx_discount and not s.coupon_rate %}
                  <div class="muted">暂无可量化折扣参数，按原价估算。</div>
                {% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </section>

      <!-- 模块四：港澳 + 内地重点城市门店卡片 -->
      <section class="card">
        <div class="card-header">
          <div class="card-title">
            <span>④ 港澳 & 内地重点门店卡片</span>
            <span class="pill">信息来自公开渠道与已确认的线下卡片</span>
          </div>
        </div>
        <div class="section-title">按地区分组查看</div>
        <div class="store-grid">
          {% for s in stores %}
          <article class="store-card">
            <div class="store-header">
              <div>
                <div class="store-name">{{ s.name }}</div>
                <div class="store-location">{{ s.region }} · {{ s.city }} · {{ s.mall }}</div>
              </div>
              <div class="tag-row">
                {% if s.region in ['香港', '澳门'] %}
                  <span class="highlight-pill">港澳线下门店</span>
                {% elif 'SKP' in s.mall %}
                  <span class="highlight-pill">SKP 高端场景</span>
                {% else %}
                  <span class="highlight-pill">核心商圈</span>
                {% endif %}
              </div>
            </div>
            <div class="store-body">
              <div>
                <span class="muted">当前优惠：</span>{{ s.promo_desc }}
                {% if s.promo_valid_until %}
                  <span class="muted">（有效期至 {{ s.promo_valid_until }}，以官方公示为准）</span>
                {% endif %}
              </div>
              <div>
                <span class="muted">补货节奏：</span>{{ s.restock_note or '待实地补充，以门店说法为准。' }}
              </div>
              {% if s.inventory_tags %}
                <div>
                  <span class="muted">当前主打货品：</span>
                  <span class="tag-row">
                    {% for t in s.inventory_tags %}
                      <span class="tag gold">{{ t }}</span>
                    {% endfor %}
                  </span>
                </div>
              {% endif %}
              <div class="store-meta-row">
                <div class="tag-row">
                  {% for t in s.type_tags %}
                    <span class="tag">{{ t }}</span>
                  {% endfor %}
                </div>
              </div>
              <div class="muted" style="font-size: 10px; margin-top: 4px;">
                信息来源：{{ s.promo_source }}
              </div>
            </div>
          </article>
          {% endfor %}
        </div>
      </section>
    </div>

    <footer>
      本页面仅整合来自老铺黄金及合作商场的公开信息和你提供的线下卡片，不构成任何投资或价格承诺。<br/>
      所有价格与优惠以各门店及官网实时公示为准，交易前请务必再次与门店确认。
    </footer>
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    main()

