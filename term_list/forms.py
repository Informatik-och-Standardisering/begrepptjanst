import json
import logging
import os
from typing import Any, Dict, Optional, cast

from django import forms
from django.core.exceptions import ValidationError
from django.forms.widgets import HiddenInput
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import (
    AttributeValue,
    Concept,
    ConceptExternalFiles,
    ConfigurationOptions,
    Dictionary,
    Synonym,
)

log = logging.getLogger(__name__)


class CustomDateInput(forms.DateInput):
    input_type = "date"


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        default_attrs = {
            "multiple": True,
            "aria-label": "Ladda upp filer som kan hjälpa oss",
            "aria-describedby": "file-upload-help",
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


class GroupFilteredModelForm(forms.ModelForm):
    """A form that filters choices based on the logged-in user's group membership."""

    def __init__(self, *args, **kwargs):
        # Pass the request user to the form
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # if self.user and not self.user.is_superuser:
        #     from pdb import set_trace; set_trace()
        #     self.filter_queryset()

    # def filter_queryset(self):
    #     user = self.user
    #     if user and not user.is_superuser:
    #         user_groups = user.groups.all()
    #         domain_ids = Dictionary.objects.filter(groups__in=user_groups).values_list('dictionary_id', flat=True)
    #         begrepp_ids = Concept.objects.filter(begrepp_fk__dictionary_id__in=domain_ids).values_list('id', flat=True)
    #         from pdb import set_trace; set_trace()
    #         self.fields['begrepp'].queryset = Concept.objects.filter(id__in=begrepp_ids)


class TermRequestForm(forms.Form):

    def __init__(self, *args, **kwargs):
        super(TermRequestForm, self).__init__(*args, **kwargs)
        self.fields["dictionary"].widget.attrs["readonly"] = True

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def clean_name(self):
        namn = self.cleaned_data.get("name")
        return namn

    def clean_email(self):
        epost = self.cleaned_data.get("email")
        return epost

    def clean_dictionary(self):

        dictionary = Dictionary.objects.filter(
            dictionary_long_name=self.cleaned_data.get("dictionary")
        ).first()
        # Assuming you're checking if the dictionary exists in the database
        if not dictionary:
            raise ValidationError(_("Ordboken existerar inte."))

        return dictionary

    def clean_context(self):
        context = self.cleaned_data.get("context")
        return context

    def clean_concept(self):
        concept = self.cleaned_data.get("concept")
        return concept

    concept = forms.CharField(
        max_length=254,
        label=_("Term som representerar begreppet"),
        widget=forms.TextInput,
    )
    dictionary = forms.CharField(max_length=64, label=_("Ordlista"))
    context = forms.CharField(
        widget=forms.Textarea, label=_("Beskriv hur begreppet används:")
    )
    name = forms.CharField(max_length=100, label=_("Namn"))
    email = forms.EmailField(max_length=254, label=_("Epost"))
    file_field = MultipleFileField(
        label=_("Bifogar en eller flera skärmklipp eller filer som kan hjälpa oss"),
        required=False,
    )


class PrettyDecodedJSONWidget(forms.Textarea):
    def format_value(self, value):
        try:
            # Handle stringified JSON
            if isinstance(value, str):
                value = json.loads(value)
            return json.dumps(value, indent=2, ensure_ascii=False)
        except Exception:
            return value


class ConfigurationOptionsForm(forms.ModelForm):
    class Meta:
        model = ConfigurationOptions
        fields = "__all__"
        widgets = {
            "config": PrettyDecodedJSONWidget(attrs={"cols": 80, "rows": 20}),
        }


class CommentTermForm(forms.Form):

    name = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "aria-label": "Ange ditt namn"}
        ),
        label="Namn",
        max_length=255,
    )
    epost = forms.EmailField(
        label="E-postadress",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "id": "prenumera",
                "placeholder": "E-postadress",
                "aria-label": "E-postadress",
            }
        ),
        required=True,
    )
    comment = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "aria-label": "Skriv din kommentar här",
            }
        ),
        max_length=2000,
        label="Kommentar",
    )

    term = forms.CharField(
        widget=forms.HiddenInput(
            attrs={"aria-hidden": "true"}  # Hidden input does not need a visible label
        )
    )

    file_field = MultipleFileField(
        label=_("Bifogar en/flera skärmklipp eller filer som kan hjälpa oss"),
        required=False,
    )


class SynonymInlineForm(forms.ModelForm):

    class Meta:
        model = Synonym
        fields = "__all__"
        labels = {"synonym": "Synonym"}

    def clean(self):
        super(SynonymInlineForm, self).clean()
        if self.cleaned_data.get("synonym") is None:
            self.add_error(
                "synonym",
                "Kan inte radera synonym med bak knappen, använder checkbox till höger",
            )


class ConceptExternalFilesInlineForm(forms.ModelForm):
    class Meta:
        model = ConceptExternalFiles
        fields = ("support_file",)  # explicit tuple

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # remove trailing ":" label suffix and set a friendly label
        self.label_suffix = ""
        fld = self.fields.get("support_file")
        if fld is not None:
            pass
            # fld.label = "Bifogad fil"
            # optional: tweak widget attrs to match admin styling
            # fld.widget.attrs.update({"class": "vFileField"})


class ExternalFilesForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.label_suffix = ""
        fld = self.fields.get("support_file")
        if fld is not None:
            fld.label = "Bifogad fil"

        # self.label_suffix = ""
        # If this form is bound to an existing instance with a file, disable the field
        if self.instance and self.instance.pk and self.instance.support_file:
            self.fields["support_file"].disabled = False
            self.fields["support_file"].help_text = "Fil redan uppladdad"
        self.fields["support_file"].label = "Bifogad fil"

    class Meta:
        model = ConceptExternalFiles
        exclude = ()

    begrepp = forms.CharField(widget=forms.HiddenInput())
    kommentar = forms.CharField(widget=forms.HiddenInput())
    support_file = forms.FileField()


class ExcelImportForm(forms.Form):
    excel_file = forms.FileField()


class ColumnMappingForm(forms.Form):

    excel_file = forms.CharField(widget=forms.HiddenInput())
    dictionary = forms.ChoiceField(
        label=_("Välja ordbok"), required=False
    )  # Add dictionary field here

    def __init__(self, *args, **kwargs):
        columns = kwargs.pop("columns")
        model_fields = kwargs.pop("model_fields")
        available_dictionaries = kwargs.pop(
            "available_dictionaries", []
        )  # Pass available dictionaries
        super().__init__(*args, **kwargs)

        # Dynamically create form fields for mapping columns to model fields

        for col in columns:
            self.fields[col] = forms.ChoiceField(
                choices=[(None, "---")] + [(field, field) for field in model_fields],
                required=False,
                label=f"{col}",
            )

        # If dictionaries are available, allow the user to choose one
        if available_dictionaries:
            field = cast(forms.ChoiceField, self.fields["dictionary"])
            field.choices = [(None, "---")] + [
                (dict_id, dict_name) for dict_id, dict_name in available_dictionaries
            ]


class AttributeValueInlineForm(forms.ModelForm):
    class Meta:
        model = AttributeValue
        fields = [
            "value_string",
            "value_text",
            "value_integer",
            "value_decimal",
            "value_boolean",
            "value_url",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.attribute_id:
            attribute = self.instance.attribute
            data_type = attribute.data_type
            display_name = attribute.display_name
            concept: Optional[Any] = getattr(self.instance, "term", None)

            field_map = {
                "string": "value_string",
                "text": "value_text",
                "integer": "value_integer",
                "decimal": "value_decimal",
                "boolean": "value_boolean",
                "url": "value_url",
            }

            for field_name, field in self.fields.items():
                if field_name != field_map.get(data_type, ""):
                    self.fields[field_name].widget = HiddenInput()
                else:
                    self.fields[field_name].label = ""
                    requester = concept.task_requester.first() if concept else None
                    if (
                        requester
                        and display_name == _("Begrepp kontext")
                        and concept is not None
                    ):
                        uploaded_files = concept.conceptexternalfiles_set.all()

                        file_list = []
                        for f in uploaded_files:
                            filename = os.path.basename(f.support_file.name)
                            stem, ext = os.path.splitext(filename)
                            url = f.support_file.url
                            max_chars = 15
                            if len(stem) > max_chars:
                                stem = stem[:max_chars] + "…"

                            file_list.append([url, stem, ext])

                        file_links = [
                            format_html(
                                '<li><a href="{url}" target="_blank" rel="noopener">{name}</a></li>',
                                url=url,
                                name=f"{stem}{ext}",
                            )
                            for f in uploaded_files
                            if f.support_file
                        ]

                        log.debug("Requester present, adding extra field")
                        req = requester
                        help_chunks = [
                            '<span class="requester-label">{label}</span>',
                            '<div class="requester-name">{name}</div>',
                            '<a class="requester-email" href="mailto:{email}">{email}</a>',
                        ]

                        if file_links:
                            help_chunks.append(
                                '<div class="requester-files">'
                                '<span class="requester-label">{files_label}</span>'
                                '<ol class="requester-file-list">{links}</ol>'
                                "</div>".format(
                                    files_label=_("Bifogade filer"),
                                    links="".join(file_links),
                                )
                            )

                        self.fields[field_name].help_text = mark_safe(
                            format_html(
                                "".join(help_chunks),
                                label=_("Beställare"),
                                name=req.name or _("Okänd namn"),
                                email=req.email,
                                files=file_links,
                            )
                        )


class ConceptForm(GroupFilteredModelForm):

    class Meta:
        model = Concept
        exclude = ()
        fields = "__all__"
        help_texts = {
            "term": _("Rullistan visar termer redan i DB"),
            "definition": _("Visas som HTML på framsidan"),
            "källa": _("Rullistan visar termer redan i DB"),
        }

    use_required_attribute = False

    def __init__(self, *args, user=None, **kwargs):

        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["status"] = forms.ChoiceField(
            choices=ConfigurationOptions.get_status_choices(), required=True
        )
        if user and not user.is_superuser and "dictionaries" in self.fields:
            cast(
                forms.ModelMultipleChoiceField, self.fields["dictionaries"]
            ).queryset = Dictionary.objects.filter(
                groups__in=user.groups.all()
            ).distinct()

        if "dictionaries" in self.fields:
            self.fields["dictionaries"].required = True

            if user and not user.is_superuser:
                cast(
                    forms.ModelMultipleChoiceField, self.fields["dictionaries"]
                ).queryset = Dictionary.objects.filter(
                    groups__in=user.groups.all()
                ).distinct()

    def clean(self):

        cleaned_definition = self.cleaned_data.get("definition") or ""
        cleaned_data: Dict[str, Any] = super().clean() or {}

        if any((c in ["{", "}", "½"]) for c in cleaned_definition):
            raise forms.ValidationError(
                {"definition": _("Får inte ha { } eller ½ i texten")}
            )

        if (not hasattr(self, "user")) or (self.user is None):
            raise Exception(
                _(
                    "Formuläret sakner 'användare'. Var säkert att den skickas från admin."
                )
            )

        selected_dictionaries = cleaned_data.get("dictionaries")
        if not selected_dictionaries:
            # field-specific error mapping if you prefer it here
            raise forms.ValidationError(
                {"dictionaries": _("Välj minst en ordlista innan du sparar.")}
            )

        user = self.user
        if user and not user.is_superuser:
            selected_dictionaries = cleaned_data.get("dictionaries")
            if selected_dictionaries is None:
                return cleaned_data
            allowed = Dictionary.objects.filter(groups__in=user.groups.all()).distinct()

            unauthorized = selected_dictionaries.exclude(
                pk__in=allowed.values_list("pk", flat=True)
            )
            if unauthorized.exists():
                raise ValidationError(
                    _(
                        "Du har inte behörighet att koppla detta begrepp till en eller flera av de valda ordlistorna."
                    )
                )

        return cleaned_data


class ConceptExternalFilesForm(forms.ModelForm):

    support_file = forms.FileField(label=_("Bifogad fil"))

    class Meta:
        model = ConceptExternalFiles
        exclude = ()
        help_texts = {
            "kommentar": _("Kan länkas till en kommentar också, men behövs inte")
        }


class ChooseExportAttributes(forms.Form):

    attribut = forms.MultipleChoiceField(required=False)
    term = forms.CharField(widget=forms.HiddenInput(), required=False)


class StatisticsFilterForm(forms.Form):

    INTERVAL_CHOICES = [("day", "Dag"), ("week", "Vecka"), ("month", "Månad")]

    from_date = forms.DateField(label="Från", widget=CustomDateInput(format="%Y-%m-%d"))
    to_date = forms.DateField(label="Till", widget=CustomDateInput(format="%Y-%m-%d"))
    interval = forms.ChoiceField(choices=INTERVAL_CHOICES, required=False, widget=HiddenInput)

    def clean(self):
        cleaned_data = super().clean()
        from_date, to_date = cleaned_data.get("from_date"), cleaned_data.get("to_date")
        if from_date and to_date and from_date > to_date:
            raise ValidationError("Från-datum måste vara före till-datum.")
        return cleaned_data
