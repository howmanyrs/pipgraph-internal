"""
PipGraph CLI - Terminal frontend for PipGraph backend API.

Usage:
    pipgraph                    # Run demo examples (default)
    pipgraph -i/--interactive   # Interactive mode
    pipgraph -d/--demo          # Run demo examples
    pipgraph -f/--file path.md  # Process note from file
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Optional

from pipgraph_cli.client import PipGraphClient, NotePayload
from pipgraph_cli.ui import get_ui
from pipgraph_cli.examples import get_demo_examples


async def test_single_note(
    client: PipGraphClient,
    file_path: str,
    content: str
) -> bool:
    """
    Test processing a single note.

    Args:
        client: PipGraph client instance
        file_path: Path to note file
        content: Note content

    Returns:
        True if successful, False otherwise
    """
    ui = get_ui()

    ui.print_header(f"Processing note: {file_path}")
    ui.print_note_info(file_path, content)

    note = NotePayload(file_path=file_path, content=content)

    success = False

    def on_status(status: str, message: str):
        ui.print_status(status, message)

    def on_error(error_message: str):
        ui.print_error(error_message)

    try:
        result = await client.process_note(
            note,
            on_status=on_status,
            on_error=on_error
        )

        if result:
            ui.print_success("Processing completed!")
            ui.print_result(result)
            success = True
        else:
            ui.print_error("Processing failed - no result returned")

    except ConnectionError as e:
        ui.print_error(f"Connection error: {e}")
        ui.print_info("Make sure backend is running at http://localhost:8000")

    except TimeoutError as e:
        ui.print_error(f"Timeout: {e}")

    except Exception as e:
        ui.print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()

    return success


async def interactive_mode(backend_url: str):
    """
    Interactive mode for entering notes via console.

    Args:
        backend_url: Backend WebSocket URL
    """
    ui = get_ui()
    client = PipGraphClient(backend_url)

    ui.print_welcome()

    while True:
        ui.print_separator()
        file_path = ui.prompt("Enter file path (or command)").strip()

        if file_path.lower() in ['quit', 'exit', 'q']:
            ui.print_info("Exiting...")
            break

        if file_path.lower() == 'demo':
            await run_demo_examples(backend_url)
            continue

        if not file_path:
            ui.print_error("File path cannot be empty!")
            continue

        ui.print_info("Enter note content (press Ctrl+D or Ctrl+Z when done):")
        ui.print_separator()

        try:
            lines = []
            while True:
                try:
                    line = input()
                    lines.append(line)
                except EOFError:
                    break
            content = "\n".join(lines)
        except KeyboardInterrupt:
            ui.print_info("\nCancelled.")
            continue

        if not content.strip():
            ui.print_error("Content cannot be empty!")
            continue

        await test_single_note(client, file_path, content)


async def run_demo_examples(backend_url: str):
    """
    Run demo examples.

    Args:
        backend_url: Backend WebSocket URL
    """
    ui = get_ui()
    client = PipGraphClient(backend_url)
    examples = get_demo_examples()

    ui.print_header("Running Demo Examples")

    for i, example in enumerate(examples, 1):
        ui.print_info(f"\nDemo {i}/{len(examples)}")
        success = await test_single_note(
            client,
            example["file_path"],
            example["content"]
        )

        if i < len(examples):
            # Pause between examples
            await asyncio.sleep(1)

        if not success:
            ui.print_info("Demo execution stopped due to error")
            break


async def test_from_file(backend_url: str, file_path: str):
    """
    Process note from file.

    Args:
        backend_url: Backend WebSocket URL
        file_path: Path to note file
    """
    ui = get_ui()
    client = PipGraphClient(backend_url)
    path = Path(file_path)

    if not path.exists():
        ui.print_error(f"File not found: {file_path}")
        return

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        ui.print_error(f"Failed to read file: {e}")
        return

    await test_single_note(client, str(path), content)


async def check_backend(backend_url: str) -> bool:
    """
    Check if backend is available.

    Args:
        backend_url: Backend WebSocket URL

    Returns:
        True if backend is available, False otherwise
    """
    ui = get_ui()
    ui.print_info(f"Checking backend connection at {backend_url}...")

    from pipgraph_cli.client import test_connection

    if await test_connection(backend_url):
        ui.print_success("Backend is available")
        return True
    else:
        ui.print_error(f"Cannot connect to backend at {backend_url}")
        ui.print_info("Make sure backend is running:")
        ui.print_info("  cd backend/")
        ui.print_info("  uvicorn app.api.main:app --reload")
        return False


async def async_main():
    """Async main function."""
    parser = argparse.ArgumentParser(
        description="PipGraph CLI - Terminal frontend for PipGraph backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pipgraph                    # Run demo examples (default)
  pipgraph -i                 # Interactive mode
  pipgraph -d                 # Run demo examples
  pipgraph -f note.md         # Process note from file
  pipgraph --backend-url ws://localhost:8080  # Custom backend URL
        """
    )

    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode'
    )

    parser.add_argument(
        '--file', '-f',
        type=str,
        help='Process note from file'
    )

    parser.add_argument(
        '--demo', '-d',
        action='store_true',
        help='Run demo examples'
    )

    parser.add_argument(
        '--backend-url',
        type=str,
        default='ws://localhost:8000',
        help='Backend WebSocket URL (default: ws://localhost:8000)'
    )

    parser.add_argument(
        '--no-rich',
        action='store_true',
        help='Disable rich formatting (use plain text)'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 0.1.0'
    )

    args = parser.parse_args()

    # Initialize UI
    ui = get_ui(use_rich=not args.no_rich)

    # Check backend availability
    if not await check_backend(args.backend_url):
        sys.exit(1)

    # Run appropriate mode
    try:
        if args.file:
            await test_from_file(args.backend_url, args.file)

        elif args.demo:
            await run_demo_examples(args.backend_url)

        elif args.interactive:
            await interactive_mode(args.backend_url)

        else:
            # Default: run demo examples
            ui.print_info("No arguments provided. Running demo examples...")
            ui.print_info("Use --help to see available options.\n")
            await run_demo_examples(args.backend_url)

    except KeyboardInterrupt:
        ui.print_info("\n\nInterrupted by user. Exiting...")
        sys.exit(0)


def main():
    """Main entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)


if __name__ == "__main__":
    main()
