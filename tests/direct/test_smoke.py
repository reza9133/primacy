from tests.direct.helpers import *  # noqa: F401,F403
from tests.direct.helpers import DISTINCT, addr


def test_smoke_full_cycle(h):
    h.create_bounty(slots=2)
    h.check()
    a = h.submit(h.bob, "pagination")
    h.check()
    assert h.adjudicate() == "distinct"
    h.check()
    b = h.submit(h.charlie, "retry")
    assert h.adjudicate() == "distinct"
    assert h.bounty()["status"] == "closed"
    h.check()
    assert h.credit(h.bob) > 0
    assert h.withdraw(h.bob) > 0
    h.check()
