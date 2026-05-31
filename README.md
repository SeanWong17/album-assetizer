<p align="center">
  <a href="./README_en.md">English</a> | <span>简体中文</span>
</p>

<div align="center">

# Album Assetizer

**个人相册语义资产生成器 · 把照片变成可检索的结构化数据**

<p>
  <a href="https://github.com/ruanyf/weekly/blob/master/docs/issue-399.md">
    <img src="https://img.shields.io/badge/科技爱好者周刊-第399期推荐-ff69b4?style=flat-square&logo=rss" alt="Tech Enthusiast Weekly">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square" alt="License">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  </a>
  <a href="https://github.com/SeanWong17/album-assetizer/pulls">
    <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome">
  </a>
</p>

<img src="docs/screenshots/Demo.png" alt="效果预览" width="80%">

</div>

---

## 📋 项目简介

手机里几万张照片，想找某张图只能靠肉眼翻。系统相册的搜索能力有限，数据还锁在各家生态里。

**Album Assetizer** 扫描本地相册，调用视觉大模型为每张图生成中文结构化描述（场景、标签、主体、活动、OCR 等），同时提取 EXIF 拍摄时间和 GPS 坐标，最终输出标准格式（JSONL / CSV / SQLite），可直接接入任何下游应用。

```
照片 → 扫描 → EXIF 提取 → 视觉大模型标注 → 结构化数据资产
```

---

## ✨ 核心特性

| 模块 | 功能描述 |
|------|----------|
| **格式支持** | JPG / PNG / HEIC / DNG / CR3 / LIVP（Apple Live Photo） |
| **图片预处理** | 自动缩放、EXIF 方向校正、RGBA→RGB、RAW 解码、体积控制 |
| **元数据提取** | EXIF 拍摄时间、GPS 经纬度，支持时区解析 |
| **大模型标注** | OpenAI 兼容 API，支持 Structured Output（json_schema + 自动降级） |
| **并发与速率** | 多线程并发 + RPM 限速 + 稳定后自动扩容 + 连续失败自动缩容 |
| **容错机制** | 指数退避重试、错误分类（可重试 vs 永久失败）、崩溃恢复、优雅停机 |
| **二轮精修** | 首轮视觉生成 + 可选的纯文本模型精修，提升标注一致性 |
| **数据导出** | SQLite 持久化，一键导出 JSONL / CSV / 失败列表 |
| **质量审阅** | 内置 HTML 审阅脚本，支持分页、筛选、键盘导航 |

---

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/SeanWong17/album-assetizer.git
cd album-assetizer
pip install -e .
```

### 2. 配置 API

```bash
# 在相册根目录下创建工作目录并配置
mkdir -p /path/to/album/.album-assetizer
cp examples/sample.env /path/to/album/.album-assetizer/.env
```

编辑 `.env` 文件，填入你的 API Key 和 Base URL（支持任何 OpenAI 兼容接口）：

```env
ALBUM_ASSETIZER_API_KEY=your_api_key
ALBUM_ASSETIZER_BASE_URL=https://your-provider.com/v1
ALBUM_ASSETIZER_MODEL=your-vision-model
```

### 3. 验证连通性

```bash
album-assetizer --root /path/to/album smoke-text       # 文本接口探测
album-assetizer --root /path/to/album smoke-image --path some_photo.jpg  # 单图探测
```

### 4. 运行完整流程

```bash
album-assetizer --root /path/to/album scan            # 扫描素材入库
album-assetizer --root /path/to/album sync-metadata   # 提取 EXIF 时间/GPS
album-assetizer --root /path/to/album run             # 调用大模型批量标注
album-assetizer --root /path/to/album export          # 导出 JSONL/CSV
album-assetizer --root /path/to/album stats           # 查看处理统计
```

---

## 📊 输出字段

每张图片生成一条结构化记录：

| 字段 | 类型 | 说明 |
|------|------|------|
| `caption_short` | string | 一句话简短描述 |
| `caption_long` | string | 详细描述，适合检索和回顾 |
| `scene` | string | 场景分类（户外、室内、街道等） |
| `tags` | list | 语义标签（6-18 个，去重） |
| `main_subjects` | list | 画面主体（人物、建筑、食物等） |
| `activities` | list | 正在发生的活动 |
| `style_labels` | list | 风格标签（截图、黑白、HDR 等） |
| `quality_flags` | list | 质量标记（模糊、过曝等） |
| `safety_flags` | list | 安全标记 |
| `contains_text` | bool | 是否包含文字 |
| `ocr_text` | string | OCR 识别文字（≤300 字） |
| `people_count` | int | 人数（-1 表示无法判断） |
| `confidence` | float | 置信度 (0-1) |
| `embedding_text` | string | 拼接全字段的 embedding 文本 |
| `taken_at` | string | EXIF 拍摄时间（ISO 8601） |
| `gps_lat` / `gps_lng` | float | EXIF GPS 经纬度 |

---

## 🔧 进阶用法

### 审阅脚本

```bash
python3 scripts/render_review_html.py \
  --jsonl /path/to/results.jsonl \
  --image-root /path/to/album_root \
  --output review.html
```

生成静态 HTML 审阅页，支持分页、关键词筛选、键盘导航，用于 Prompt 评估和质量抽检。

### 二轮文本精修

```bash
album-assetizer --root /path/to/album \
  --text-refine-model your-text-model \
  refine-done
```

对已完成的首轮标注结果进行规范化精修（去重、修正文案、压缩冗余标签），提升标注一致性。

### 自动扩缩容

```bash
album-assetizer --root /path/to/album \
  --auto-scale \
  --scale-up-workers 6 --scale-up-rpm 120 \
  run
```

稳定处理一段时间后自动提升并发和速率，连续失败时自动降回保守配置。

---

## 🏗️ 项目结构

```text
album-assetizer/
├── src/album_assetizer/
│   ├── cli.py              # CLI 入口与参数解析
│   ├── config.py           # 运行时配置定义
│   ├── scanner.py          # 相册文件扫描
│   ├── metadata.py         # EXIF/GPS 元数据提取
│   ├── image_prep.py       # 图片预处理（缩放、转码、压缩）
│   ├── api.py              # API 调用与响应解析
│   ├── worker.py           # 工作线程（重试、错误分类）
│   ├── processor.py        # 并发编排（扩缩容、优雅停机）
│   ├── rate_limiter.py     # 线程安全速率限制器
│   ├── db.py               # SQLite 数据层
│   ├── exporters.py        # JSONL/CSV 导出
│   ├── prompts.py          # LLM 提示词
│   ├── schemas.py          # 输出字段与 JSON Schema
│   ├── models.py           # 数据类与异常定义
│   └── runtime.py          # 工具函数
├── scripts/
│   ├── render_review_html.py        # 审阅页生成
│   └── export_explorer_snapshot.py  # Explorer 快照导出
├── tests/
├── examples/sample.env
├── pyproject.toml
├── ROADMAP.md
└── CONTRIBUTING.md
```

---

## 📐 项目边界

本项目只做：**生成并沉淀高质量的相册语义资产**。

项目内置了一个轻量审阅脚本（即首页截图所示），可以直观地浏览图片与生成的结构化描述，用于验证标注质量。更完整的消费场景（检索、聚类、推荐、时间线、地图可视化等）不在本项目范围内，你可以用自己熟悉的工具链来使用这些数据。

---

## 🗺️ 路线图

详见 [ROADMAP.md](ROADMAP.md)。

---

## 🤝 参与贡献

欢迎提交 Issue 或 Pull Request。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 📄 License

[MIT License](LICENSE) © 2026 SeanWong17

---

## 社区

本项目在 [LINUX DO](https://linux.do) 社区发布与推广，感谢社区佬友们的支持与反馈。

---

<div align="center">
  <br>
  Made with ❤️ by <a href="https://github.com/SeanWong17">SeanWong17</a>
</div>