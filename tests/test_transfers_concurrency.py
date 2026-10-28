import threading
from decimal import Decimal

import pytest
from django.conf import settings
from django.db import connections

from banking.models import Account, Transaction
from banking.services.transfers import InsufficientFunds, transfer

# Real commits and real threads: the default test transaction would hide the locks.
pytestmark = pytest.mark.django_db(transaction=True)

WELCOME = settings.WELCOME_CREDIT
JOIN_TIMEOUT = 20  # seconds; a deadlock must fail the test, not hang CI


def run_together(jobs):
    """Run each job in its own thread, released at the same moment.

    Returns one entry per job: its result, or the exception it raised.
    """
    barrier = threading.Barrier(len(jobs))
    outcomes: list[object] = [None] * len(jobs)

    def worker(index, job):
        try:
            barrier.wait(timeout=JOIN_TIMEOUT)
            outcomes[index] = job()
        except Exception as error:  # noqa: BLE001 - a thread's exception would otherwise be lost
            outcomes[index] = error
        finally:
            connections.close_all()  # each thread opened its own connection

    threads = [
        threading.Thread(target=worker, args=(index, job))
        for index, job in enumerate(jobs)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(JOIN_TIMEOUT)
    if any(thread.is_alive() for thread in threads):
        pytest.fail("a transfer did not finish: deadlock?")
    return outcomes


def test_concurrent_transfers_cannot_double_spend(account, other_account):
    # Each transfer costs 6,000.00 + 150.00 fee; the 10,000.00 balance covers only one.
    amount = Decimal("6000.00")
    jobs = [
        lambda: transfer(account, other_account.account_number, amount),
        lambda: transfer(account, other_account.account_number, amount),
    ]

    outcomes = run_together(jobs)

    failures = [o for o in outcomes if isinstance(o, InsufficientFunds)]
    assert len(failures) == 1
    assert Account.objects.get(pk=account.pk).balance == WELCOME - Decimal("6150.00")
    assert Account.objects.get(pk=other_account.pk).balance == WELCOME + amount
    assert Transaction.objects.count() == 4  # two welcome credits + one transfer pair


def test_crossing_transfers_do_not_deadlock(account, other_account):
    jobs = [
        lambda: transfer(account, other_account.account_number, Decimal("100.00")),
        lambda: transfer(other_account, account.account_number, Decimal("200.00")),
    ]

    outcomes = run_together(jobs)

    assert not any(isinstance(o, Exception) for o in outcomes)
    # a pays 105 and receives 200; b pays 205 and receives 100
    assert Account.objects.get(pk=account.pk).balance == WELCOME - Decimal(
        "105.00"
    ) + Decimal("200.00")
    assert Account.objects.get(pk=other_account.pk).balance == WELCOME - Decimal(
        "205.00"
    ) + Decimal("100.00")
