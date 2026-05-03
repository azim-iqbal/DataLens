RESULT_CACHE: dict[str, dict] = {}


def store_result(session_id: str, result: dict) -> None:
    RESULT_CACHE[session_id] = result


def get_result(session_id: str) -> dict | None:
    return RESULT_CACHE.get(session_id)


def update_result(session_id: str, result: dict) -> None:
    RESULT_CACHE[session_id] = result
