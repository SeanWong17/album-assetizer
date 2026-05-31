# Roadmap

## Phase 1：描述生成与数据沉淀

- [x] 项目骨架与 CLI 入口
- [x] SQLite 数据库 schema（assets 表、索引、WAL 模式）
- [x] JSONL / CSV / failures 导出
- [x] 轻量审阅脚本（render_review_html.py）
- [x] 图片扫描（JPG / PNG / HEIC / DNG / CR3 / LIVP）
- [x] 增量扫描（基于 content_sig 跳过未变更文件）
- [x] 图片预处理（缩放、EXIF 校正、RGBA→RGB、体积控制、RAW 解码）
- [x] OpenAI 兼容 API 调用 + Structured Output（json_schema + fallback）
- [x] 结果标准化（标签去重、数量限制、confidence 钳位、OCR 截断）
- [x] embedding_text 生成（拼接全字段供下游 embedding）
- [x] 并发处理（ThreadPoolExecutor + 可配置 workers）
- [x] RPM 速率限制
- [x] 首轮视觉生成 + 二轮文本精修（refine-done）
- [x] .env 文件加载 API 配置

## Phase 2：质量与稳定性

- [x] 指数退避重试（可配置 base/max/max_attempts）
- [x] 错误分类（rate_limit / api_connection / unsupported_asset 等，区分可重试 vs 永久失败）
- [x] 崩溃恢复（mark_running_as_pending，重启后自动恢复中断任务）
- [x] 优雅停机（SIGINT/SIGTERM 信号处理，等待在途任务完成）
- [x] Auto-scaling（稳定后提升 workers/RPM，连续失败后降回）
- [x] 连通性预检（smoke-text / smoke-image）
- [x] tqdm 进度展示（实时 ok/err/rpm/workers）
- [x] Rotating 日志（文件 + 控制台双输出）
- [ ] Provider 抽象（支持多模型 / 多 endpoint）
- [ ] OCR 密集 / 截图 / 文档 / 地图类提示词优化
- [ ] 视频摘要能力

## 边界

本项目只做：**生成并沉淀高质量的相册语义资产**。

输出的结构化数据天然适合接入检索、聚类、推荐、可视化、时间线等下游场景，但这些消费能力不在本项目范围内。
