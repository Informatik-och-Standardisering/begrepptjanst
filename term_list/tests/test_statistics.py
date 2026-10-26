"""Usage statistics shown to editors in the admin."""

from datetime import date, datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse

from term_list.functions import (
    besökare_hash,
    most_viewed_concepts,
    most_viewed_dictionaries,
    views_over_time,
    visitors_over_time,
)
from term_list.models import DailySalt, MetadataSearchTrack
from term_list.tests.factories import ConceptFactory, DictionaryFactory

pytestmark = pytest.mark.django_db


def log_view(concept_id, timestamp, visitor_hash=None):
    track = MetadataSearchTrack.objects.create(
        sök_term=str(concept_id), ip_adress="127.0.0.1", visitor_hash=visitor_hash
    )
    MetadataSearchTrack.objects.filter(pk=track.pk).update(sök_timestamp=timestamp)


def visitor_request(ip="192.0.2.1", user_agent="Firefox"):
    return RequestFactory().get("/", REMOTE_ADDR=ip, HTTP_USER_AGENT=user_agent)


class TestVisitorHash:
    def test_same_visitor_gets_same_hash_within_a_day(self):
        """Two requests from the same IP and browser on the same day give the same hash."""
        assert besökare_hash(visitor_request()) == besökare_hash(visitor_request())

    def test_different_visitors_get_different_hashes(self):
        """A different IP or browser gives a different hash."""
        hash_ = besökare_hash(visitor_request())

        assert besökare_hash(visitor_request(ip="192.0.2.2")) != hash_
        assert besökare_hash(visitor_request(user_agent="Chrome")) != hash_

    def test_new_day_gives_new_hash_and_deletes_old_salt(self):
        """On a new day the salt is replaced, so the same visitor gets a new hash."""
        yesterdays_hash = besökare_hash(visitor_request())
        DailySalt.objects.update(date=date.today() - timedelta(days=1))

        todays_hash = besökare_hash(visitor_request())

        assert todays_hash != yesterdays_hash
        assert list(DailySalt.objects.values_list("date", flat=True)) == [date.today()]

    def test_viewing_a_term_stores_the_visitor_hash(self, client, concept):
        """A logged term view carries a visitor hash and not the salt."""
        client.get("/begrepp-forklaring/", {"q": concept.id})

        track = MetadataSearchTrack.objects.get(sök_term=str(concept.id))
        assert len(track.visitor_hash) == 64


class TestMostViewedConcepts:
    def test_counts_views_within_range_most_viewed_first(self, concept):
        """Views on both end dates count, views outside the range don't."""
        other = ConceptFactory()
        log_view(concept.id, datetime(2026, 10, 1, 0, 0))
        log_view(concept.id, datetime(2026, 10, 31, 23, 59))
        log_view(other.id, datetime(2026, 10, 15, 12, 0))
        log_view(other.id, datetime(2026, 11, 1, 0, 0))

        result = most_viewed_concepts(date(2026, 10, 1), date(2026, 10, 31))

        assert [(row["concept"], row["views"]) for row in result] == [(concept, 2), (other, 1)]

    def test_unknown_concept_id_has_no_concept(self):
        """A logged id without a matching concept is returned with concept None."""
        log_view("999999", datetime(2026, 10, 1, 12, 0))

        result = most_viewed_concepts(date(2026, 10, 1), date(2026, 10, 1))

        assert result == [{"concept": None, "concept_id": "999999", "views": 1}]


class TestMostViewedDictionaries:
    def test_concept_in_two_dictionaries_counts_for_both(self, concept, dictionary):
        """Views of a concept count for every dictionary it belongs to."""
        other_dictionary = DictionaryFactory()
        concept.dictionaries.add(other_dictionary)
        other_concept = ConceptFactory()
        other_concept.dictionaries.add(other_dictionary)
        log_view(concept.id, datetime(2026, 10, 1, 12, 0))
        log_view(other_concept.id, datetime(2026, 10, 1, 12, 0))

        result = most_viewed_dictionaries(date(2026, 10, 1), date(2026, 10, 1))

        assert [(row["dictionary"], row["views"]) for row in result] == [
            (other_dictionary, 2),
            (dictionary, 1),
        ]


class TestViewsOverTime:
    def test_days_without_views_are_zero(self, concept):
        """Every day in the range is returned, with 0 for days without views."""
        log_view(concept.id, datetime(2026, 10, 1, 12, 0))
        log_view(concept.id, datetime(2026, 10, 3, 12, 0))

        result = views_over_time(date(2026, 10, 1), date(2026, 10, 3), "day")

        assert result == [(date(2026, 10, 1), 1), (date(2026, 10, 2), 0), (date(2026, 10, 3), 1)]

    def test_weeks_start_on_monday(self, concept):
        """Weekly periods start on Monday and count all views in the week, also when the range starts mid-week."""
        log_view(concept.id, datetime(2026, 10, 1, 12, 0))
        log_view(concept.id, datetime(2026, 10, 2, 9, 30))
        log_view(concept.id, datetime(2026, 10, 5, 12, 0))

        result = views_over_time(date(2026, 10, 1), date(2026, 10, 7), "week")

        assert result == [(date(2026, 9, 28), 2), (date(2026, 10, 5), 1)]

    def test_months_start_on_the_first(self, concept):
        """Monthly periods start on the first of the month, across a year boundary."""
        log_view(concept.id, datetime(2026, 12, 15, 12, 0))
        log_view(concept.id, datetime(2027, 1, 20, 12, 0))

        result = views_over_time(date(2026, 12, 10), date(2027, 1, 31), "month")

        assert result == [(date(2026, 12, 1), 1), (date(2027, 1, 1), 1)]


class TestVisitorsOverTime:
    def setup_visits(self, concept):
        log_view(concept.id, datetime(2026, 9, 28, 9, 0), visitor_hash="a")
        log_view(concept.id, datetime(2026, 9, 28, 10, 0), visitor_hash="b")
        log_view(concept.id, datetime(2026, 9, 29, 9, 0), visitor_hash="a")
        log_view(concept.id, datetime(2026, 9, 29, 10, 0), visitor_hash="a")
        log_view(concept.id, datetime(2026, 9, 29, 11, 0))

    def test_daily_unique_visitors_ignore_views_without_hash(self, concept):
        """Each hash counts once per day; views without a hash don't count as visitors."""
        self.setup_visits(concept)

        result = visitors_over_time(date(2026, 9, 28), date(2026, 9, 30), "day")

        assert result == [(date(2026, 9, 28), 2), (date(2026, 9, 29), 1), (date(2026, 9, 30), 0)]

    def test_weekly_value_is_average_of_daily_unique_visitors(self, concept):
        """A week shows the daily unique visitors averaged over its days, not a summed total."""
        self.setup_visits(concept)

        result = visitors_over_time(date(2026, 9, 28), date(2026, 10, 4), "week")

        assert result == [(date(2026, 9, 28), 0.4)]


class TestStatisticsView:
    url = reverse("admin:term_list_metadatasearchtrack_statistics")

    def test_admin_sees_most_viewed_concepts(self, admin_user_authenticated_client, concept):
        """The statistics page lists concepts viewed in the chosen range."""
        log_view(concept.id, datetime(2026, 10, 1, 12, 0))

        response = admin_user_authenticated_client.get(
            self.url, {"from_date": "2026-10-01", "to_date": "2026-10-31"}
        )

        assert response.status_code == 200
        assert concept.term in response.content.decode()

    def test_admin_sees_most_viewed_dictionaries(
        self, admin_user_authenticated_client, concept, dictionary
    ):
        """The statistics page lists dictionaries of concepts viewed in the chosen range."""
        log_view(concept.id, datetime(2026, 10, 1, 12, 0))

        response = admin_user_authenticated_client.get(
            self.url, {"from_date": "2026-10-01", "to_date": "2026-10-31"}
        )

        assert dictionary.dictionary_name in response.content.decode()

    def test_page_contains_chart_data(self, admin_user_authenticated_client, concept):
        """The statistics page embeds the views over time for the chart."""
        log_view(concept.id, datetime(2026, 10, 1, 12, 0), visitor_hash="a")

        response = admin_user_authenticated_client.get(
            self.url, {"from_date": "2026-10-01", "to_date": "2026-10-02"}
        )

        assert response.context["chart_data"]["views"] == [1, 0]
        assert response.context["chart_data"]["visitors"] == [1, 0]
        assert 'id="views-chart-data"' in response.content.decode()

    def test_interval_not_allowed_for_range_falls_back_to_default(
        self, admin_user_authenticated_client
    ):
        """Asking for days over a range longer than two years shows months instead."""
        response = admin_user_authenticated_client.get(
            self.url, {"from_date": "2020-01-01", "to_date": "2026-10-26", "interval": "day"}
        )

        assert response.context["interval"] == "month"

    def test_staff_without_view_permission_is_denied(self, client):
        """Staff who can't view Sök Metadata get a 403."""
        user = User.objects.create_user(username="staff", password="password123", is_staff=True)
        client.force_login(user)

        assert client.get(self.url).status_code == 403
