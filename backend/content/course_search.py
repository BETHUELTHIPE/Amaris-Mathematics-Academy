"""Bounded, public-metadata course search with deterministic relevance ordering."""

import re
import unicodedata

from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.expressions import Expression
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend, OrderingFilter

MAX_QUERY_LENGTH = 100
MAX_TERMS = 8
SEARCH_FIELDS = ("title", "short_description", "curriculum", "academic_level", "category__name")
ALIASES = {
    "maths": ("maths", "mathematics", "mathematical"),
    "math": ("math", "mathematics", "mathematical"),
    "lit": ("literacy", "lit"),
    "ncv": ("NC(V)", "NCV"),
}


def search_terms(raw):
    query = " ".join(unicodedata.normalize("NFKC", raw).split())
    if len(query) > MAX_QUERY_LENGTH:
        raise ValidationError({"search": "Keep your search under 101 characters."})
    # Grade 12 / gr.12 / grade12 are one concept, rather than unrelated tokens.
    token_query = re.sub(r"\b(?:grade|gr)\.?\s*(\d{1,2})\b", r"grade\1", query, flags=re.IGNORECASE)
    token_query = re.sub(r"\bNC\s*\(\s*V\s*\)", "ncv", token_query, flags=re.IGNORECASE)
    terms = list(dict.fromkeys(re.findall(r"[^\W_]+", token_query.casefold())))
    if len(terms) > MAX_TERMS:
        raise ValidationError({"search": "Use no more than eight search words."})
    if query and not terms:
        raise ValidationError({"search": "Enter a topic, grade, curriculum or course name."})
    return query, terms


def term_condition(term):
    condition = Q()
    if term == "matric" or (term.startswith("grade") and term[5:].isdigit()):
        number = "12" if term == "matric" else term[5:]
        phrases = (f"Grade {number}", f"Grade{number}", f"Gr {number}", f"Gr. {number}")
        # Exact level matching keeps Grade 1 from accidentally matching Grade 12.
        for phrase in phrases:
            condition |= Q(academic_level__iexact=phrase)
        for field in ("title", "short_description"):
            for phrase in phrases:
                condition |= Q(**{f"{field}__icontains": phrase + " "})
                condition |= Q(**{f"{field}__iendswith": phrase})
        if term == "matric":
            condition |= Q(title__icontains="matric") | Q(short_description__icontains="matric")
        return condition
    for variant in ALIASES.get(term, (term,)):
        for field in SEARCH_FIELDS:
            condition |= Q(**{f"{field}__icontains": variant})
    return condition


class CourseSearchFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        query, terms = search_terms(request.query_params.get("search", ""))
        if not terms:
            return queryset
        for term in terms:
            queryset = queryset.filter(term_condition(term))
        # Search only compact public metadata. Never join paid lesson bodies,
        # private videos, tutor records or student data to a search result.
        rank: Expression = Case(
            When(title__iexact=query, then=Value(100)),
            When(title__istartswith=query, then=Value(70)),
            When(title__icontains=query, then=Value(50)),
            default=Value(0),
            output_field=IntegerField(),
        )
        for term in terms:
            rank = rank + Case(
                When(title__icontains=term, then=Value(10)),
                When(academic_level__icontains=term, then=Value(5)),
                When(curriculum__icontains=term, then=Value(3)),
                default=Value(0),
                output_field=IntegerField(),
            )
        return queryset.annotate(search_relevance=rank)


class CourseOrderingFilter(OrderingFilter):
    def get_ordering(self, request, queryset, view):
        requested = request.query_params.get(self.ordering_param)
        if requested:
            ordering = self.remove_invalid_fields(queryset, requested.split(","), view, request)
            if ordering:
                return [*ordering, "pk"]
        if "search_relevance" in queryset.query.annotations:
            return ["-search_relevance", "order", "title", "pk"]
        return ["order", "title", "pk"]
