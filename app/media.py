"""Bounded image transcoding; stores encoded WebP in PostgreSQL, not ephemeral files."""
import io
import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import HTTPException
from .models import Media

MAX_UPLOAD = 5 * 1024 * 1024

def store_image(db, uploader_id, data: bytes, *, avatar=False):
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(413, 'Imagem deve ter no máximo 5 MB.')
    try:
        with Image.open(io.BytesIO(data)) as original:
            if original.format not in ('JPEG', 'PNG', 'WEBP', 'GIF'):
                raise HTTPException(415, 'Formato inválido. Use JPG, PNG, WebP ou GIF.')
            if original.width * original.height > 24_000_000:
                raise HTTPException(413, 'A imagem possui resolução excessiva.')
            image = ImageOps.exif_transpose(original)
            image.thumbnail((512, 512) if avatar else (1800, 1800))
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA' if 'A' in image.mode else 'RGB')
            output = io.BytesIO()
            image.save(output, 'WEBP', quality=78, method=4)
            binary = output.getvalue()
            if len(binary) > 2_000_000:
                raise HTTPException(413, 'Imagem processada muito grande; envie outra.')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, 'Arquivo de imagem inválido ou corrompido.')
    media = Media(id=str(uuid.uuid4()), uploader_id=uploader_id, mime_type='image/webp',
                  content=binary, size_bytes=len(binary))
    db.add(media)
    db.flush()
    return media.id
