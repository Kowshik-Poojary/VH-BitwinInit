"""Case 9: tempfile.NamedTemporaryFile(delete=False) without close."""

import tempfile


def write_scratch_data(payload: bytes) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(payload)
    return tmp.name
