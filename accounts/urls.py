from authlib.google import GoogleOAuth2Client
from authlib.microsoft import MicrosoftOAuth2Client
from django.urls import include, path

from accounts import views


urlpatterns = [
    path("logout/", views.logout, name="logout"),
    path(
        "google-sso/",
        views.sso,
        name="google-sso",
        kwargs={"sso_client_class": GoogleOAuth2Client},
    ),
    path(
        "microsoft-sso/",
        views.sso,
        name="microsoft-sso",
        kwargs={"sso_client_class": MicrosoftOAuth2Client},
    ),
    path("register/", views.register, name="register"),
    path("register/<str:code>/", views.register, name="email_registration_confirm"),
    path("create/", views.create, name="create"),
    path("", include("django.contrib.auth.urls")),
]
