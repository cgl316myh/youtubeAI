# YouTube Daily Digest

每天自动抓取 YouTube 上 **AI / VPN / 云服务器** 相关、近 30 天人气最高的视频（每类 15 条），生成本地可浏览的 HTML，并可通过 GitHub Actions 定时跑 + GitHub Pages 在线查看。

## 功能

- 每类按播放量取 Top 15（近 30 天）
- `docs/index.html`：总索引快链
- `docs/latest.html`：始终为最新一期
- `docs/YYYY-MM-DD.html`：历史日报
- GitHub Actions：每天北京时间 08:00 自动跑，也可手动触发

## 本地运行

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env，填入 YOUTUBE_API_KEY=...
python fetch_videos.py
```

然后用浏览器打开 `docs/index.html` 或 `docs/latest.html`。

## 部署到 GitHub（本机不开也能跑）

### 1. 创建仓库并推送

在 GitHub 新建空仓库（例如 `youtubeAI`），然后：

```bash
git init -b main
git add .
git commit -m "feat: YouTube daily digest with GitHub Actions"
git remote add origin https://github.com/<你的用户名>/youtubeAI.git
git push -u origin main
```

### 2. 配置 API Key（Secret）

仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

- Name: `YOUTUBE_API_KEY`
- Value: 你的 YouTube Data API 密钥

> 不要把密钥写进代码或提交到仓库。若密钥曾在聊天/截图中暴露，请到 Google Cloud 控制台轮换（删除旧密钥、新建一把）。

### 3. 打开 GitHub Pages

仓库 → **Settings** → **Pages**

- Source: **GitHub Actions**

### 4. 首次手动运行

仓库 → **Actions** → **Daily YouTube Digest** → **Run workflow**

成功后访问：

`https://<用户名>.github.io/youtubeAI/`

（私有仓库是否支持 Pages 取决于你的 GitHub 套餐。）

### 5. 定时说明

工作流 cron 为 UTC `0 0 * * *`，即北京时间每天 **08:00**。可在 `.github/workflows/daily.yml` 里改。

## 修改关键词 / 条数

编辑 `config.yaml`：

- `published_within_days`：时间窗口（默认 30）
- `max_results_per_category`：每类条数（默认 15）
- `categories[].queries`：搜索关键词

## 安全提醒

- API Key 仅放在 `.env`（本地，已 gitignore）或 GitHub Secrets
- 建议在 Google Cloud 凭据里把密钥的 API 限制设为仅 `YouTube Data API v3`
