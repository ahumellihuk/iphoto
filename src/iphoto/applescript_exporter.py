"""AppleScript-based video exporter for Photos.app.

Uses UUID-based lookup to correctly identify videos, even when multiple
videos share the same filename.
"""

import subprocess
import time
from pathlib import Path
from typing import NamedTuple, Optional


class ExportResult(NamedTuple):
    """Result of an AppleScript export attempt."""
    success: bool
    path: Optional[Path]
    error: Optional[str]


def run_applescript(script: str, timeout: int) -> tuple[bool, str, str]:
    """Run AppleScript and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", f"AppleScript timed out after {timeout} seconds"
    except Exception as e:
        return False, "", str(e)


def activate_photos(timeout: int = 10) -> bool:
    """Bring Photos.app to foreground."""
    script = '''
    tell application "Photos"
        activate
    end tell
    '''
    success, _, _ = run_applescript(script, timeout=timeout)
    return success


def restart_photos(timeout: int = 30) -> None:
    """Quit and relaunch Photos.app to recover from AppleScript timeouts."""
    quit_script = '''
    tell application "Photos"
        quit
    end tell
    '''
    run_applescript(quit_script, timeout=timeout)
    time.sleep(2.0)
    activate_photos(timeout=timeout)


def is_timeout_error(message: str) -> bool:
    """Detect AppleEvent timeout errors."""
    msg = message.lower()
    return "timeout" in msg or "-1712" in msg or "appleevent timed out" in msg


def check_photos_responsive(timeout: int = 15) -> bool:
    """Check if Photos.app is running and responsive to AppleScript."""
    script = '''
    tell application "Photos"
        return "OK"
    end tell
    '''
    success, stdout, _ = run_applescript(script, timeout=timeout)
    return success and stdout.strip() == "OK"


def _clean_stale_files(output_dir: Path, filename: str) -> None:
    """Remove zero-byte stale files from a previous failed export attempt."""
    stem = Path(filename).stem
    suffix = Path(filename).suffix.lower()
    for f in output_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() == suffix and f.stem.startswith(stem):
            if f.stat().st_size == 0:
                f.unlink()


def _find_exported_file(output_dir: Path, filename: str) -> Optional[Path]:
    """Find an exported file, accounting for Photos.app renaming (e.g. 'IMG_1234 2.MOV')."""
    # Exact match first
    exact = output_dir / filename
    if exact.is_file():
        return exact

    # Fuzzy match: Photos.app may rename with numeric suffix
    stem = Path(filename).stem
    suffix = Path(filename).suffix.lower()
    for f in output_dir.iterdir():
        if f.is_file() and f.suffix.lower() == suffix and f.stem.startswith(stem):
            return f
    return None


def _poll_for_file(
    output_dir: Path,
    filename: str,
    timeout_seconds: int,
    poll_interval: float,
) -> Optional[Path]:
    """Poll for an exported file to appear with non-zero size."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        found = _find_exported_file(output_dir, filename)
        if found and found.stat().st_size > 0:
            return found
        time.sleep(poll_interval)
    # Final check
    found = _find_exported_file(output_dir, filename)
    if found and found.stat().st_size > 0:
        return found
    return None


def export_via_applescript(
    uuid: str,
    filename: str,
    output_dir: Path,
    timeout: int = 600,
    max_retries: int = 3,
    delay_between_retries: float = 1.0,
    post_export_wait_seconds: int = 30,
    post_export_poll_seconds: float = 1.0,
) -> ExportResult:
    """Export a video from Photos.app using AppleScript with UUID lookup.

    Args:
        uuid: Photos library UUID of the video (primary identifier)
        filename: Original filename (used to locate the exported file on disk)
        output_dir: Directory to export to (must exist)
        timeout: Timeout in seconds for the export operation
        max_retries: Number of retry attempts if export fails
        delay_between_retries: Seconds to wait between retries
        post_export_wait_seconds: Max seconds to wait for file to appear
        post_export_poll_seconds: Seconds between file existence checks

    Returns:
        Tuple of (success, exported_path, error_message)
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale zero-byte files from previous failed attempts
    _clean_stale_files(output_dir, filename)

    # Ensure Photos is active and responsive
    activate_photos()
    if not check_photos_responsive():
        restart_photos()
        time.sleep(3.0)

    # Use UUID to identify the exact video (avoids duplicate filename issues)
    applescript = f'''
tell application "Photos"
    try
        set theItem to media item id "{uuid}"
        set exportPath to POSIX file "{output_dir}"

        with timeout of {timeout} seconds
            export {{theItem}} to exportPath with using originals
        end timeout

        return "SUCCESS"
    on error errMsg number errNum
        if errNum is -1728 then
            return "ERROR:NOT_FOUND:No media item found with id {uuid}"
        end if
        return "ERROR:" & errNum & ":" & errMsg
    end try
end tell
'''

    last_error = None

    for attempt in range(max_retries):
        try:
            success, stdout, stderr = run_applescript(
                applescript, timeout=timeout + 30
            )
            output = stdout.strip()

            if success:
                if output == "SUCCESS":
                    found = _poll_for_file(output_dir, filename, post_export_wait_seconds, post_export_poll_seconds)
                    if found:
                        return ExportResult(True, found, None)
                    last_error = f"Export reported success but file not created after {post_export_wait_seconds}s"
                elif output.startswith("ERROR:NOT_FOUND"):
                    return ExportResult(False, None, f"Video uuid={uuid} not found in Photos library")
                elif output.startswith("ERROR:"):
                    parts = output.split(":", 2)
                    if len(parts) >= 3:
                        last_error = f"AppleScript error {parts[1]}: {parts[2]}"
                    else:
                        last_error = output
                else:
                    last_error = f"Unexpected AppleScript output: {output}"
            else:
                last_error = f"osascript failed: {stderr.strip() if stderr else 'No error message'}"

        except subprocess.TimeoutExpired:
            last_error = f"Export timed out after {timeout} seconds"
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"

        # Retry logic
        if attempt < max_retries - 1:
            _clean_stale_files(output_dir, filename)

            if last_error and (is_timeout_error(last_error) or "not created" in last_error):
                restart_photos()
                time.sleep(3.0)

            delay = delay_between_retries * (2 ** attempt)
            time.sleep(delay)

    return ExportResult(False, None, f"Export failed after {max_retries} attempts: {last_error}")
