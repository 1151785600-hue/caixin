# 财新网文章自动监控

自动扫描财新网最新发布的文章，在分时免费窗口期内抓取全文并保存为HTML。

## 工作原理

- 每个工作日（周一至周五）北京时间 08:00 - 18:00、23:00 各运行一次
- 扫描财新网 www/china/economy/finance/companies 五个频道
- 从每篇文章的 JSON-LD 结构化数据中提取 `articleBody` 字段
- 如果正文存在（说明仍在分时免费窗口内），保存为 HTML 文件
- 自动提交到仓库 `articles/` 目录

## 文件结构

```
├── .github/workflows/monitor.yml  # GitHub Actions 定时任务
├── caixin_monitor.py              # 抓取脚本
├── articles/                      # 保存的文章（自动生成）
└── README.md
```

## 使用方法

1. 在 GitHub 上创建一个私有仓库（建议私有，避免版权问题）
2. 将本目录所有文件推送到仓库
3. GitHub Actions 会自动按计划运行
4. 在 Actions 页面可以手动触发（`workflow_dispatch`）

## 注意事项

- GitHub Actions 的 cron 调度可能有几分钟延迟，不影响使用
- 财新分时免费窗口通常只有几个小时，命中率取决于文章发布时间与扫描时间的重合度
- 建议私有仓库使用，避免公开传播版权内容
