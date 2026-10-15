"""
Image uploads: checked, resized and re-encoded with Pillow (removes metadata), then stored on
Cloudinary (CLOUDINARY_URL set) or in MEDIA_ROOT.
"""

import io
import uuid
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, UnidentifiedImageError

from .errors import ValidationFailed
from .models import Upload

FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def store_image(file, *, user, request):
    if file.size > settings.UPLOAD_MAX_BYTES:
        raise ValidationFailed("The image is larger than 5 MB.", details={"file": "too_large"})
    try:
        image = Image.open(file)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationFailed("The file is not an image.", details={"file": "invalid_image"}) from exc
    if image.format not in FORMATS:
        raise ValidationFailed("Use a JPEG, PNG or WebP image.", details={"file": "unsupported_format"})

    image_format = image.format
    image.thumbnail((settings.UPLOAD_MAX_SIDE, settings.UPLOAD_MAX_SIDE))
    if image_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, quality=85, optimize=True)
    name = f"{uuid.uuid4().hex}.{FORMATS[image_format]}"

    if settings.CLOUDINARY_URL:
        url = _upload_to_cloudinary(buffer.getvalue(), name)
    else:
        path = default_storage.save(f"uploads/{name}", ContentFile(buffer.getvalue()))
        url = request.build_absolute_uri(default_storage.url(path))

    return Upload.objects.create(url=url, width=image.width, height=image.height, uploaded_by=user)


def _upload_to_cloudinary(content, name):
    import cloudinary
    import cloudinary.uploader

    parsed = urlparse(settings.CLOUDINARY_URL)  # cloudinary://<api_key>:<api_secret>@<cloud_name>
    cloudinary.config(cloud_name=parsed.hostname, api_key=parsed.username, api_secret=parsed.password, secure=True)
    result = cloudinary.uploader.upload(content, folder="wow-quick-bites", public_id=name.rsplit(".", 1)[0])
    return result["secure_url"]
