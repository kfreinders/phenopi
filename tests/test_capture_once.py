from datetime import datetime

from scripts.capture.capture_once import write_placeholder_capture


def test_placeholder_capture_creates_empty_timestamped_image(tmp_path):
    output_dir = tmp_path / "captures" / "experiment-one"

    output_path = write_placeholder_capture(
        output_dir,
        captured_at=datetime(2026, 7, 22, 15, 4, 9),
    )

    assert output_path == output_dir / "capture_20260722_150409.jpg"
    assert output_path.exists()
    assert output_path.read_bytes() == b""


def test_placeholder_capture_can_write_to_a_deterministic_path(tmp_path):
    output_path = tmp_path / "run" / "capture_20260722_150409.jpg"

    result = write_placeholder_capture(output_path=output_path)

    assert result == output_path
    assert output_path.is_file()
