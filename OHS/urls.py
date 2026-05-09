from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve
from django.views.generic.base import RedirectView

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon_final.ico")),
    path("admin/", admin.site.urls),
    path("", include("home.urls")),
    path("chat/", include("chat.urls")),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="login.html"),
        name="login",
    ),
]


# Serve media files even when DEBUG=False (useful for Docker / staging)
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]


handler404 = "home.views.custom_404"
handler403 = "home.views.custom_403"
handler500 = "home.views.custom_500"
