from django.contrib import admin
from django.urls import path, include

from core import views as core_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Staff-only email previews (before admin.site.urls, whose catch-all would swallow them)
    path("admin/emails/", core_views.email_preview_list, name="email_preview_list"),
    path("admin/emails/<str:key>/", core_views.email_preview, name="email_preview"),
    path("admin/emails/<str:key>/<str:fmt>/", core_views.email_preview_body, name="email_preview_body"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("anymail/", include("anymail.urls")),
    path("payments/", include("payments.urls")),
    path("stratas/", include("stratas.urls")),
    path("dockets/", include("dockets.urls")),
    path("documents/", include("documents.urls")),
    path("inbox/", include("inbox.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
