from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.utils.translation import deactivate_all

from accounts import views
from accounts.models import User


def messages(response):
    return [m.message for m in get_messages(response.wsgi_request)]


class FakeFlow:
    EMAIL = "user@example.com"
    RAISE_EXCEPTION = False
    prompt = "consent select_account"

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def get_authentication_url(self):
        auth_params = self.kwargs["authorization_params"]
        return f"http://example.com/auth/?prompt={auth_params.get('prompt', '')}"

    def get_user_data(self):
        if self.RAISE_EXCEPTION:
            raise Exception("Email not verified")  # noqa: TRY002
        return {"email": self.EMAIL}


class MicrosoftFakeFlow(FakeFlow):
    prompt = "select_account"


views.GoogleOAuth2Client = FakeFlow
views.MicrosoftOAuth2Client = MicrosoftFakeFlow


@override_settings(STAFF_EMAIL_DOMAINS=["example.com"])
class LoginTestCase(TestCase):
    def tearDown(self):
        deactivate_all()

    def test_login(self):
        """Basic login and logout redirects"""
        user = User.objects.create_user("user@example.com", "password")

        self.assertRedirects(self.client.get("/"), "/accounts/login/?next=%2F")

        self.client.login(email=user.email)

        self.assertContains(
            self.client.get("/"), 'action="/accounts/logout/"', 1, status_code=200
        )
        # self.assertRedirects(self.client.get("/accounts/login/"), "/")

    def test_login_hint_removal_on_logout(self):
        """The login_hint cookie is removed when logging out explicitly"""
        user = User.objects.create_user("user@example.com", "password")

        self.client.login(email=user.email)
        self.client.cookies.load({"login_hint": "test@example.com"})

        self.assertEqual(
            self.client.cookies.get("login_hint").value, "test@example.com"
        )
        response = self.client.get("/accounts/logout/")
        self.assertRedirects(response, "/accounts/login/")

        self.assertEqual(self.client.cookies.get("login_hint").value, "")

    def test_server_flow(self):
        """Exercise the OAuth2 webserver flow implementation"""
        FakeFlow.EMAIL = "user@example.org"
        FakeFlow.RAISE_EXCEPTION = False

        client = Client()

        response = client.get("/accounts/login/")
        self.assertNotContains(response, "select=1")

        response = client.get("/accounts/google-sso/")
        self.assertRedirects(
            response, "http://example.com/auth/?prompt=", fetch_redirect_response=False
        )

        response = client.get(
            "/accounts/google-sso/?code=x", headers={"accept-language": "en"}
        )
        self.assertRedirects(response, "/accounts/create/")

        response = client.get("/accounts/login/?error=1")
        self.assertContains(response, "select=1")

        response = client.get("/accounts/google-sso/?select=1")
        self.assertRedirects(
            response,
            "http://example.com/auth/?prompt=consent select_account",
            fetch_redirect_response=False,
        )

        FakeFlow.EMAIL = "user@example.com"
        response = client.get(
            "/accounts/google-sso/?code=x", headers={"accept-language": "en"}
        )
        self.assertRedirects(response, "/accounts/create/")

        response = client.post(
            "/accounts/create/",
            {
                "full_name": "Blub Blubber",
                "new_password1": "blubblubblubblub123412341234",
                "new_password2": "blubblubblubblub123412341234",
            },
            headers={"accept-language": "en"},
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)

        response = client.get("/")
        self.assertEqual(messages(response), ["Welcome, Blub Blubber!"])
        self.assertEqual(client.cookies.get("login_hint").value, FakeFlow.EMAIL)

        client = Client()
        response = client.get("/accounts/google-sso/?code=x")
        self.assertRedirects(response, "/")
        self.assertEqual(messages(response), [])
        self.assertEqual(client.cookies.get("login_hint").value, FakeFlow.EMAIL)

        # Disabled user
        User.objects.update(is_active=False)
        client = Client()
        FakeFlow.EMAIL = "user@example.com"
        response = client.get(
            "/accounts/google-sso/?code=x", headers={"accept-language": "en"}
        )
        self.assertRedirects(response, "/accounts/login/?error=1")
        self.assertEqual(
            messages(response),
            ["The user with email address user@example.com is inactive."],
        )

    def test_microsoft_server_flow(self):
        """Exercise the OAuth2 webserver flow implementation for Microsoft SSO"""
        MicrosoftFakeFlow.EMAIL = "user@example.org"
        MicrosoftFakeFlow.RAISE_EXCEPTION = False

        client = Client()

        response = client.get("/accounts/microsoft-sso/")
        self.assertRedirects(
            response, "http://example.com/auth/?prompt=", fetch_redirect_response=False
        )

        response = client.get("/accounts/microsoft-sso/?select=1")
        self.assertRedirects(
            response,
            "http://example.com/auth/?prompt=select_account",
            fetch_redirect_response=False,
        )

        MicrosoftFakeFlow.EMAIL = "user@example.com"
        response = client.get(
            "/accounts/microsoft-sso/?code=x", headers={"accept-language": "en"}
        )
        self.assertRedirects(response, "/accounts/create/")

        response = client.post(
            "/accounts/create/",
            {
                "full_name": "Blub Blubber",
                "new_password1": "blubblubblubblub123412341234",
                "new_password2": "blubblubblubblub123412341234",
            },
            headers={"accept-language": "en"},
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)

        response = client.get("/")
        self.assertEqual(messages(response), ["Welcome, Blub Blubber!"])
        self.assertEqual(
            client.cookies.get("login_hint").value, MicrosoftFakeFlow.EMAIL
        )

        client = Client()
        response = client.get("/accounts/microsoft-sso/?code=x")
        self.assertRedirects(response, "/")
        self.assertEqual(messages(response), [])
        self.assertEqual(
            client.cookies.get("login_hint").value, MicrosoftFakeFlow.EMAIL
        )

        # Disabled user
        User.objects.update(is_active=False)
        client = Client()
        response = client.get(
            "/accounts/microsoft-sso/?code=x", headers={"accept-language": "en"}
        )
        self.assertRedirects(response, "/accounts/login/?error=1")
        self.assertEqual(
            messages(response),
            ["The user with email address user@example.com is inactive."],
        )

    def test_server_flow_user_data_failure(self):
        """Failing to fetch user data shouldn't produce an internal server error"""
        FakeFlow.EMAIL = "user@example.com"
        FakeFlow.RAISE_EXCEPTION = True

        response = self.client.get(
            "/accounts/google-sso/?code=x", headers={"accept-language": "de"}
        )
        self.assertRedirects(response, "/accounts/login/")
        self.assertEqual(
            messages(response),
            ["Fehler beim Abrufen von Benutzerdaten. Bitte versuchen Sie es erneut."],
        )

    def test_no_user_data(self):
        response = self.client.get(
            "/accounts/create/", headers={"accept-language": "en"}
        )
        self.assertRedirects(response, "/accounts/login/")
        self.assertEqual(
            messages(response),
            ["Verified user data couldn't be found. Please try again."],
        )
