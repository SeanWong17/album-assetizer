"""图片预处理模块：读取各种格式，统一转为压缩后的 JPEG 字节。"""

from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

import rawpy
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from album_assetizer.models import AssetRecord, PreparedImage, UnsupportedAssetError
from album_assetizer.scanner import RAW_EXTENSIONS, detect_livp_companion

# 注册 HEIC/HEIF 支持
register_heif_opener()


def open_image_from_bytes(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def prepare_image_from_pil(image: Image.Image, cfg) -> PreparedImage:
    """将 PIL 图片转为标准化 JPEG：EXIF 校正 → RGB → 缩放 → 压缩。"""
    # 根据 EXIF 方向旋转
    image = ImageOps.exif_transpose(image)

    # 统一转为 RGB
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGBA")
    if image.mode == "L":
        image = image.convert("RGB")
    if image.mode == "RGBA":
        # 将透明通道合并到白色背景
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")

    # 按最长边缩放
    width, height = image.size
    max_edge = max(width, height)
    if max_edge > cfg.max_image_edge:
        scale = cfg.max_image_edge / max_edge
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    # 压缩为 JPEG，若超出体积限制则逐步降低质量
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=cfg.jpeg_quality, optimize=True)
    jpeg_bytes = output.getvalue()

    quality = cfg.jpeg_quality
    while len(jpeg_bytes) > cfg.max_image_bytes and quality > 55:
        quality -= 8
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        jpeg_bytes = output.getvalue()

    return PreparedImage(
        jpeg_bytes=jpeg_bytes,
        width=image.width,
        height=image.height,
        mime_type="image/jpeg",
        source_note="prepared_jpeg",
    )


def prepare_regular_image(path: Path, cfg) -> PreparedImage:
    """处理普通图片文件，RAW 格式使用 rawpy 解码。"""
    suffix = path.suffix.lower()
    if suffix in RAW_EXTENSIONS:
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False)
        image = Image.fromarray(rgb)
        return prepare_image_from_pil(image, cfg)

    try:
        image = Image.open(path)
        image.load()
        return prepare_image_from_pil(image, cfg)
    except UnidentifiedImageError as exc:
        raise UnsupportedAssetError(f"不支持或损坏的图片文件: {path}") from exc


def prepare_livp_image(path: Path, cfg) -> PreparedImage:
    """从 LIVP zip 中提取图片并预处理。"""
    with zipfile.ZipFile(path) as zf:
        image_name, _ = detect_livp_companion(zf)
        with zf.open(image_name, "r") as fp:
            image_bytes = fp.read()
    image = open_image_from_bytes(image_bytes)
    return prepare_image_from_pil(image, cfg)


def prepare_asset_image(asset: AssetRecord, cfg) -> PreparedImage:
    """根据素材类型分发到对应的预处理函数。"""
    if asset.asset_type == "livp":
        return prepare_livp_image(asset.abs_path, cfg)
    if asset.asset_type == "image":
        return prepare_regular_image(asset.abs_path, cfg)
    raise UnsupportedAssetError(f"不支持的素材类型: {asset.asset_type}")


def build_data_url(prepared: PreparedImage) -> str:
    """将预处理后的图片编码为 base64 data URL。"""
    encoded = base64.b64encode(prepared.jpeg_bytes).decode("ascii")
    return f"data:{prepared.mime_type};base64,{encoded}"
