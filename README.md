# 老铺黄金 · 全球买金专员手册

每日自动更新金价数据，发布到 GitHub Pages，全球可访问。

## 快速部署（5步上线）

### 第 1 步：在 GitHub 创建仓库

1. 打开 [github.com/new](https://github.com/new)
2. 仓库名：`laopu-intel`（或任意名字）
3. 选 **Public**（公开仓库，Pages 免费）
4. 不勾选任何初始文件，直接点 **Create repository**

---

### 第 2 步：把本地代码推送到 GitHub

在终端依次运行：

```bash
cd /Users/jin/gold-dashboard

# 初始化 git（已初始化可跳过）
git init
git add .
git commit -m "初始化老铺黄金情报页面"

# 替换为你的 GitHub 用户名
git remote add origin https://github.com/【你的用户名】/laopu-intel.git
git branch -M main
git push -u origin main
```

---

### 第 3 步：开启 GitHub Pages

> **注意**：Actions 首次运行后会自动创建 `gh-pages` 分支，之后再配置 Pages。
> 如果仓库刚创建，可先跳到第 4 步手动触发一次 Actions，再回来配置。

1. 进入仓库 → **Settings** → **Pages**
2. Source 选 **Deploy from a branch**
3. Branch 选 **gh-pages**，目录选 **/(root)**
4. 点 **Save**

稍等 1-2 分钟，页面将在以下地址上线：

```
https://【你的用户名】.github.io/lp-longmao/
```

---

### 第 4 步：确认 Actions 权限

1. 进入仓库 → **Settings** → **Actions** → **General**
2. 找到 **Workflow permissions**
3. 选 **Read and write permissions**，点 **Save**

---

### 第 5 步：测试自动更新

1. 进入仓库 → **Actions** → **每日更新老铺黄金情报页面**
2. 点右上角 **Run workflow** → **Run workflow**
3. 等待约 1 分钟，刷新 GitHub Pages 链接，金价数据已自动更新

✅ 之后每周**五北京时间 07:00** 自动触发更新，无需任何操作。

---

## 文件结构

```
（仓库根目录）
├── .github/
│   └── workflows/
│       └── update-intel.yml  # GitHub Actions 定时任务（必须在根目录）
└── gold-dashboard/
    ├── laopu-intel.html      # HTML 模板（含 {{占位符}}）
    ├── generate_intel.py     # 数据抓取 + 页面生成脚本
    ├── requirements.txt      # Python 依赖
    └── index.html            # 自动生成，不要手动编辑
```

## 手动更新内容

需要修改促销信息、调价预告等**人工内容**时：

1. 直接编辑 `laopu-intel.html`（避免改动 `{{占位符}}` 标记）
2. 推送到 GitHub：
   ```bash
   git add laopu-intel.html
   git commit -m "更新：xxx促销活动"
   git push
   ```
3. GitHub Pages 约 1 分钟后自动生效

## 数据来源

| 数据 | 来源 |
|------|------|
| 伦敦金现货 | Yahoo Finance `GC=F`（黄金期货近月合约） |
| USD/CNY 汇率 | Yahoo Finance `USDCNY=X` |
| 老铺黄金港股 | Yahoo Finance `6181.HK` |
| 上海金估算 | 伦敦金 × 汇率 ÷ 31.1035 |
