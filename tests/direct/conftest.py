import pytest

from tests.direct.helpers import Harness


@pytest.fixture
def h(direct_vm, direct_deploy):
    return Harness(direct_vm, direct_deploy)
