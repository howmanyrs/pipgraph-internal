"""
PipGraph CLI - Terminal frontend for PipGraph backend API.

Usage:
    pipgraph                    # Start workflow mode (default)
    pipgraph -f/--file path.md  # Process note from file
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Optional

from pipgraph_cli.client import PipGraphClient, test_connection
from pipgraph_cli.ui import get_ui


async def check_backend(backend_url: str) -> bool:
    """
    Check if backend is available.

    Args:
        backend_url: Backend HTTP URL

    Returns:
        True if backend is available, False otherwise
    """
    ui = get_ui()
    ui.print_info(f"Checking backend connection at {backend_url}...")

    if await test_connection(backend_url):
        ui.print_success("Backend is available")
        return True
    else:
        ui.print_error(f"Cannot connect to backend at {backend_url}")
        ui.print_info("Make sure backend is running:")
        ui.print_info("  cd backend/")
        ui.print_info("  uvicorn app.api.main:app --reload")
        return False


async def workflow_mode(backend_url: str, file_path: Optional[str] = None):
    """
    Workflow mode with REST API for processing notes.

    Args:
        backend_url: Backend HTTP URL
        file_path: Optional path to note file to process
    """
    ui = get_ui()
    client = PipGraphClient(backend_url)

    ui.print_header("PipGraph Workflow Mode")
    ui.print_info("Process notes with PARA classification and entity extraction.")
    ui.print_info("Type 'quit' to exit.\n")

    # If file provided, read content from it
    initial_file_path = None
    initial_content = None
    if file_path:
        path = Path(file_path)
        if not path.exists():
            ui.print_error(f"File not found: {file_path}")
            return
        try:
            initial_content = path.read_text(encoding='utf-8')
            initial_file_path = str(path)
        except Exception as e:
            ui.print_error(f"Failed to read file: {e}")
            return

    while True:
        ui.print_separator()

        # Get file path
        if initial_file_path:
            note_path = initial_file_path
            initial_file_path = None  # Only use once
        else:
            note_path = ui.prompt("Enter file path (or 'quit')").strip()

        if note_path.lower() in ['quit', 'exit', 'q']:
            ui.print_info("Exiting workflow mode...")
            break

        if not note_path:
            ui.print_error("File path cannot be empty!")
            continue

        # Get content
        if initial_content:
            content = initial_content
            initial_content = None  # Only use once
            ui.print_info(f"Processing file: {note_path}")
        else:
            content = ui.prompt_multiline("Enter note content")

        if not content.strip():
            ui.print_error("Content cannot be empty!")
            continue

        try:
            # Start workflow
            ui.print_info("\nStarting workflow...")
            workflow_response = await client.start_workflow(note_path, content)
            
            # Use file_path from response or input (should be same)
            current_path = workflow_response.get("file_path", note_path)
            ui.print_workflow_started(current_path, workflow_response["status"])

            # Process workflow until completed
            while True:
                # Get current status using file_path
                status_response = await client.get_workflow_status(current_path)
                current_status = status_response.get("status", "unknown")

                if current_status == "completed":
                    ui.print_workflow_complete(
                        episode_uuid=status_response.get("episode_uuid"),
                        file_path=current_path
                    )
                    break

                elif current_status == "error":
                    ui.print_error(status_response.get("error", "Unknown error"))
                    break

                elif current_status == "waiting_user":
                    # Get suggestions for this note
                    suggestions_response = await client.get_suggestions(current_path)
                    suggestions = suggestions_response.get("suggestions", [])

                    if not suggestions:
                        ui.print_info("Workflow waiting for user, but no suggestions found.")
                        # This might happen if waiting for a general question, not a suggestion
                        # For now, we break to avoid infinite loop, or user can implement generic input
                        break

                    # Process the first suggestion
                    # Note: We process one at a time because submitting a decision resumes the workflow,
                    # which might change the state or resolve other suggestions automatically via cascade.
                    suggestion = suggestions[0]
                    remaining_count = len(suggestions) - 1
                    
                    if remaining_count > 0:
                        ui.print_info(f"Processing 1 of {len(suggestions)} pending suggestions...")

                    ui.print_suggestion(suggestion, 0)
                    ui.print_decision_options()

                    # Get user action
                    action = ui.prompt("Enter action").strip().lower()

                    if action not in ["confirm", "dismiss", "modify", "create_custom"]:
                        ui.print_error(f"Invalid action: {action}")
                        continue # Retry input

                    # Get additional input if needed
                    modified_value = None
                    custom_name = None

                    if action == "modify":
                        modified_value = ui.prompt("Enter new value").strip()
                    elif action == "create_custom":
                        custom_name = ui.prompt("Enter new container name").strip()

                    # Submit decision
                    ui.print_info(f"\nSubmitting decision: {action}...")
                    decision_response = await client.submit_decision(
                        suggestion["suggestion_id"],
                        action,
                        modified_value=modified_value,
                        custom_container_name=custom_name
                    )

                    if decision_response.get("success"):
                        ui.print_success(f"Decision '{action}' applied successfully!")

                        # Show cascade results
                        cascade = decision_response.get("cascade_applied", [])
                        ui.print_cascade_result(cascade)
                        
                        # Loop continues to check status again (which might be processing or next suggestion)
                    else:
                        ui.print_error("Decision failed")
                        break

                elif current_status == "processing":
                    ui.print_status("processing", "Workflow is running...")
                    await asyncio.sleep(1)

                else:
                    ui.print_info(f"Unknown status: {current_status}")
                    await asyncio.sleep(1)

        except Exception as e:
            ui.print_error(f"Workflow error: {e}")
            # Optional: print stack trace for debug
            # import traceback
            # traceback.print_exc()


async def async_main():
    """Async main function."""
    parser = argparse.ArgumentParser(
        description="PipGraph CLI - Terminal frontend for PipGraph backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pipgraph                    # Start workflow mode
  pipgraph -f note.md         # Process note from file
  pipgraph --backend-url http://localhost:8080  # Custom backend URL
        """
    )

    parser.add_argument(
        '--file', '-f',
        type=str,
        help='Process note from file'
    )

    parser.add_argument(
        '--backend-url',
        type=str,
        default='http://localhost:8000',
        help='Backend URL (default: http://localhost:8000)'
    )

    parser.add_argument(
        '--no-rich',
        action='store_true',
        help='Disable rich formatting (use plain text)'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 0.2.0'
    )

    args = parser.parse_args()

    # Initialize UI
    get_ui(use_rich=not args.no_rich)

    # Check backend availability
    if not await check_backend(args.backend_url):
        sys.exit(1)

    # Run workflow mode
    try:
        await workflow_mode(args.backend_url, args.file)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
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
    