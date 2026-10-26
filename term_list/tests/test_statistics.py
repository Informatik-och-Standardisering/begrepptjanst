"""Usage statistics shown to editors in the admin."""

from datetime import date, datetime

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from term_list.functions import most_viewed_concepts
from term_list.models import MetadataSearchTrack
from term_list.tests.factories import ConceptFactory

pytestmark = pytest.mark.django_db


def log_view(concept_id, timestamp):
    track = MetadataSearchTrack.objects.create(sök_term=str(concept_id), ip_adress="127.0.0.1")
    MetadataSearchTrack.objects.filter(pk=track.pk).update(sök_timestamp=timestamp)


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

    def test_staff_without_view_permission_is_denied(self, client):
        """Staff who can't view Sök Metadata get a 403."""
        user = User.objects.create_user(username="staff", password="password123", is_staff=True)
        client.force_login(user)

        assert client.get(self.url).status_code == 403
