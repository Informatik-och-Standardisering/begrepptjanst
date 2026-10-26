import functools
import hashlib
import re
import secrets
from collections import Counter, OrderedDict
from datetime import date, timedelta
from pathlib import Path

import maxminddb
from django.db.models import Count, F
from django.db.models.functions import TruncDate, TruncDay, TruncMonth, TruncWeek

from .models import Concept, DailySalt, Dictionary, MetadataSearchTrack, SearchTrack


def besökare_ip_adress(request):

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def mäta_sök_träff(sök_term, sök_data, request):

    ny_sök = SearchTrack()
    ny_sök.sök_term = sök_term
    ny_sök.records_returned = str([i.get('begrepp_id') for i in sök_data])[1:-1]
    ny_sök.ip_adress = besökare_ip_adress(request)
    ny_sök.save()
    return None

def besökare_hash(request):
    """Return a hash that identifies the visitor for today only."""

    today = date.today()
    daily_salt, created = DailySalt.objects.get_or_create(
        date=today, defaults={'salt': secrets.token_hex(32)}
    )
    if created:
        DailySalt.objects.exclude(date=today).delete()
    visitor = besökare_ip_adress(request) + request.META.get('HTTP_USER_AGENT', '') + daily_salt.salt
    return hashlib.sha256(visitor.encode()).hexdigest()

@functools.cache
def _country_reader():
    return maxminddb.open_database(Path(__file__).resolve().parent.parent / 'geoip' / 'dbip-country-lite.mmdb')

def besökare_land(request):
    """Return the visitor's two-letter country code, or None when it's unknown."""

    try:
        record = _country_reader().get(besökare_ip_adress(request))
    except ValueError:
        return None
    return record['country']['iso_code'] if record else None

def mäta_förklaring_träff(sök_term, request):

    ny_sök = MetadataSearchTrack()
    ny_sök.sök_term = sök_term
    ny_sök.ip_adress = besökare_ip_adress(request)
    ny_sök.visitor_hash = besökare_hash(request)
    ny_sök.country = besökare_land(request)
    ny_sök.save()

def most_viewed_concepts(from_date, to_date, limit=50):
    """Return the most viewed concepts between two dates (inclusive) with view counts."""

    rows = (
        MetadataSearchTrack.objects.filter(sök_timestamp__date__range=(from_date, to_date))
        .values('sök_term')
        .annotate(views=Count('id'))
        .order_by('-views', 'sök_term')[:limit]
    )
    concept_ids = [row['sök_term'] for row in rows if row['sök_term'].isdecimal()]
    concepts = {str(pk): concept for pk, concept in Concept.objects.in_bulk(concept_ids).items()}
    return [
        {'concept': concepts.get(row['sök_term']), 'concept_id': row['sök_term'], 'views': row['views']}
        for row in rows
    ]

def most_viewed_dictionaries(from_date, to_date):
    """Return dictionaries ordered by views of their concepts between two dates (inclusive)."""

    view_counts = dict(
        MetadataSearchTrack.objects.filter(sök_timestamp__date__range=(from_date, to_date))
        .values_list('sök_term')
        .annotate(views=Count('id'))
    )
    concept_ids = [concept_id for concept_id in view_counts if concept_id.isdecimal()]
    memberships = Concept.dictionaries.through.objects.filter(concept_id__in=concept_ids)
    totals = Counter()
    for concept_id, dictionary_id in memberships.values_list('concept_id', 'dictionary_id'):
        totals[dictionary_id] += view_counts[str(concept_id)]
    dictionaries = Dictionary.objects.in_bulk(list(totals))
    return [{'dictionary': dictionaries[pk], 'views': views} for pk, views in totals.most_common()]

def views_per_country(from_date, to_date):
    """Return (country code or None, views) between two dates (inclusive), most views first."""

    return list(
        MetadataSearchTrack.objects.filter(sök_timestamp__date__range=(from_date, to_date))
        .values_list('country')
        .annotate(views=Count('id'))
        .order_by('-views', F('country').asc(nulls_last=True))
    )

TRUNCATE = {'day': TruncDay, 'week': TruncWeek, 'month': TruncMonth}

def interval_choices(from_date, to_date):
    """Return the default interval and the intervals allowed for the range length."""

    days = (to_date - from_date).days + 1
    if days <= 90:
        return 'day', ['day', 'week']
    if days <= 730:
        return 'week', ['day', 'week', 'month']
    return 'month', ['week', 'month']

def _period_start(day, interval):
    if interval == 'month':
        return day.replace(day=1)
    if interval == 'week':
        return day - timedelta(days=day.weekday())
    return day

def _period_starts(from_date, to_date, interval):
    start = _period_start(from_date, interval)
    while start <= to_date:
        yield start
        if interval == 'month':
            start = (start + timedelta(days=32)).replace(day=1)
        else:
            start += timedelta(days=7 if interval == 'week' else 1)

def views_over_time(from_date, to_date, interval):
    """Return (period start, views) for every period in the range, including periods without views."""

    counts = dict(
        MetadataSearchTrack.objects.filter(sök_timestamp__date__range=(from_date, to_date))
        .annotate(period=TRUNCATE[interval](TruncDate('sök_timestamp')))
        .values_list('period')
        .annotate(views=Count('id'))
    )
    return [(start, counts.get(start, 0)) for start in _period_starts(from_date, to_date, interval)]

def visitors_over_time(from_date, to_date, interval):
    """Return (period start, average unique visitors per day) for every period in the range."""

    daily_visitors = dict(
        MetadataSearchTrack.objects.filter(sök_timestamp__date__range=(from_date, to_date))
        .annotate(day=TruncDate('sök_timestamp'))
        .values_list('day')
        .annotate(visitors=Count('visitor_hash', distinct=True))
    )
    totals, days = Counter(), Counter()
    day = from_date
    while day <= to_date:
        start = _period_start(day, interval)
        totals[start] += daily_visitors.get(day, 0)
        days[start] += 1
        day += timedelta(days=1)
    return [(start, round(totals[start] / days[start], 1)) for start in days]

def sort_concept_keys(begrepp_dict):

    desired_dict_order = ['status',
                          'term',
                          'synonym',
                          'definition',
                          'källa',
                          'anmärkning',
                          'term på annat språk',
                          'annan referens',
                          'kod',
                          'term id']

    return OrderedDict([(v, begrepp_dict[v]) for v in desired_dict_order])

def replace_nbs_with_normal_space(string_with_bad_values):

    '''
    Replace a nonbreaking space (nbs) (Latin) with a normal space. The nbs can cause problems
    in html rendering.

    '''
    return re.sub('\\xa0', ' ', string_with_bad_values, flags=re.IGNORECASE|re.UNICODE)


class Xlator(dict):
    """ All-in-one multiple-string-substitution class
        with flexible word boundaries for suffixes like plurals."""

    def escape_keys(self):
        return [re.escape(i) for i in self.keys()]

    def _make_regex(self):
        # Define common suffixes for pluralization or word forms
        suffixes = r"(en|ens|er|ar|et|s)?\b"

        # Escape the keys and join them with word boundaries
        escaped_keys = self.escape_keys()
        joined_keys = r'\b(' + r'|'.join(escaped_keys) + r')' + suffixes

        # Compile the regular expression with the flexible word boundary
        compiled_re = re.compile(joined_keys, re.IGNORECASE)

        return compiled_re

    def __call__(self, match):
        """ Handler invoked for each regex match """
        base_word = match.group(1)  # This captures the base word before the suffix
        suffix = match.group(2) or ""  # This captures the suffix (if any)
        tooltip = self.get(base_word, base_word)  # Lookup the base word in the dictionary

        # Return the tooltip with the original suffix added back
        return tooltip.strip() + suffix


    def xlat(self, text):
        """ Translate text, returns the modified text. """
        return self._make_regex().sub(self, text)

HTML_TAGS = ['a', 'abbr', 'acronym', 'address', 'applet', 'area', 'article', 'aside',
'audio', 'b', 'base', 'basefont', 'bb', 'bdo', 'big', 'blockquote', 'body', 'br /', 'br',
'button', 'canvas', 'caption', 'center', 'cite', 'code', 'col', 'colgroup', 'command',
'datagrid', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog', 'dir', 'div', 'dl',
'dt', 'em', 'embed', 'eventsource', 'fieldset', 'figcaption', 'figure', 'font', 'footer',
'form', 'frame', 'frameset', 'h1 to h6', 'head', 'header', 'hgroup', 'hr /', 'html',
'i', 'iframe', 'img', 'input', 'ins', 'isindex', 'kbd', 'keygen', 'label', 'legend',
'li', 'link', 'map', 'mark', 'menu', 'meta', 'meter', 'nav', 'noframes', 'noscript',
'object', 'ol', 'optgroup', 'option', 'output', 'p', 'param', 'pre', 'progress', 'q',
'rp', 'rt', 'ruby', 's', 'samp', 'script', 'section', 'select', 'small', 'source',
'span', 'strike', 'strong', 'style', 'sub', 'sup', 'table', 'tbody', 'td', 'textarea',
'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'track', 'tt', 'u', 'ul', 'var',
'video', 'wbr']
