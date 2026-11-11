"""품질 테스트 공통 설정."""

from __future__ import annotations

import httpx
import pytest

from pipeline.http import SourceBlocked, SourceUnavailable

# network 테스트를 건너뜀으로 바꾸는 예외. 원문 서버가 요청을 막았거나(SourceBlocked) 서버에 닿지
# 못했을 때(SourceUnavailable, PIPELINE_OFFLINE=1, httpx의 전송 오류)다.
UNREACHABLE = (SourceBlocked, SourceUnavailable, httpx.TransportError)


def _unreachable_cause(error: BaseException | None) -> BaseException | None:
    """error나 그 원인 사슬(__cause__, __context__)에서 원문 서버에 닿지 못한 예외를 찾는다.

    파서가 다운로드 오류를 자기 예외로 감싸 다시 올려도 원인을 알아보기 위해서다.
    """
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, UNREACHABLE):
            return error
        seen.add(id(error))
        error = error.__cause__ or error.__context__
    return None


def _skip_if_blocked(item, outcome) -> None:
    """원문 서버에 닿지 못해서 실패한 network 테스트는 실패가 아니라 건너뜀으로 적는다.

    원문을 다시 받아 대조하는 테스트는 fia.com 같은 외부 서버의 요청 제한에 걸리거나, 네트워크가
    막힌 곳(PIPELINE_OFFLINE=1, 샌드박스)에서 돌 수 있다. 그럴 때 우회하지 않고, 건너뛴 까닭을
    남긴다. 코드나 데이터가 틀려서 난 실패는 그대로 실패다.
    """
    if not (outcome.excinfo and item.get_closest_marker("network")):
        return
    error = _unreachable_cause(outcome.excinfo[1])
    if error is None:
        return
    if isinstance(error, SourceBlocked):
        reason = f"원문 서버가 요청을 거부했다: {error}"
    else:
        reason = f"원문 서버에 닿지 못했다: {type(error).__name__}: {error}"
    print(f"::warning::{item.nodeid}: {reason}")
    outcome.force_exception(pytest.skip.Exception(reason))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    """픽스처에서 원문을 받다가 막힌 경우. 모듈 범위 픽스처의 오류는 테스트마다 다시 나온다."""
    outcome = yield
    _skip_if_blocked(item, outcome)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """테스트 본문에서 원문을 받다가 막힌 경우."""
    outcome = yield
    _skip_if_blocked(item, outcome)
