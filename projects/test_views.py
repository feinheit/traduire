from unittest.mock import AsyncMock, patch

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.messages import get_messages
from django.test import AsyncClient, Client, TestCase
from django.test.utils import override_settings

from accounts.models import User
from projects.models import Catalog, Event, Project
from projects.translators import (
    TranslationError,
    _protect_variables,
    _restore_variables,
    _variable_name,
    find_variables,
    fix_nls,
)


def messages(response):
    return [m.message for m in get_messages(response.wsgi_request)]


class ProjectsTest(TestCase):
    def create_project_and_catalog(self):
        p = Project.objects.create(name="test", slug="test")
        c = p.catalogs.create(
            language_code="fr",
            domain="djangojs",
            pofile="""\
#: conf/strings.js frontend/intro/intro.js frontend/people/person.js
msgid "Continue"
msgstr "Continuer"

#: conf/strings.js
msgid "Copied code!"
msgstr "Code copié !"

#: fmw/dashboard/classes/forms.py
#, python-format
msgid "Successfully reset the password of %(count)s student."
msgid_plural "Successfully reset passwords of %(count)s students."
msgstr[0] "Réinitialisation du mot de passe de %(count)s élève."
msgstr[1] "Réinitialisation des mots de passe de %(count)s élèves ."
""",
        )
        return p, c

    def test_project_access(self):
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        p, _c = self.create_project_and_catalog()

        p2 = Project.objects.create(name="test2", slug="test2")
        user = User.objects.create_user("user@example.com", "user")
        user.projects.add(p2)
        u_client = Client()
        u_client.force_login(user)

        r = su_client.get("/", headers={"accept-language": "en"})
        self.assertContains(r, '<a href="/test/">test</a>')
        self.assertContains(r, '<a href="/test2/">test2</a>')

        r = u_client.get("/", headers={"accept-language": "en"})
        self.assertNotContains(r, '<a href="/test/">test</a>')
        self.assertContains(r, '<a href="/test2/">test2</a>')

        r = su_client.get(p.get_absolute_url(), headers={"accept-language": "en"})
        self.assertContains(r, f"token = &quot;{superuser.token}&quot;")
        self.assertContains(
            r,
            '<a href="/test/fr/djangojs/">French, djangojs (100%)</a>',
        )

        r = su_client.get("/traduire.toml")
        self.assertContains(r, f'token = "{superuser.token}"')

        r = su_client.get("/test/messages.csv")
        self.assertContains(r, ",Continue,")

        r = u_client.get(p.get_absolute_url(), headers={"accept-language": "en"})
        self.assertEqual(r.status_code, 404)

        r = u_client.get(p2.get_absolute_url(), headers={"accept-language": "en"})
        self.assertEqual(r.status_code, 200)

    def test_filtering(self):
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        _p, c = self.create_project_and_catalog()

        r = su_client.get(c.get_absolute_url(), headers={"accept-language": "en"})
        self.assertContains(r, "msgid_0")
        self.assertContains(
            r,
            '<input type="hidden" name="msgid_1" value="Copied code!" id="id_msgid_1">',
        )

        r = su_client.get(
            c.get_absolute_url() + "?start=1000", headers={"accept-language": "en"}
        )
        self.assertContains(r, "msgid_0")
        self.assertContains(
            r,
            '<input type="hidden" name="msgid_1" value="Copied code!" id="id_msgid_1">',
        )

        r = su_client.get(
            c.get_absolute_url() + "?start=1", headers={"accept-language": "en"}
        )
        self.assertContains(r, "msgid_0")
        self.assertContains(
            r,
            '<input type="hidden" name="msgid_0" value="Copied code!" id="id_msgid_0">',
        )

        r = su_client.get(
            c.get_absolute_url() + "?pending=on", headers={"accept-language": "en"}
        )
        self.assertNotContains(r, "msgid_0")

        r = su_client.get(
            c.get_absolute_url() + "?query=bla", headers={"accept-language": "en"}
        )
        self.assertNotContains(r, "msgid_0")

        r = su_client.get(
            c.get_absolute_url() + "?start=a", headers={"accept-language": "en"}
        )
        self.assertRedirects(r, c.get_absolute_url())

    def test_api(self):
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        p, c = self.create_project_and_catalog()

        # API test
        r = su_client.get(
            "/api/pofile/test/fr/djangojs/",
            headers={"x-cli-api": "anything"},
        )
        self.assertEqual(r.status_code, 400)

        r = su_client.get(
            "/api/pofile/test/fr/djangojs/",
            headers={"x-cli-api": settings.CLI_API},
        )
        self.assertEqual(r.status_code, 403)

        r = su_client.get(
            "/api/pofile/not-exists/fr/djangojs/",
            headers={"x-token": superuser.token, "x-cli-api": settings.CLI_API},
        )
        self.assertEqual(r.status_code, 404)

        r = su_client.get(
            "/api/pofile/test/fr/djangojs/",
            headers={"x-token": superuser.token, "x-cli-api": settings.CLI_API},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content.decode("utf-8"), c.pofile)

        r = su_client.patch(
            "/api/pofile/test/fr/djangojs/",
            headers={"x-token": superuser.token, "x-cli-api": settings.CLI_API},
        )
        self.assertEqual(r.status_code, 405)

        r = su_client.get(
            "/api/pofile/test/de/djangojs/",
            headers={"x-token": superuser.token, "x-cli-api": settings.CLI_API},
        )
        self.assertEqual(r.status_code, 404)

        r = su_client.post(
            "/api/pofile/test/fr/djangojs/",
            headers={"x-token": superuser.token, "x-cli-api": settings.CLI_API},
            data=b"""\
#: conf/strings.js frontend/intro/intro.js frontend/people/person.js
msgid "Continue"
msgstr "Blub"

#: conf/strings.js
msgid "Copied code!"
msgstr ""

msgid "Hello World"
msgstr "Blab"
""",
            content_type="text/plain",
        )

        c.refresh_from_db()

        self.assertIn(
            """\
msgid "Continue"
msgstr "Continuer"
""",
            c.pofile,
        )

        self.assertIn(
            """\
msgid "Hello World"
msgstr ""
""",
            c.pofile,
        )

        # Different language!
        r = su_client.put(
            "/api/pofile/test/de/djangojs/",
            headers={"x-token": superuser.token, "x-cli-api": settings.CLI_API},
            data=b"""\
#: conf/strings.js frontend/intro/intro.js frontend/people/person.js
msgid "Continue"
msgstr "Blub"

#: conf/strings.js
msgid "Copied code!"
msgstr ""

msgid "Hello World"
msgstr "Blab"
""",
        )

        c = p.catalogs.order_by("id").last()

        self.assertIn(
            """\
#: conf/strings.js frontend/intro/intro.js frontend/people/person.js
msgid "Continue"
msgstr "Blub"
""",
            c.pofile,
        )

        self.assertIn(
            """\
msgid "Hello World"
msgstr "Blab"
""",
            c.pofile,
        )

        # Delete catalogs through the API. Not currently exposed in the CLI.
        r = su_client.delete(
            "/api/pofile/test/fr/djangojs/",
            headers={"x-token": superuser.token, "x-cli-api": settings.CLI_API},
        )
        self.assertEqual(r.status_code, 204)

        r = su_client.delete(
            "/api/pofile/test/fr/djangojs/",
            headers={"x-token": superuser.token, "x-cli-api": settings.CLI_API},
        )
        self.assertEqual(r.status_code, 404)

    def test_updating(self):
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        p, c = self.create_project_and_catalog()

        with override_settings(DEEPL_AUTH_KEY="hello"):
            r = su_client.get(
                c.get_absolute_url(),
                headers={"accept-language": "en"},
            )
            self.assertContains(r, "data-suggest")

        with override_settings(DEEPL_AUTH_KEY=""):
            r = su_client.get(
                c.get_absolute_url(),
                headers={"accept-language": "en"},
            )
            self.assertNotContains(r, "data-suggest")

        r = su_client.post(
            c.get_absolute_url(),
            {
                "msgid_0": "Continue",
                "msgstr_0": "Onward!",  # Obviously incorrect.
                "fuzzy_0": "on",
                "msgid_1": "not exists",
                "msgstr_1": "not exists",
                "fuzzy_1": "",
            },
            headers={"accept-language": "en"},
        )
        self.assertRedirects(r, c.get_absolute_url() + "?start=0")

        c.refresh_from_db()
        self.assertIn(
            """\
#: conf/strings.js frontend/intro/intro.js frontend/people/person.js
#, fuzzy
msgid "Continue"
msgstr "Onward!"
""",
            c.pofile,
        )

        # Didn't exist, is ignored
        self.assertNotIn("not exists", c.pofile)

        r = su_client.post(
            c.get_absolute_url() + "?query=continue",
            {
                "msgid_0": "Continue",
                "msgstr_0": "Onward!",  # Obviously incorrect.
                "fuzzy_0": "",
            },
            headers={"accept-language": "en"},
        )
        self.assertRedirects(r, c.get_absolute_url() + "?query=continue&start=0")

        c.refresh_from_db()
        self.assertIn(
            """\
#: conf/strings.js frontend/intro/intro.js frontend/people/person.js
msgid "Continue"
msgstr "Onward!"
""",
            c.pofile,
        )

        r = su_client.post(
            c.get_absolute_url() + "?query=continue",
            {
                "msgid_0": "Continue",
                "msgstr_0": "Onward!",  # Obviously incorrect.
                "fuzzy_0": "",
            },
            headers={"accept-language": "en"},
        )
        self.assertRedirects(
            r,
            c.get_absolute_url() + "?query=continue&start=0",
            fetch_redirect_response=False,
        )

        response = su_client.get(c.get_absolute_url())
        self.assertEqual(messages(response), ["No changes detected."])

        c = p.catalogs.create(
            language_code="es",
            domain="djangojs",
            pofile="""\
#: fmw/dashboard/classes/forms.py
#, python-format
msgid "Successfully reset the password of %(count)s student."
msgid_plural "Successfully reset passwords of %(count)s students."
msgstr[0] "Réinitialisation du mot de passe de %(count)s élève."
msgstr[1] "Réinitialisation des mots de passe de %(count)s élèves ."
""",
        )
        r = su_client.post(
            c.get_absolute_url(),
            {
                "msgid_0": "Successfully reset the password of %(count)s student.",
                "msgstr_0:0": "Blub %(count)s",
                "msgstr_0:1": "Blab %(count)s",
            },
            headers={"accept-language": "en"},
        )

        c.refresh_from_db()
        self.assertIn(
            """\
#: fmw/dashboard/classes/forms.py
#, python-format
msgid "Successfully reset the password of %(count)s student."
msgid_plural "Successfully reset passwords of %(count)s students."
msgstr[0] "Blub %(count)s"
msgstr[1] "Blab %(count)s"
""",
            c.pofile,
        )

        # print(c.pofile)
        # print(list(c.po))
        # print(r, r.content.decode("utf-8"))

    def test_admin(self):
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        self.create_project_and_catalog()

        p2 = Project.objects.create(name="test2", slug="test2")
        user = User.objects.create_user("user@example.com", "user")
        user.projects.add(p2)

        with override_settings(DEBUG=True):  # Disable ManifestStaticFilesStorage
            r = su_client.get("/admin/projects/project/")

        self.assertContains(r, '<td class="field-explicit_users">-</td>')
        self.assertContains(
            r, '<td class="field-explicit_users"> &lt;user@example.com&gt;</td>'
        )

    async def test_suggest(self):
        c = AsyncClient()

        r = await c.get("/api/suggest/")
        self.assertEqual(r.status_code, 405)

        r = await c.post("/api/suggest/")
        self.assertEqual(r.status_code, 403)

        user = await sync_to_async(User.objects.create_user)("user@example.com", "user")
        await c.aforce_login(user)

        r = await c.post("/api/suggest/")
        self.assertEqual(r.status_code, 400)

        with patch(
            "projects.views.translators.translate_by_deepl",
            AsyncMock(return_value="Bonjour"),
        ):
            r = await c.post(
                "/api/suggest/", {"language_code": "fr", "msgid": "Anything"}
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), {"msgstr": "Bonjour"})

        mock = AsyncMock()
        mock.side_effect = TranslationError("Oops")
        with patch("projects.views.translators.translate_by_deepl", mock):
            r = await c.post(
                "/api/suggest/", {"language_code": "fr", "msgid": "Anything"}
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), {"error": "Oops"})

    def test_invalid_catalog(self):
        c = Catalog(language_code="it", domain="django", pofile="blub")
        self.assertEqual(str(c), "Italian, django (Invalid)")

    def test_fix_nls(self):
        for test in [
            ("", "", ""),
            ("a\nb", "a\r\nb", "a\nb"),
            ("\na", "a", "\na"),
            ("a\n", "a", "a\n"),
            ("a", "\na\n", "a"),
            ("a", "\n", ""),
        ]:
            with self.subTest(test=test):
                self.assertEqual(fix_nls(test[0], test[1]), test[2])

    def test_protect_restore_variables(self):
        cases = [
            # No placeholders — unchanged
            ("Hello world", "Hello world"),
            # %(name)s style
            ("Reset %(count)s password.", "Reset %(count)s password."),
            ("%(count)d items", "%(count)d items"),
            # {name} style
            ("Hello {name}!", "Hello {name}!"),
            # {0} positional
            ("Item {0} of {1}", "Item {0} of {1}"),
            # {name:spec} with format spec
            ("Value: {amount:.2f}", "Value: {amount:.2f}"),
            # Mixed styles in same string
            ("%(user)s has {count} items", "%(user)s has {count} items"),
            # Multiple of same style
            ("{first} and {second}", "{first} and {second}"),
        ]
        for original, expected in cases:
            with self.subTest(original=original):
                protected, placeholders = _protect_variables(original)
                restored = _restore_variables(protected, placeholders)
                self.assertEqual(restored, expected)

    def test_protect_variables_hides_placeholders(self):
        """The protected text should contain no original placeholder syntax."""
        text = "Hello %(name)s, you have {count} messages."
        protected, placeholders = _protect_variables(text)
        self.assertNotIn("%(name)s", protected)
        self.assertNotIn("{count}", protected)
        self.assertEqual(len(placeholders), 2)
        self.assertIn("%(name)s", placeholders)
        self.assertIn("{count}", placeholders)

    def test_protect_variables_keeps_name_visible(self):
        """Variable names should appear in the tag content for translation context."""
        protected, _ = _protect_variables("Hello %(username)s, you have {count} items.")
        self.assertIn("username", protected)
        self.assertIn("count", protected)

    def test_variable_name_extraction(self):
        cases = [
            ("%(count)s", "count"),
            ("%(user_name)d", "user_name"),
            ("{hello}", "hello"),
            ("{0}", "0"),
            ("{amount:.2f}", "amount"),
        ]
        for placeholder, expected in cases:
            with self.subTest(placeholder=placeholder):
                self.assertEqual(_variable_name(placeholder), expected)

    def test_find_variables(self):
        self.assertEqual(find_variables("No variables here"), [])
        self.assertEqual(find_variables("Hello %(name)s!"), ["%(name)s"])
        self.assertEqual(find_variables("Hello {name}!"), ["{name}"])
        self.assertEqual(
            find_variables("%(user)s has {count} items"),
            ["%(user)s", "{count}"],
        )

    def test_variable_hint_in_help_text(self):
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        _p, c = self.create_project_and_catalog()

        r = su_client.get(c.get_absolute_url(), headers={"accept-language": "en"})
        # The plural entry has %(count)s — it should appear as a hint
        self.assertContains(r, "<code>%(count)s</code>")

    def test_variable_validation_on_save(self):
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        _p, c = self.create_project_and_catalog()

        # The plural entry is the third entry (index 2) in the catalog
        # Submit a translation that drops %(count)s
        r = su_client.post(
            c.get_absolute_url(),
            {
                "msgid_2": "Successfully reset the password of %(count)s student.",
                "msgstr_2:0": "Réinitialisation sans la variable.",
                "msgstr_2:1": "Réinitialisation sans la variable.",
            },
            headers={"accept-language": "en"},
        )
        # Should re-render the form with errors, not redirect
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Missing variables")

    def test_msgid_with_whitespace_is_translatable(self):
        """msgid values with leading/trailing whitespace must not be stripped
        before matching against the catalog, otherwise the entry is silently
        skipped and appears un-saveable (issue #13)."""
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        p = Project.objects.create(name="ws", slug="ws")
        c = p.catalogs.create(
            language_code="fr",
            domain="django",
            pofile='msgid ""\n"\\nHello with leading newline"\nmsgstr ""\n',
        )

        r = su_client.post(
            c.get_absolute_url(),
            {
                "msgid_0": "\nHello with leading newline",
                "msgstr_0": "\nBonjour avec saut de ligne",
            },
            headers={"accept-language": "en"},
        )
        self.assertRedirects(r, c.get_absolute_url() + "?start=0")

        c.refresh_from_db()
        self.assertIn("Bonjour avec saut de ligne", c.pofile)

    def test_msgid_with_crlf_from_browser_is_translatable(self):
        """Browsers normalize newlines to CRLF in form submissions. When the
        catalog msgid contains an embedded LF, the round-tripped hidden msgid
        arrives with CRLF and must still match the catalog entry — otherwise
        the entry is silently skipped (issue #13)."""
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        p = Project.objects.create(name="crlf", slug="crlf")
        c = p.catalogs.create(
            language_code="fr",
            domain="django",
            pofile='msgid ""\n"\\nHello with leading newline"\nmsgstr ""\n',
        )

        r = su_client.post(
            c.get_absolute_url(),
            {
                "msgid_0": "\r\nHello with leading newline",
                "msgstr_0": "\r\nBonjour avec saut de ligne",
            },
            headers={"accept-language": "en"},
        )
        self.assertRedirects(r, c.get_absolute_url() + "?start=0")

        c.refresh_from_db()
        self.assertIn("Bonjour avec saut de ligne", c.pofile)
        # The stored msgstr must keep LF, not CRLF.
        self.assertNotIn("\r", c.pofile)

    def test_valid_translation_with_variables_saves(self):
        superuser = User.objects.create_superuser("admin@example.com", "admin")
        su_client = Client()
        su_client.force_login(superuser)

        _p, c = self.create_project_and_catalog()

        # Submit a translation that keeps %(count)s
        r = su_client.post(
            c.get_absolute_url(),
            {
                "msgid_2": "Successfully reset the password of %(count)s student.",
                "msgstr_2:0": "Réinitialisation de %(count)s mot de passe.",
                "msgstr_2:1": "Réinitialisation de %(count)s mots de passe.",
            },
            headers={"accept-language": "en"},
        )
        self.assertRedirects(r, c.get_absolute_url() + "?start=0")

    def test_event_save(self):
        user = User.objects.create_superuser("admin@example.com", "admin")
        p, c = self.create_project_and_catalog()

        p2 = Project.objects.create(name="test2", slug="test2")

        e = Event.objects.create(
            user=user,
            action=Event.Action.CATALOG_CREATED,
            catalog=c,
        )
        self.assertEqual(str(e), "created catalog")
        self.assertEqual(e.project, p)

        e = Event.objects.create(
            user=user,
            action=Event.Action.CATALOG_CREATED,
            catalog=c,
            project=p2,  # Makes no sense but is allowed
        )
        self.assertEqual(str(e), "created catalog")
        self.assertEqual(e.project, p2)

        e = Event.objects.create(
            action=Event.Action.CATALOG_CREATED,
        )
        self.assertEqual(str(e), "created catalog")

        e = Event.objects.create(
            user=user,
            action=Event.Action.CATALOG_CREATED,
            project=p2,
        )
        self.assertEqual(str(e), "created catalog")

        self.assertEqual(
            list(Event.objects.values_list("action", flat=True)),
            [
                "catalog-created",
                "catalog-created",
                "catalog-created",
                "catalog-created",
                "project-created",
                "project-created",
                "user-created",
            ],
        )

    def test_event_log(self):
        self.create_project_and_catalog()

        self.assertEqual(
            list(Event.objects.values_list("action", flat=True)),
            ["project-created"],
        )


class FeedsTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser("admin@example.com", "admin")
        self.user = User.objects.create_user("user@example.com", "user")

        self.p1 = Project.objects.create(name="Project One", slug="p1")
        self.p2 = Project.objects.create(name="Project Two", slug="p2")
        self.user.projects.add(self.p2)

        Event.objects.create(
            user=self.superuser,
            action=Event.Action.CATALOG_UPDATED,
            project=self.p1,
        )
        Event.objects.create(
            user=self.user,
            action=Event.Action.CATALOG_REPLACED,
            project=self.p2,
        )

    def test_global_feed_no_token(self):
        r = self.client.get("/feed.rss")
        self.assertEqual(r.status_code, 404)

    def test_global_feed_invalid_token(self):
        r = self.client.get("/feed.rss?token=bad")
        self.assertEqual(r.status_code, 404)

    def test_global_feed_staff_sees_all_projects(self):
        r = self.client.get(f"/feed.rss?token={self.superuser.token}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/rss+xml; charset=utf-8")
        content = r.content.decode()
        self.assertIn("Project One", content)
        self.assertIn("Project Two", content)

    def test_global_feed_user_sees_own_projects_only(self):
        r = self.client.get(f"/feed.rss?token={self.user.token}")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        self.assertNotIn("Project One", content)
        self.assertIn("Project Two", content)

    def test_project_feed_no_token(self):
        r = self.client.get("/p1/feed.rss")
        self.assertEqual(r.status_code, 404)

    def test_project_feed_invalid_token(self):
        r = self.client.get("/p1/feed.rss?token=bad")
        self.assertEqual(r.status_code, 404)

    def test_project_feed_no_access(self):
        r = self.client.get(f"/p1/feed.rss?token={self.user.token}")
        self.assertEqual(r.status_code, 404)

    def test_project_feed_returns_rss(self):
        r = self.client.get(f"/p1/feed.rss?token={self.superuser.token}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/rss+xml; charset=utf-8")
        content = r.content.decode()
        self.assertIn("Project One", content)
        self.assertNotIn("Project Two", content)

    def test_project_feed_digest_groups_by_day(self):
        # Add a second event on the same project — should produce one digest item
        Event.objects.create(
            user=self.superuser,
            action=Event.Action.CATALOG_REPLACED,
            project=self.p1,
        )
        r = self.client.get(f"/p1/feed.rss?token={self.superuser.token}")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        # Both actions should appear in the description of the single digest item
        self.assertIn("updated catalog", content)
        self.assertIn("replaced catalog", content)
        # Only one <item> since both events are on the same day
        self.assertEqual(content.count("<item>"), 1)

    def test_feed_excludes_login_events(self):
        Event.objects.create(
            user=self.superuser,
            action=Event.Action.USER_LOGGED_IN,
            project=self.p1,
        )
        r = self.client.get(f"/p1/feed.rss?token={self.superuser.token}")
        content = r.content.decode()
        self.assertNotIn("user logged in", content)

    def test_feed_unique_guid_per_project_day(self):
        r = self.client.get(f"/feed.rss?token={self.superuser.token}")
        content = r.content.decode()
        self.assertIn('<guid isPermaLink="false">p1-', content)
        self.assertIn('<guid isPermaLink="false">p2-', content)
