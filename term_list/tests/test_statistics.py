"""Usage statistics shown to editors in the admin."""

from datetime import date, datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory
from django.urls import reverse

from term_list.functions import (
    besökare_hash,
    besökare_ip_adress,
    besökare_land,
    most_viewed_concepts,
    most_viewed_dictionaries,
    mäta_unikt_besök,
    unique_visits_over_time,
    views_over_time,
    views_per_country,
)
from term_list.models import DailySalt, MetadataSearchTrack, UniqueVisit
from term_list.tests.factories import ConceptFactory, DictionaryFactory

pytestmark = pytest.mark.django_db

AJAX_HEADERS = {"X-Custom-Requested-With": "XMLHttpRequest"}


def log_view(concept_id, timestamp, visitor_hash=None, country=None):
    track = MetadataSearchTrack.objects.create(
        sök_term=str(concept_id), visitor_hash=visitor_hash, country=country
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


class TestVisitorIp:
    def test_prefers_first_x_forwarded_for_address(self):
        """The visitor IP comes from the first X-Forwarded-For address when present, not REMOTE_ADDR."""
        request = visitor_request(ip="10.0.0.1")
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.9, 10.0.0.1"

        assert besökare_ip_adress(request) == "203.0.113.9"


class TestIpMigration:
    migrate_from = [("term_list", "0008_metadatasearchtrack_country")]
    migrate_to = [("term_list", "0009_fill_visitor_hash_and_country_from_ip")]
    latest = [("term_list", "0010_remove_ip_adress")]

    @pytest.mark.django_db(transaction=True)
    def test_fills_country_and_daily_hash_from_ip(self):
        """Old clicks get a country and a hash that matches within a day and differs across days."""
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_track = executor.loader.project_state(self.migrate_from).apps.get_model(
            "term_list", "MetadataSearchTrack"
        )
        for day in (1, 1, 2):
            track = old_track.objects.create(sök_term="1", ip_adress="195.67.0.1")
            old_track.objects.filter(pk=track.pk).update(sök_timestamp=datetime(2026, 10, day, 12, 0))

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        tracks = list(
            executor.loader.project_state(self.migrate_to).apps.get_model("term_list", "MetadataSearchTrack")
            .objects.order_by("sök_timestamp", "pk")
        )
        MigrationExecutor(connection).migrate(self.latest)

        assert [track.country for track in tracks] == ["SE", "SE", "SE"]
        assert tracks[0].visitor_hash == tracks[1].visitor_hash != tracks[2].visitor_hash


class TestVisitorCountry:
    def test_known_ip_gives_its_country(self):
        """An IP in a Swedish range is looked up as SE."""
        assert besökare_land(visitor_request(ip="195.67.0.1")) == "SE"

    def test_local_ip_gives_no_country(self):
        """A local address has no country."""
        assert besökare_land(visitor_request(ip="127.0.0.1")) is None

    def test_invalid_ip_gives_no_country(self):
        """A malformed forwarded address doesn't crash the lookup."""
        request = visitor_request()
        request.META["HTTP_X_FORWARDED_FOR"] = "not-an-ip"

        assert besökare_land(request) is None

    def test_views_per_country_most_first(self, concept):
        """Views are counted per country, with unknown countries as None."""
        log_view(concept.id, datetime(2026, 10, 1, 9, 0), country="SE")
        log_view(concept.id, datetime(2026, 10, 1, 10, 0), country="SE")
        log_view(concept.id, datetime(2026, 10, 1, 11, 0), country="NO")
        log_view(concept.id, datetime(2026, 10, 1, 12, 0))

        result = views_per_country(date(2026, 10, 1), date(2026, 10, 1))

        assert result == [("SE", 2), ("NO", 1), (None, 1)]


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


class TestRecordUniqueVisit:
    def test_first_request_today_records_one_visit(self):
        """A visitor's first request today stores today's date and their hash."""
        request = visitor_request()

        mäta_unikt_besök(request)

        visit = UniqueVisit.objects.get()
        assert (visit.date, visit.visitor_hash) == (date.today(), besökare_hash(request))

    def test_same_visitor_same_day_counts_once(self):
        """Repeated requests from one visitor on the same day give a single row."""
        mäta_unikt_besök(visitor_request())
        mäta_unikt_besök(visitor_request())

        assert UniqueVisit.objects.count() == 1

    def test_same_visitor_next_day_counts_again(self):
        """The same visitor on a new day is a new unique visit."""
        mäta_unikt_besök(visitor_request())
        yesterday = date.today() - timedelta(days=1)
        UniqueVisit.objects.update(date=yesterday)
        DailySalt.objects.update(date=yesterday)

        mäta_unikt_besök(visitor_request())

        assert sorted(UniqueVisit.objects.values_list("date", flat=True)) == [yesterday, date.today()]

    def test_different_visitors_same_day_count_separately(self):
        """Two visitors on the same day give two rows."""
        mäta_unikt_besök(visitor_request())
        mäta_unikt_besök(visitor_request(ip="192.0.2.2"))

        assert UniqueVisit.objects.count() == 2

    @pytest.mark.parametrize("user_agent", ["Googlebot/2.1", "YandexBot", "SomeCrawler", "Baiduspider", ""])
    def test_bots_and_missing_user_agent_are_skipped(self, user_agent):
        """Requests from bots, crawlers, spiders or without a user agent aren't counted."""
        mäta_unikt_besök(visitor_request(user_agent=user_agent))

        assert not UniqueVisit.objects.exists()


class TestPageLoadRecordsVisit:
    def test_loading_the_main_page_records_a_visit(self, client):
        """A normal load of the main page counts as a unique visit."""
        client.get("/", HTTP_USER_AGENT="Mozilla/5.0 Firefox")

        assert UniqueVisit.objects.count() == 1

    def test_ajax_search_records_no_visit(self, client):
        """A search from the page doesn't count as a visit."""
        client.get("/", {"q": "vård"}, headers=AJAX_HEADERS, HTTP_USER_AGENT="Mozilla/5.0 Firefox")

        assert not UniqueVisit.objects.exists()


class TestUniqueVisitsOverTime:
    def test_days_without_visits_are_zero(self):
        """Every day in the range is returned, with 0 for days without visits; visits outside don't count."""
        UniqueVisit.objects.create(date=date(2026, 10, 1), visitor_hash="a")
        UniqueVisit.objects.create(date=date(2026, 10, 1), visitor_hash="b")
        UniqueVisit.objects.create(date=date(2026, 10, 3), visitor_hash="a")
        UniqueVisit.objects.create(date=date(2026, 10, 4), visitor_hash="a")

        result = unique_visits_over_time(date(2026, 10, 1), date(2026, 10, 3), "day")

        assert result == [(date(2026, 10, 1), 2), (date(2026, 10, 2), 0), (date(2026, 10, 3), 1)]

    def test_weeks_start_on_monday(self):
        """Weekly periods start on Monday and sum the visits in the week."""
        UniqueVisit.objects.create(date=date(2026, 10, 1), visitor_hash="a")
        UniqueVisit.objects.create(date=date(2026, 10, 2), visitor_hash="a")
        UniqueVisit.objects.create(date=date(2026, 10, 5), visitor_hash="a")

        result = unique_visits_over_time(date(2026, 10, 1), date(2026, 10, 7), "week")

        assert result == [(date(2026, 9, 28), 2), (date(2026, 10, 5), 1)]

    def test_months_start_on_the_first(self):
        """Monthly periods start on the first of the month, across a year boundary."""
        UniqueVisit.objects.create(date=date(2026, 12, 15), visitor_hash="a")
        UniqueVisit.objects.create(date=date(2027, 1, 20), visitor_hash="a")

        result = unique_visits_over_time(date(2026, 12, 10), date(2027, 1, 31), "month")

        assert result == [(date(2026, 12, 1), 1), (date(2027, 1, 1), 1)]


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
        """The statistics page embeds the views and unique visits over time for the charts."""
        log_view(concept.id, datetime(2026, 10, 1, 12, 0))
        UniqueVisit.objects.create(date=date(2026, 10, 1), visitor_hash="a")

        response = admin_user_authenticated_client.get(
            self.url, {"from_date": "2026-10-01", "to_date": "2026-10-02"}
        )

        assert response.context["chart_data"]["views"] == [1, 0]
        assert response.context["chart_data"]["unique_visits"] == [1, 0]
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
