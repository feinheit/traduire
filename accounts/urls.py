from django.urls import include, path

from accounts import views


urlpatterns = [
    path("logout/", views.logout, name="logout"),
    path(
        "google-sso/",
        views.google_sso,
        name="google-sso",
    ),
    path(
        "microsoft-sso/",
        views.microsoft_sso,
        name="microsoft-sso",
    ),
    path("register/", views.register, name="register"),
    path("register/<str:code>/", views.register, name="email_registration_confirm"),
    path("create/", views.create, name="create"),
    path("", include("django.contrib.auth.urls")),
]
