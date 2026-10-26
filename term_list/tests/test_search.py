"""A visitor searching for a term on the front page.

`main_search_view` only returns real results on an AJAX request (it checks
a custom `X-Custom-Requested-With` header) — a plain GET renders an empty
results page. Tests that exercise search results go through the AJAX path.
"""

import pytest

from term_list.models import SearchTrack
from term_list.tests.factories import (
    AttributeFactory,
    AttributeValueFactory,
    ConceptFactory,
    DictionaryFactory,
    SynonymFactory,
)
from term_list.views import search_concepts_with_attributes

pytestmark = pytest.mark.django_db

AJAX_HEADERS = {"X-Custom-Requested-With": "XMLHttpRequest"}


def search(client, q, dictionary=None):
    params = {"q": q}
    if dictionary:
        params["dictionary"] = dictionary
    response = client.get("/", params, headers=AJAX_HEADERS)
    return response.json()


class TestSearchMatching:
    def test_finds_concept_by_term(self, client, dictionary):
        """Searching for a concept's term text finds that concept."""
        concept = ConceptFactory(term="Diagnos")
        concept.dictionaries.add(dictionary)
        html = search(client, "Diagnos")
        assert "Diagnos" in html

    def test_finds_concept_by_definition(self, client, dictionary):
        """Searching for text that only appears in the definition still finds the concept."""
        concept = ConceptFactory(term="Xyz", definition="Ovanlig sjukdomsbild")
        concept.dictionaries.add(dictionary)
        html = search(client, "Ovanlig sjukdomsbild")
        assert "Xyz" in html

    def test_finds_concept_by_synonym(self, client, dictionary):
        """Searching for a synonym's text finds the concept it belongs to."""
        concept = ConceptFactory(term="Huvudterm")
        concept.dictionaries.add(dictionary)
        SynonymFactory(concept=concept, synonym="Smeknamn")
        html = search(client, "Smeknamn")
        assert "Huvudterm" in html

    @pytest.mark.xfail(
        reason=(
            "BUG (term_list/views.py::search_concepts_with_attributes): "
            "`matched_concepts` correctly includes concepts found only via an "
            "AttributeValue match, but the function then reassigns `queryset` "
            "from the original term/definition/synonym-only queryset instead "
            "of from `matched_concepts`, so attribute-only matches never make "
            "it into the returned results. TODO: fix the bug, then remove this "
            "xfail marker."
        ),
        strict=True,
    )
    def test_finds_concept_by_custom_attribute_value(self, client, dictionary):
        """Searching for text stored in a custom Attribute's value finds the concept."""
        concept = ConceptFactory(term="Attributterm")
        concept.dictionaries.add(dictionary)
        attribute = AttributeFactory(data_type="string")
        AttributeValueFactory(
            term=concept, attribute=attribute, value_string="ovanlig sökbar text"
        )
        html = search(client, "ovanlig sökbar text")
        assert "Attributterm" in html

    def test_excluded_status_never_appears_in_results(self, dictionary):
        """A concept whose status is configured as excluded is never returned, even on an exact term match.

        Asserts against `search_concepts_with_attributes()` directly rather
        than the rendered "no results" HTML: that template echoes the search
        term back into a `no_search_result(...)` script call, so a plain
        "term not in html" check would pass even when zero-results was a
        coincidence, not proof the exclusion actually filtered anything.
        """
        concept = ConceptFactory(term="Dold", status="Avställd")
        concept.dictionaries.add(dictionary)
        results = search_concepts_with_attributes("Dold")
        assert all(r["id"] != concept.id for r in results)

    def test_search_by_single_uppercase_letter_filters_by_first_letter(
        self, client, dictionary
    ):
        """A single uppercase letter search matches concepts whose term starts with that letter."""
        matching = ConceptFactory(term="Ärende")
        matching.dictionaries.add(dictionary)
        non_matching = ConceptFactory(term="Övrigt")
        non_matching.dictionaries.add(dictionary)
        html = search(client, "Ä")
        assert "Ärende" in html
        assert "Övrigt" not in html


class TestSearchDictionaryFiltering:
    def test_filtering_by_dictionary_excludes_concepts_in_other_dictionaries(
        self, client, dictionary
    ):
        """Filtering search to one dictionary hides concepts that only belong to a different dictionary."""
        other_dictionary = DictionaryFactory()
        in_chosen = ConceptFactory(term="Inom")
        in_chosen.dictionaries.add(dictionary)
        in_other = ConceptFactory(term="Utanför")
        in_other.dictionaries.add(other_dictionary)

        html = search(client, "n", dictionary=dictionary.dictionary_name)

        assert "Inom" in html
        assert "Utanför" not in html

    def test_no_dictionary_filter_searches_across_all_dictionaries(
        self, client, dictionary
    ):
        """Searching without a dictionary filter ("show all") returns matches from every dictionary."""
        other_dictionary = DictionaryFactory()
        first = ConceptFactory(term="Alfa")
        first.dictionaries.add(dictionary)
        second = ConceptFactory(term="Alfabet")
        second.dictionaries.add(other_dictionary)

        html = search(client, "Alfa")

        assert "Alfa" in html
        assert "Alfabet" in html

    def test_no_dictionary_filter_shows_alla_ordlistor_heading(self, client, dictionary):
        """Searching without a dictionary filter shows the "all dictionaries" heading, not a crash."""
        concept = ConceptFactory(term="Rubrik")
        concept.dictionaries.add(dictionary)
        html = search(client, "Rubrik")
        assert "Alla ordlistor" in html

    def test_no_dictionary_filter_shows_each_results_own_dictionary_name(
        self, client, dictionary
    ):
        """Searching "show all" includes each result's own dictionary name, so the extra dictionary column has data."""
        concept = ConceptFactory(term="Kolumn")
        concept.dictionaries.add(dictionary)
        html = search(client, "Kolumn")
        assert dictionary.dictionary_name in html

    def test_filtering_by_dictionary_shows_its_name_in_the_heading(self, client, dictionary):
        """Filtering search to one dictionary shows that dictionary's name in the results heading."""
        concept = ConceptFactory(term="Filtrerad")
        concept.dictionaries.add(dictionary)
        html = search(client, "Filtrerad", dictionary=dictionary.dictionary_name)
        assert f"Visar resultat för {dictionary.dictionary_name}" in html


class TestSearchHighlightingDictionaryScoping:
    def test_show_all_does_not_cross_highlight_terms_from_other_dictionaries(
        self, client, dictionary
    ):
        """In "show all" mode, a term from a different dictionary must not be turned into a tooltip inside a definition."""
        other_dictionary = DictionaryFactory()
        referenced = ConceptFactory(term="Alfa", definition="Första bokstaven")
        referenced.dictionaries.add(dictionary)
        referencing = ConceptFactory(
            term="Beta", definition="Kommer efter Alfa i alfabetet"
        )
        referencing.dictionaries.add(other_dictionary)

        html = search(client, "Beta")

        assert 'aria-describedby="def-Alfa"' not in html

    def test_show_all_still_cross_highlights_terms_within_the_same_dictionary(
        self, client, dictionary
    ):
        """In "show all" mode, a term is still turned into a tooltip when it shares a dictionary with the referencing definition."""
        referenced = ConceptFactory(term="Alfa", definition="Första bokstaven")
        referenced.dictionaries.add(dictionary)
        referencing = ConceptFactory(
            term="Beta", definition="Kommer efter Alfa i alfabetet"
        )
        referencing.dictionaries.add(dictionary)

        html = search(client, "Beta")

        assert 'aria-describedby="def-Alfa"' in html

    def test_show_all_handles_concepts_without_any_dictionary_safely(
        self, client, dictionary
    ):
        """A concept with no dictionary at all must not corrupt its own or other definitions.

        Regression test: building a tooltip substitution from an empty term
        set produces a regex with an empty alternation, which matches a
        zero-width string everywhere and mangles the text it is applied to.
        """
        orphan = ConceptFactory(
            term="Särart", definition="Utan koppling till någon ordlista"
        )
        normal = ConceptFactory(term="Särdrag", definition="Har en ordlista")
        normal.dictionaries.add(dictionary)

        html = search(client, "Sär")

        assert "Utan koppling till någon ordlista" in html
        assert "Har en ordlista" in html


class TestSearchTracking:
    def test_search_records_a_search_track_entry(self, client, dictionary):
        """Performing a search creates a SearchTrack row recording what was searched for."""
        concept = ConceptFactory(term="Spårat")
        concept.dictionaries.add(dictionary)
        search(client, "Spårat")
        assert SearchTrack.objects.filter(sök_term="Spårat").exists()
