"""Tiny factories shared by app test suites. Keep them dumb: explicit args, sane defaults."""
from itertools import count

from django.contrib.auth import get_user_model

from stratas.models import Membership, StrataPlan

_seq = count(1)


def make_user(email=None, **extra):
    n = next(_seq)
    email = email or f"user{n}@example.com"
    return get_user_model().objects.create_user(
        username=email, email=email, password="test-pass-123", **extra
    )


def make_strata(plan_number=None, name="Test Strata"):
    return StrataPlan.objects.create(plan_number=plan_number or f"EPS{next(_seq)}", name=name)


def make_membership(user, strata, role=Membership.Role.COUNCIL, status=Membership.Status.ACTIVE, **extra):
    return Membership.objects.create(user=user, strata=strata, role=role, status=status, **extra)
