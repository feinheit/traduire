from authlib.email import decode
from authlib.google import GoogleOAuth2Client
from authlib.views import (
    REDIRECT_COOKIE_NAME,
    EmailRegistrationForm,
    retrieve_next,
    set_next_cookie,
)
from django.contrib import auth, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from accounts.forms import UserForm
from accounts.models import User


def logout(request):
    auth.logout(request)
    messages.success(request, _("You have been signed out."))
    response = redirect("login")
    response.delete_cookie("login_hint")
    return response


@never_cache
@set_next_cookie
def sso(request, sso_client_class=GoogleOAuth2Client):
    auth_params = request.GET.dict()
    auth_params.setdefault("login_hint", request.COOKIES.get("login_hint", ""))
    if request.GET.get("select"):
        auth_params["prompt"] = sso_client_class.prompt
    client = sso_client_class(request, authorization_params=auth_params)

    if not request.GET.get("code"):
        return redirect(client.get_authentication_url())

    try:
        user_data = client.get_user_data()
    except Exception:
        messages.error(request, _("Error while fetching user data. Please try again."))
        return redirect("login")

    email = user_data.get("email")
    user = auth.authenticate(request, email=email)
    if user and user.is_active:
        auth.login(request, user)
        response = redirect(retrieve_next(request) or "/")
        response.delete_cookie(REDIRECT_COOKIE_NAME)
        response.set_cookie("login_hint", user.email, expires=180 * 86400)
        return response

    if User.objects.filter(email=email).exists():
        messages.error(
            request, _("The user with email address %s is inactive.") % email
        )
        response = HttpResponseRedirect("{}?error=1".format(reverse("login")))
        response.delete_cookie("login_hint")
        return response

    request.session["user_data"] = {
        "email": email,
        "full_name": user_data.get("full_name", ""),
    }
    response = redirect("create")
    response.set_cookie("login_hint", email, expires=180 * 86400)
    return response


def register(request, *, code=None):
    if code is None:
        args = [request.POST] if request.method == "POST" else []
        form = EmailRegistrationForm(*args, request=request)
        if form.is_valid():
            form.send_mail()
            messages.success(request, _("Please check your mailbox."))
            return redirect(".")
        return render(request, "registration/register.html", {"form": form})

    try:
        email, _payload = decode(code, max_age=3600)
    except ValidationError as exc:
        [messages.error(request, msg) for msg in exc.messages]
        return redirect("login")

    if User.objects.filter(email=email).exists():
        messages.error(
            request,
            _("An account with the email address {email} exists already.").format(
                email=email
            ),
        )
        return redirect("login")

    request.session["user_data"] = {"email": email}
    return redirect("create")


def create(request):
    user_data = request.session.get("user_data")
    if not user_data:
        messages.error(
            request, _("Verified user data couldn't be found. Please try again.")
        )
        return redirect("login")

    args = [request.POST] if request.method == "POST" else []
    user = User(**user_data)
    form = UserForm(*args, instance=user)
    if form.is_valid():
        form.save()

        auth.login(request, auth.authenticate(request, email=user.email))
        messages.info(request, _("Welcome, {}!").format(user.get_full_name()))
        return HttpResponseRedirect("/")

    return render(request, "registration/register.html", {"form": form})
