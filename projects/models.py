import datetime as dt
from functools import cached_property

import polib
from django.conf import global_settings, settings
from django.core import validators
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.timesince import timesince
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _

from accounts.models import User


class ChoicesCharField(models.CharField):
    """
    ``models.CharField`` with choices, which makes the migration framework
    always ignore changes to ``choices``, ever.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("choices", [("", "")])  # Non-empty choices for get_*_display
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, _path, args, kwargs = super().deconstruct()
        kwargs["choices"] = [("", "")]
        return name, "django.db.models.CharField", args, kwargs


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True

    @property
    def pretty_timesince(self):
        return timesince(self.updated_at, depth=1)


class ProjectQuerySet(models.QuerySet):
    def for_user(self, user):
        return self if user.is_staff else self.filter(users=user)

    def groups(self):
        groups = {"active": [], "inactive": [], "any": bool(self)}
        cutoff = localtime() - dt.timedelta(days=60)
        localtime()
        for obj in self:
            groups["active" if obj.updated_at > cutoff else "inactive"].append(obj)
        return groups


class Project(TimestampedModel):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    name = models.CharField(_("name"), max_length=100)
    slug = models.SlugField(_("slug"), unique=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="projects",
        verbose_name=_("users"),
        blank=True,  # Only internal is fine.
        limit_choices_to={"is_staff": False},
    )
    _email_domains = models.TextField(
        _("email domains"),
        blank=True,
        help_text=_(
            "User accounts on these domains will automatically get access to this project. One domain per line."
        ),
    )

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = _("project")
        verbose_name_plural = _("projects")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("projects:project", kwargs={"slug": self.slug})

    @property
    def email_domains(self):
        return [v.strip() for v in self._email_domains.strip().splitlines()]

    def clean(self):
        validator = validators.DomainNameValidator(
            message=_("Some of the lines are not valid domain names.")
        )
        for domain in self.email_domains:
            validator(domain)

    def get_api_url(self):
        return f"/api/pofile/{self.slug}/"

    @cached_property
    def all_users(self):
        return User.objects.filter(
            Q(is_active=True) & (Q(is_staff=True) | Q(projects=self))
        )

    def toml(self, *, request):
        return f"""\
[[project]]
name = "{self.name}"
token = "{request.user.token}"
url = "{request.build_absolute_uri(self.get_api_url())}"
path = "" # Add the absolute path of your local project!
"""


class CatalogQuerySet(models.QuerySet):
    def for_user(self, user):
        return self if user.is_staff else self.filter(project__users=user)


class Catalog(TimestampedModel):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="catalogs",
        verbose_name=_("project"),
    )
    language_code = ChoicesCharField(
        _("language"), max_length=10, choices=global_settings.LANGUAGES
    )
    domain = models.CharField(_("domain"), max_length=20, default="django")
    pofile = models.TextField("pofile")

    objects = CatalogQuerySet.as_manager()

    class Meta:
        ordering = ["language_code", "domain"]
        unique_together = [("project", "language_code", "domain")]
        verbose_name = _("catalog")
        verbose_name_plural = _("catalogs")

    def __str__(self):
        try:
            percent_translated = f"{self.po.percent_translated()}%"
        except Exception:
            percent_translated = "Invalid"
        return (
            f"{self.get_language_code_display()}, {self.domain} ({percent_translated})"
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.project.save()

    save.alters_data = True

    def get_absolute_url(self):
        return reverse(
            "projects:catalog",
            kwargs={
                "project": self.project.slug,
                "language_code": self.language_code,
                "domain": self.domain,
            },
        )

    @cached_property
    def po(self):
        return polib.pofile(self.pofile, wrapwidth=0)


class Event(models.Model):
    class Action(models.TextChoices):
        USER_CREATED = "user-created", _("user created")
        USER_LOGGED_IN = "user-logged-in", _("user logged in")
        PROJECT_CREATED = "project-created", _("created project")
        PROJECT_ACCESS_GRANTED = "project-access-granted", _("project access granted")
        CATALOG_CREATED = "catalog-created", _("created catalog")
        CATALOG_UPDATED = "catalog-updated", _("updated catalog")
        CATALOG_SUBMITTED = "catalog-submitted", _("submitted catalog")
        CATALOG_REPLACED = "catalog-replaced", _("replaced catalog")
        CATALOG_DELETED = "catalog-deleted", _("deleted catalog")

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="events",
        verbose_name=_("user"),
    )
    action = models.CharField(_("action"), max_length=40, choices=Action)

    project = models.ForeignKey(
        Project,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="events",
        verbose_name=_("project"),
    )
    catalog = models.ForeignKey(
        Catalog,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="events",
        verbose_name=_("catalog"),
    )

    user_string = models.CharField(_("user string"), max_length=1000)
    project_string = models.CharField(_("project string"), max_length=1000)
    catalog_string = models.CharField(_("catalog string"), max_length=1000)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("event")
        verbose_name_plural = _("events")

    def __str__(self):
        return self.get_action_display()

    def save(self, *args, **kwargs):
        if not self.project and self.catalog:
            self.project = self.catalog.project
        if not self.user_string and self.user:
            self.user_string = str(self.user)
        if not self.project_string and self.project:
            self.project_string = str(self.project)
        if not self.catalog_string and self.catalog:
            self.catalog_string = str(self.catalog)
        super().save(*args, **kwargs)

    save.alters_data = True

    def as_html(self):
        return format_html(
            """\
<p>
  <small>{created_at}</small><br>
  {user} {action} {catalog}
</p>
            """,
            created_at=date_format(localtime(self.created_at), "Y-m-d H:i"),
            action=self.get_action_display(),
            user=self.user or self.user_string,
            project=self.project or self.project_string,
            catalog=self.catalog_string,
        )
