---
name: wechat-writing
description: 写公众号、发 AI 新闻、生成公众号封面、做同风格 PPT 封面或推公众号草稿箱时使用。覆盖 aihot 选题、个人素材检索与资料调研、技术文章起草、按样文精简审稿、小红书笔记改写，以及用宿主生图工具做封面、用 wxpub 预览和推草稿箱。也支持只改现有稿、核查、学习改稿与归档。
---

# 公众号写作

用户说“公众号”“发一篇 AI 新闻”“做公众号封面”“改成小红书”或“推草稿箱”时，从对应环节直接开始。用户已给定选题或源稿时，直接使用。

| 用户意图 | 操作 |
|---|---|
| 今日 AI 新闻、找选题、给现有题目想角度 | 读 [AI 新闻选题](references/ai-news.md)。请用户从候选里挑；用户已明确授权自动挑选时，按其标准选题。 |
| 找我以前的记录、做资料调研 | 读 [个人素材与调研](references/research.md)。 |
| 起草、去 AI 味、核查 | 读 [成稿与编辑](references/editorial.md)。起草先厘清素材和判断，再做一次删改；只润色时直接编辑原稿。 |
| 小红书版 | 读 [小红书改写](references/xiaohongshu.md)。输出独立笔记稿。 |
| 做公众号封面、复用风格做 PPT 封面 | 读 [公众号封面](references/cover.md)。固定手绘风格，模型生成无字背景，再叠加标题。 |
| 配图、预览、推草稿箱、归档 | 读 [发布与归档](references/publishing.md)。通过 wxpub 生成公众号交付物。 |
| 导入范文、学习人工改稿 | 读 [成稿与编辑](references/editorial.md) 的“学习作者文风”。 |

沿用现有文章的目录、署名和已注明的项目约定。用户未指定新稿位置时，用当前项目的 `articles/<slug>/article.md`；AI 日报用 `articles/ai-daily-YYYY-MM-DD-<slug>/article.md`。项目另有已明确的目录配置时按其配置执行。只写稿或只改稿时交付 Markdown，需要渲染或推草稿箱时再调用 wxpub。
