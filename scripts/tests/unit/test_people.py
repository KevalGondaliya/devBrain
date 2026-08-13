from __future__ import annotations

import random

from faker import Faker

from generators.people import generate_people


def test_generate_people_distinct_names_and_emails() -> None:
    fake = Faker()
    fake.seed_instance(42)
    rng = random.Random(42)
    people = generate_people(fake, rng, count=24)
    assert len(people) == 24
    assert len({p.name for p in people}) == 24
    assert len({p.email for p in people}) == 24
    assert all(p.role for p in people)


def test_generate_people_reproducible_given_same_seed() -> None:
    fake1 = Faker()
    fake1.seed_instance(7)
    people1 = generate_people(fake1, random.Random(7), count=10)

    fake2 = Faker()
    fake2.seed_instance(7)
    people2 = generate_people(fake2, random.Random(7), count=10)

    assert people1 == people2
