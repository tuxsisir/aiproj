"""
Serving uploaded files. Uploads are never public (`/media/` is only served in DEBUG): every file goes through a
view that checks who is asking, then calls `serve_upload`.
"""
import mimetypes
import os

from django.http import FileResponse, Http404

# Shown in the browser; anything else (HTML, SVG, office files…) downloads, so an upload can't run script here.
INLINE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/heic", "application/pdf"}


def serve_upload(fieldfile):
    if not fieldfile:
        raise Http404("No file.")
    try:
        handle = fieldfile.open("rb")
    except FileNotFoundError:
        raise Http404("File is missing.")
    name = os.path.basename(fieldfile.name)
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    inline = content_type in INLINE_TYPES
    response = FileResponse(handle, filename=name, as_attachment=not inline,
                            content_type=content_type if inline else "application/octet-stream")
    response["Cache-Control"] = "private, max-age=300"
    return response
