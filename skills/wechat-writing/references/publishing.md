# 配图、预览、草稿箱与归档

wxpub 是公众号的发布后端。在此仓库运行 `pip install .`，或运行 `pip install git+https://github.com/mantuoluozk/wxpub.git`。账号配置通过 `wxpub init` 建本地模板。实际推送前用 `wxpub doctor` 检查凭证、字体、权限和出口 IP。

1. 检查 Markdown 的 YAML frontmatter，至少包含 `title`；按稿件需要加 `subtitle`、`date`、`author`、`summary`、`theme`、`layout` 和 `cover`。摘要写在 120 字以内。截图和数据图靠近相关段落，说明来源和数据口径。用相对于文章目录的路径或来源图片 URL。
2. 沿用用户提供或已选定的封面。需要新封面时按 [公众号封面](cover.md) 生成，写入 frontmatter 的 `cover`。用户要求模型生图时，确认实际图片已落盘，再执行预览或推送；缺图会触发 wxpub 自动套模板。
3. 执行 `wxpub publish article.md --dry-run -o out`，打开 `out/preview.html`，核对标题、封面、首图、段落和代码块，交给用户看。只需预览时到此交付。
4. 用户已确认当前成品并授权推草稿箱时，执行 `wxpub publish article.md -o out`，以命令返回的结果确认是否成功。反复推送前先检查现有草稿，避免同稿多份。正式发布由用户在公众号后台操作。
5. 提供标题、预览路径和草稿结果。项目已有发布日志、选题台账或发布台账时，按其现有格式登记真实状态。推到草稿箱记为草稿；正式发布状态等用户提供发布结果后再记。
