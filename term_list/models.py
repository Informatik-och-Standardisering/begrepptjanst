
from typing import TYPE_CHECKING, cast

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    # Import for type checking only; a local stub is present for mypy.
    from simple_history.models import HistoricalRecords
else:
    try:
        from simple_history.models import HistoricalRecords
    except Exception:
        HistoricalRecords = object  # runtime fallback when simple_history isn't available

DEFAULT_STATUS = "Ej Påbörjad"

CONCEPT_STATUS = (('Avråds', "Avråds"),
                  ('Beslutad', 'Beslutad'),
                  ('Pågår', 'Pågår'))

STATUS_CHOICES = (('Avråds', "Avråds"),
              ('Avställd', "Avställd"),
              ('Beslutad', 'Beslutad'),
              ('Publicera ej', 'Publicera ej'),
              ('Pågår', 'Pågår'),
              (DEFAULT_STATUS, DEFAULT_STATUS))

class Dictionary(models.Model):

    """The dictionary that a term belongs to. The same term can belong
    to more than one dictionary"""

    class Meta:
        verbose_name_plural = _("Ordböcker")
        verbose_name = _("Orbok")
        app_label = 'term_list'

    dictionary_id = models.AutoField(primary_key=True)
    dictionary_context = models.TextField(blank=True, null=True)
    dictionary_name = models.CharField(max_length=50)
    dictionary_long_name = models.CharField(max_length=255, null=True)
    groups = models.ManyToManyField(Group, related_name='dictionaries', blank=True)
    order = models.IntegerField(null=True)

    def __str__(self):
        """Return the name of the domain"""
        return self.dictionary_name

class ConceptExternalFiles(models.Model):

    """When a user requests a new term for definition they are able to upload
    files that give context. Those files are stored in thos model, and each
    term can have many files connected to it.
    """

    class Meta:
        verbose_name = _('Uppladdad fil')
        verbose_name_plural = _("Uppladdade filer")
        app_label = 'term_list'

    concept = models.ForeignKey("Concept", to_field='id', on_delete=models.CASCADE)
    comment = models.ForeignKey("ConceptComment", to_field='id', null=True, blank=True, on_delete=models.CASCADE)
    support_file = models.FileField(blank=True, null=True, upload_to='')

    def __str__(self):

        """Return the name of the file
        """
        return str(self.support_file)


class TaskOrderer(models.Model):

    """The model containing the person who has either submitted a request for
    a new term or has commented on an existing term.
    """

    class Meta:
        verbose_name = _("Beställare")
        verbose_name_plural = _("Beställaren")
        app_label = 'term_list'

    name = models.CharField(max_length=255, blank=True)
    create_date = models.DateTimeField(auto_now_add=True)
    finished_by_date = models.DateTimeField(null=True, blank=True)
    email = models.EmailField()
    concept = models.ForeignKey("Concept", to_field="id", on_delete=models.CASCADE, blank=True, null=False, related_name="task_requester")


    def __str__(self):

        """CaReturn the requesters name
        """
        return self.name

class Synonym(models.Model):

    """The model containings synonyms
    """

    SYNONYM_STATUS =  (('Avråds', "Avråds"),
                       ('Tillåten', "Tillåten"),
                       ('Inte angiven','Inte angiven'))

    class Meta:
        verbose_name_plural = _("Synonyms")
        verbose_name = _("Synonym")
        app_label = 'term_list'

    concept = models.ForeignKey("Concept", to_field="id", on_delete=models.CASCADE, blank=True, null=True, related_name="synonyms")
    synonym = models.CharField(max_length=255, blank=True, null=True)
    synonym_status = models.CharField(max_length=255, choices=SYNONYM_STATUS, default='Inte angiven')

    history = HistoricalRecords()

    def __str__(self):

        """Retrun the term that is the synonym"""
        return self.synonym

class ConceptComment(models.Model):

    """Model containing comments that are submitted by users against a
    particular term.
    """

    class Meta:
        verbose_name_plural = _('Begrepp kommentarer')
        verbose_name = _('Begrepp kommentar')
        app_label = 'term_list'

    concept = models.ForeignKey("Concept", to_field="id", on_delete=models.CASCADE, blank=True, null=True)
    usage_context = models.TextField()
    date = models.DateTimeField(auto_now_add=True)
    email = models.EmailField()
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=DEFAULT_STATUS)

    def __str__(self):

        """Retrun the term that is the synonym"""

        return f"{self.concept} den {self.date} av {self.name}"

class SearchTrack(models.Model):

    """Table that collects the IP address, the term search for and the
    timestamp.
    """

    class Meta:
        verbose_name_plural = _('Sök data')
        app_label = 'term_list'

    sök_term = models.CharField(max_length=255)
    sök_timestamp = models.DateTimeField(auto_now_add=True)
    records_returned = models.TextField()

    def __str__(self):
        return self.sök_term

class MetadataSearchTrack(models.Model):

    """Table taking note of which term definitions are clicked on.
    """

    class Meta:
        verbose_name = _('Sök Metadata')
        verbose_name_plural = _('Sök Metadata')
        app_label = 'term_list'

    sök_term = models.CharField(max_length=255)
    sök_timestamp = models.DateTimeField(auto_now_add=True)
    visitor_hash = models.CharField(max_length=64, null=True, blank=True)
    country = models.CharField(max_length=2, null=True, blank=True)

    def __str__(self):
        return self.sök_term

class DailySalt(models.Model):

    """Secret salt for the visitor hash, replaced every day.
    """

    class Meta:
        app_label = 'term_list'

    date = models.DateField(unique=True)
    salt = models.CharField(max_length=64)

class ConfigurationOptions(models.Model):

    class Meta:
        verbose_name = _('inställning')
        verbose_name_plural = _("Inställningar")
        app_label = 'term_list'

    name = models.CharField(max_length=255)
    description = models.TextField()
    visible = models.BooleanField()
    config = models.JSONField(blank=True, null=True)

    def __str__(self):
        return self.name

    @classmethod
    def get_status_choices(cls, name="status-and-colour"):
        try:
            config = cls.objects.get(name=name).config or {}
            return ((s["label"], s["label"]) for s in config.get("statuses", []))
        except cls.DoesNotExist:
            return []

    @classmethod
    def get_excluded_statuses(cls, name="status-exclude"):
        try:
            config = cls.objects.get(name=name).config or {}
            return [s["label"] for s in config.get("statuses", []) if s.get("exclude")]
        except cls.DoesNotExist:
            return []

class Concept(models.Model):

    class Meta:
        verbose_name = _('Begrepp')
        verbose_name_plural = _('Begrepp')
        app_label = 'term_list'

    term = models.CharField(max_length=255)  # The word itself
    definition = models.TextField(null=True, blank=True)  # Primary definition
    status = models.CharField(max_length=15, null=True)
    changed_at = models.DateTimeField(null=True, auto_now=True, verbose_name='Senaste ändring')
    created_at = models.DateTimeField(null=True, auto_now_add=True, verbose_name='Datum skapat')
    history = HistoricalRecords(['changed_at', 'definition'])

    # Annotated for static type checking (fixes pre-commit var-annotated errors)
    dictionaries: models.ManyToManyField = models.ManyToManyField(Dictionary, related_name='concept')

    history = HistoricalRecords()

    def __str__(self):
        return self.term

    def get_ordered_fields(self):
        # Default field order with fallback positions
        default_fields = {
            'status': {'display_name': 'Status', 'position': 0},
            'definition': {'display_name': 'Definition', 'position': 1},
        }

        return sorted(default_fields.items(), key=lambda x: x[1]['position'])

class GroupAttribute(models.Model):

    class Meta:
        unique_together = ('group', 'attribute')
        verbose_name = _("Attribut Grupp")
        verbose_name_plural = _("Attribut Grupper")

        ordering = ['position', 'attribute__name']

    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    attribute = models.ForeignKey('Attribute', on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)
    visible = models.BooleanField(default=True)


# Attribute Model
class Attribute(models.Model):

    class Meta:
        verbose_name = _("Attribut")
        verbose_name_plural = _("Attribut")

    name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=50, choices=[
        ('string', 'String'),
        ('integer', 'Integer'),
        ('decimal', 'Decimal'),
        ('boolean', 'Boolean'),
        ('text', 'Text'),
        ('url', 'URL'),
    ])
    description = models.TextField(null=True, blank=True)
    groups = models.ManyToManyField(Group, related_name='attributes', blank=True)

    def __str__(self):
        return self.name

# Attribute Value Model
class AttributeValue(models.Model):

    class Meta:
        verbose_name = _("Attribut Värde")
        verbose_name_plural = _("Attribute Värden")

    term = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name='attributes')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE)
    value_string = models.CharField(max_length=255, null=True, blank=True)
    value_text = models.TextField(null=True, blank=True)
    value_integer = models.IntegerField(null=True, blank=True)
    value_decimal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_url = models.URLField(null=True, blank=True)

    history = HistoricalRecords()

    def clean(self):
        """Ensure only one value field is populated."""
        value_fields = [
            self.value_string,
            self.value_text,
            self.value_integer,
            self.value_decimal,
            self.value_boolean,
            self.value_url,
        ]
        populated_fields = [field for field in value_fields if field not in [None, ""]]
        if len(populated_fields) > 1:
            raise ValidationError("Only one value field can contain data.")

    def get_value(self):
        attr = cast(Attribute, self.attribute)
        if attr.data_type == 'string':
            return self.value_string
        elif attr.data_type == 'text':
            return self.value_text
        elif attr.data_type == 'url':
            return self.value_url
        elif attr.data_type == 'integer':
            return self.value_integer
        elif attr.data_type == 'decimal':
            return self.value_decimal
        elif attr.data_type == 'boolean':
            return self.value_boolean
        return
    get_value.short_description = "Värde"  # type: ignore[attr-defined]

    def get_attribute_name(self):
        attr = cast(Attribute, self.attribute)
        return getattr(attr, "name", "")
    get_attribute_name.short_description = "Attribut"  # type: ignore[attr-defined]

    def __str__(self):
        value = self.get_value()
        attr = cast(Attribute, self.attribute)
        attr_name = getattr(attr, "name", "")
        return f"{attr_name}: {value}"
        #if value is not None else f"{attr_name}: <inget värde>"


class GroupHierarchy(models.Model):

    class Meta:
        verbose_name = _("Grupp Hierarki")
        verbose_name_plural = _("Group Hierarki")

    parent = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='subgroups')
    child = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='parent_groups')

    def __str__(self):
        child_name = getattr(self.child, "name", "")
        parent_name = getattr(self.parent, "name", "")
        return f"{child_name} (child of {parent_name})"
