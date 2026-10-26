import hashlib
import secrets
from pathlib import Path

import maxminddb
from django.db import migrations
from django.db.models import Q

GEOIP_DATABASE = Path(__file__).resolve().parent.parent.parent / 'geoip' / 'dbip-country-lite.mmdb'


def country_for(reader, ip):
    try:
        record = reader.get(ip)
    except ValueError:
        return None
    return record['country']['iso_code'] if record else None


def fill_from_ip(apps, schema_editor):
    """Fill visitor hash and country for old clicks; the per-day salts only live during this migration."""

    MetadataSearchTrack = apps.get_model('term_list', 'MetadataSearchTrack')
    tracks = list(MetadataSearchTrack.objects.filter(Q(visitor_hash__isnull=True) | Q(country__isnull=True)))
    salts = {}
    with maxminddb.open_database(GEOIP_DATABASE) as reader:
        for track in tracks:
            if track.visitor_hash is None:
                salt = salts.setdefault(track.sök_timestamp.date(), secrets.token_hex(32))
                track.visitor_hash = hashlib.sha256((track.ip_adress + salt).encode()).hexdigest()
            track.country = country_for(reader, track.ip_adress)
    MetadataSearchTrack.objects.bulk_update(tracks, ['visitor_hash', 'country'], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ('term_list', '0008_metadatasearchtrack_country'),
    ]

    operations = [
        migrations.RunPython(fill_from_ip, migrations.RunPython.noop),
    ]
