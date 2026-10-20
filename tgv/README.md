# TGV 技术情报子站

- 网页：`index.html`
- 采集脚本：`fetch_news.py`
- 历史归档：`news.json`
- 定时任务：`../.github/workflows/tgv-daily.yml`

## 运行机制
GitHub Actions 每天 UTC 22:00（北京时间次日 06:00）执行采集；也可以在 GitHub Actions 页面手动运行。定时任务可能延迟。

## 信息来源与限制
使用 Google News RSS 作为多站点检索入口，并为 TheElec、Xenospectrum、ETNews、BigGo Finance、Seoul Economic Daily 设置定向检索，同时补充台湾科技媒体、中文产业资讯、学术与专利检索词。定向检索不代表来源网站直接提供 RSS，也不保证所有文章都能被索引或访问。请遵守各网站使用条款及版权要求。

翻译使用公开翻译端点，不需要 API key，但可能限流；失败时保留原文。新闻聚合摘要可能不完整，所有技术结论、产能、客户验证和量产进度都应打开原文核实。收藏保存在当前浏览器本地，不跨设备同步。

## GitHub Pages
在仓库 Settings → Pages 中启用部署，选择从 main 分支部署（root）。页面可从仓库的 `/tgv/` 路径访问，前提是 Pages 已启用。
