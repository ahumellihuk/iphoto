"""AppleScript-based video exporter for Photos.app.

This module uses Photos.app's AppleScript API to export videos, which is more
reliable for iCloud-only videos than osxphotos in scenarios where iCloud storage
is full or local cache is limited.
"""

import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple


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


def export_via_applescript(
    filename: str,
    output_dir: Path,
    timeout: int = 600,
    max_retries: int = 3,
    delay_between_retries: float = 1.0,
    post_export_wait_seconds: int = 30,
    post_export_poll_seconds: float = 1.0,
) -> Tuple[bool, Optional[Path], Optional[str]]:
    """Export a video from Photos.app using AppleScript.

    Args:
        filename: Original filename of the video in Photos (e.g., "IMG_4973.MOV")
        output_dir: Directory to export to (must exist)
        timeout: Timeout in seconds for the export operation
        max_retries: Number of retry attempts if export fails
        delay_between_retries: Seconds to wait between retries

    Returns:
        Tuple of (success, exported_path, error_message)
        - success: True if export succeeded
        - exported_path: Path to exported file if successful, None otherwise
        - error_message: Error description if failed, None if successful

    Notes:
        - Photos.app must be running (will be launched if not)
        - Export uses "Export Unmodified Originals" mode
        - Output directory must already exist
        - The AppleScript API is known to be flaky, hence retry logic
        - Videos are processed one at a time (no batch support)
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

    # AppleScript to export video
    # Using "with using originals" to export unmodified original files
    applescript = f'''
tell application "Photos"
    try
        set theItems to (every media item whose filename is "{filename}")
        if (count of theItems) = 0 then
            return "ERROR:NOT_FOUND:No media item found with filename {filename}"
        end if

        set theItem to item 1 of theItems
        set exportPath to POSIX file "{output_dir}"

        with timeout of {timeout} seconds
            export {{theItem}} to exportPath with using originals
        end timeout

        return "SUCCESS"
    on error errMsg number errNum
        return "ERROR:" & errNum & ":" & errMsg
    end try
end tell
'''

    last_error = None

    for attempt in range(max_retries):
        try:
            # Execute AppleScript
            success, stdout, stderr = run_applescript(
                applescript, timeout=timeout + 30  # Extra buffer for AppleScript overhead
            )
            output = stdout.strip()

            # Check AppleScript result
            if success:
                if output == "SUCCESS":
                    # Verify file was actually exported
                    exported_file = output_dir / filename

                    # Give Photos.app time to finish writing
                    deadline = time.time() + post_export_wait_seconds
                    while time.time() < deadline:
                        # Check exact filename first
                        if exported_file.exists() and exported_file.stat().st_size > 0:
                            return True, exported_file, None
                        # Photos.app may rename (e.g. "IMG_1234 2.MOV") if file already exists
                        found = _find_exported_file(output_dir, filename)
                        if found and found.stat().st_size > 0:
                            return True, found, None
                        time.sleep(post_export_poll_seconds)

                    # Final check after deadline
                    if exported_file.exists():
                        return True, exported_file, None
                    found = _find_exported_file(output_dir, filename)
                    if found:
                        return True, found, None

                    last_error = (
                        f"Export reported success but file not created after {post_export_wait_seconds}s"
                    )
                elif output.startswith("ERROR:NOT_FOUND"):
                    # Video doesn't exist in Photos library
                    return False, None, f"Video '{filename}' not found in Photos library"
                elif output.startswith("ERROR:"):
                    # AppleScript returned an error
                    parts = output.split(":", 2)
                    if len(parts) >= 3:
                        error_code = parts[1]
                        error_msg = parts[2]
                        last_error = f"AppleScript error {error_code}: {error_msg}"
                    else:
                        last_error = output
                else:
                    # Unexpected output
                    last_error = f"Unexpected AppleScript output: {output}"
            else:
                # osascript command failed
                last_error = stderr.strip() if stderr else "No error message"
                last_error = f"osascript failed: {last_error}"

        except subprocess.TimeoutExpired:
            last_error = f"Export timed out after {timeout} seconds"
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"

        # If we got here, the attempt failed
        if attempt < max_retries - 1:
            # Clean up any zero-byte stale files before retry
            _clean_stale_files(output_dir, filename)

            if last_error and (is_timeout_error(last_error) or "not created" in last_error):
                # Restart Photos to reset its internal state
                restart_photos()
                time.sleep(3.0)

            # Progressive backoff between retries
            delay = delay_between_retries * (2 ** attempt)
            time.sleep(delay)

    # All retries exhausted
    return False, None, f"Export failed after {max_retries} attempts: {last_error}"


def batch_export_via_applescript(
    filenames: list[str],
    output_dir: Path,
    timeout_per_video: int = 600,
    delay_between_exports: float = 0.1,
) -> Tuple[dict[str, Path], dict[str, str]]:
    """Export multiple videos sequentially via AppleScript.

    Args:
        filenames: List of original filenames to export
        output_dir: Directory to export to
        timeout_per_video: Timeout in seconds for each video
        delay_between_exports: Delay between exports (helps reliability)

    Returns:
        Tuple of (successes, failures)
        - successes: dict of filename -> exported_path
        - failures: dict of filename -> error_message

    Notes:
        - Exports are strictly sequential (AppleScript limitation)
        - Small delay between exports improves reliability
        - Based on community recommendations for Photos.app AppleScript
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    successes = {}
    failures = {}

    for filename in filenames:
        success, path, error = export_via_applescript(
            filename=filename,
            output_dir=output_dir,
            timeout=timeout_per_video,
        )

        if success and path:
            successes[filename] = path
        else:
            failures[filename] = error or "Unknown error"

        # Delay between exports (community best practice)
        # Helps with Photos.app AppleScript API flakiness
        if delay_between_exports > 0:
            time.sleep(delay_between_exports)

    return successes, failures
