# Demo 说明

这里用于放项目演示资料。

建议保留两类内容：

- `review.html`
  真实结果的静态审阅页，直接展示图片与结构化描述
- `screenshots/`
  从审阅页截出来的示意图，用于 README 或项目首页展示

推荐截图内容：

- 左侧原图
- 右侧 `caption_short / caption_long / tags / OCR`
- 下方列表切换区

这样能最直观地体现项目输出的可读性与可检索性。

当前仓库内已包含：

- `demo/review.html`
  基于真实历史结果生成的静态审阅页示例
- `screenshots/Demo.png`
  从审阅页截取的 README 展示图

如需重新生成审阅页，可在项目根目录执行：

```bash
python3 scripts/render_review_html.py \
  --jsonl /path/to/results.jsonl \
  --image-root /path/to/album_root \
  --output docs/demo/review.html
```
