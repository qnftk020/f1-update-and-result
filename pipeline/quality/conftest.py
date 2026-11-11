"""품질 테스트 공통 설정."""

from __future__ import annotations

import pytest

from pipeline.http import SourceBlocked


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """원문 서버가 요청을 막아서 실패한 network 테스트는 실패가 아니라 건너뜀으로 적는다.

    원문을 다시 받아 대조하는 테스트는 fia.com 같은 외부 서버의 요청 제한에 걸릴 수 있다. 그럴 때
    우회하지 않고, 건너뛴 까닭을 남긴다. 코드나 데이터가 틀려서 난 실패는 그대로 실패다.
    """
    outcome = yield
    if outcome.excinfo and item.get_closest_marker("network"):
        error = outcome.excinfo[1]
        if isinstance(error, SourceBlocked):
            print(f"::warning::{item.nodeid}: 원문 서버가 요청을 거부해 건너뛴다 ({error})")
            outcome.force_exception(pytest.skip.Exception(f"원문 서버가 요청을 거부했다: {error}"))
