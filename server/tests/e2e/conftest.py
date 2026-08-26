from asyncio import sleep

import pytest_asyncio

from tests.e2e.utils import PRINTER_ID, a1_brain, p1_brain

SEED_TIMEOUT = 10.0
SEED_POLL = 0.05


async def wait_until_seeded(brain):
    printer = brain.printers[PRINTER_ID]
    for _ in range(int(SEED_TIMEOUT / SEED_POLL)):
        if printer._seeded:
            break
        await sleep(SEED_POLL)
    return printer


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def printers():
    await a1_brain.start()
    await p1_brain.start()
    await wait_until_seeded(a1_brain)
    await wait_until_seeded(p1_brain)
    yield
    await a1_brain.stop()
    await p1_brain.stop()
