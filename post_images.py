"""게시글 이미지 처리 및 Supabase Storage 연동.

실제 이미지 파일은 Supabase Storage에 저장하고 SQLite에는 공개 URL/경로만 저장합니다.
서버 비밀키는 환경변수에서만 읽으며 브라우저로 노출하지 않습니다.
"""
from __future__ import annotations

from io import BytesIO
from urllib.parse import quote
import uuid

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

import config

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# 지나치게 큰 압축폭탄 이미지를 메모리에 올리지 않도록 제한합니다.
Image.MAX_IMAGE_PIXELS = 25_000_000


class PostImageError(ValueError):
    pass


def storage_configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_STORAGE_KEY and config.SUPABASE_STORAGE_BUCKET)


def _storage_headers(content_type: str | None = None) -> dict[str, str]:
    key = config.SUPABASE_STORAGE_KEY or ""
    # Supabase 클라이언트와 같은 방식으로 API key + Authorization 헤더를 함께 보냅니다.
    # 이 키는 서버에서만 사용하며 브라우저에는 절대 노출하지 않습니다.
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _storage_object_url(path: str) -> str:
    base = config.SUPABASE_URL.rstrip("/")
    bucket = quote(config.SUPABASE_STORAGE_BUCKET, safe="")
    encoded_path = quote(path, safe="/")
    return f"{base}/storage/v1/object/{bucket}/{encoded_path}"


def public_url(path: str) -> str:
    base = config.SUPABASE_URL.rstrip("/")
    bucket = quote(config.SUPABASE_STORAGE_BUCKET, safe="")
    encoded_path = quote(path, safe="/")
    return f"{base}/storage/v1/object/public/{bucket}/{encoded_path}"


def _read_source(file_storage) -> bytes:
    if not file_storage or not getattr(file_storage, "filename", ""):
        raise PostImageError("이미지 파일이 비어 있습니다.")
    raw = file_storage.stream.read(config.POST_IMAGE_SOURCE_MAX_BYTES + 1)
    if len(raw) > config.POST_IMAGE_SOURCE_MAX_BYTES:
        max_mb = config.POST_IMAGE_SOURCE_MAX_BYTES // (1024 * 1024)
        raise PostImageError(f"원본 이미지는 한 장당 {max_mb}MB 이하만 첨부할 수 있습니다.")
    if not raw:
        raise PostImageError("이미지 파일이 비어 있습니다.")
    return raw


def _save_webp(image: Image.Image, quality: int) -> bytes:
    out = BytesIO()
    image.save(out, format="WEBP", quality=quality, method=6)
    return out.getvalue()


def prepare_image(file_storage) -> bytes:
    """입력 이미지를 검증하고 EXIF 제거 + 리사이즈 + WebP 압축합니다."""
    raw = _read_source(file_storage)
    try:
        with Image.open(BytesIO(raw)) as opened:
            if opened.format not in ALLOWED_FORMATS:
                raise PostImageError("JPG, PNG, WebP 이미지만 첨부할 수 있습니다.")
            if getattr(opened, "is_animated", False):
                raise PostImageError("움직이는 이미지는 첨부할 수 없습니다.")
            opened.load()
            image = ImageOps.exif_transpose(opened).copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PostImageError("올바른 이미지 파일이 아닙니다.") from exc

    # WebP는 RGB/RGBA로 저장합니다. 새 파일로 다시 저장되므로 EXIF 등 메타데이터는 제거됩니다.
    if "A" in image.getbands():
        image = image.convert("RGBA")
    else:
        image = image.convert("RGB")

    max_edge = max(640, int(config.POST_IMAGE_MAX_EDGE))
    if max(image.size) > max_edge:
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

    # 우선 화질을 단계적으로 낮추고, 그래도 1MB를 넘으면 크기를 조금씩 줄입니다.
    qualities = (84, 78, 72, 66, 60, 54, 48, 42)
    for _ in range(5):
        for quality in qualities:
            data = _save_webp(image, quality)
            if len(data) <= config.POST_IMAGE_MAX_BYTES:
                return data
        if min(image.size) <= 640:
            break
        next_size = (max(640, int(image.width * 0.85)), max(640, int(image.height * 0.85)))
        image.thumbnail(next_size, Image.Resampling.LANCZOS)

    max_kb = config.POST_IMAGE_MAX_BYTES // 1024
    raise PostImageError(f"이미지를 {max_kb}KB 이하로 압축하지 못했습니다. 더 작은 사진을 사용해주세요.")


def upload(post_id: int, file_storage) -> tuple[str, str]:
    if not storage_configured():
        raise PostImageError("사진 저장소가 아직 설정되지 않았습니다. 관리자에게 문의해주세요.")

    data = prepare_image(file_storage)
    path = f"posts/{int(post_id)}/{uuid.uuid4().hex}.webp"
    headers = _storage_headers("image/webp")
    headers["cache-control"] = "max-age=31536000"
    try:
        response = requests.post(
            _storage_object_url(path),
            headers=headers,
            data=data,
            timeout=config.SUPABASE_STORAGE_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PostImageError("사진 저장소에 연결하지 못했습니다.") from exc
    if response.status_code not in (200, 201):
        raise PostImageError(f"사진 업로드에 실패했습니다. (Storage {response.status_code})")
    return path, public_url(path)


def delete(paths: list[str]) -> None:
    """Storage API를 통해 객체를 삭제합니다. 하나라도 실패하면 예외를 냅니다."""
    if not paths:
        return
    if not storage_configured():
        raise PostImageError("사진 저장소가 설정되지 않아 첨부 이미지를 삭제할 수 없습니다.")
    for path in paths:
        try:
            response = requests.delete(
                _storage_object_url(path),
                headers=_storage_headers(),
                timeout=config.SUPABASE_STORAGE_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise PostImageError("사진 저장소에 연결하지 못했습니다.") from exc
        if response.status_code not in (200, 204):
            raise PostImageError(f"첨부 이미지 삭제에 실패했습니다. (Storage {response.status_code})")
