"""Console UI helpers for PipGraph CLI."""

from typing import Optional, List, Dict, Any

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.syntax import Syntax
    from rich.markdown import Markdown
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # Fallback to simple print-based UI
    Console = None


class UI:
    """Console UI manager with rich formatting."""

    def __init__(self, use_rich: bool = True):
        """
        Initialize UI manager.

        Args:
            use_rich: Use rich library for formatting (fallback to plain if not available)
        """
        self.use_rich = use_rich and RICH_AVAILABLE

        if self.use_rich:
            self.console = Console()
        else:
            self.console = None

    def print_header(self, title: str):
        """Print section header."""
        if self.use_rich:
            self.console.print("\n" + "=" * 60, style="bold blue")
            self.console.print(title, style="bold blue", justify="center")
            self.console.print("=" * 60, style="bold blue")
        else:
            print(f"\n{'=' * 60}")
            print(title.center(60))
            print("=" * 60)

    def print_separator(self):
        """Print separator line."""
        if self.use_rich:
            self.console.print("-" * 60, style="dim")
        else:
            print("-" * 60)

    def print_note_info(self, file_path: str, content: str, max_content_len: int = 200):
        """
        Print note information.

        Args:
            file_path: Path to note file
            content: Note content
            max_content_len: Maximum content preview length
        """
        if self.use_rich:
            self.console.print(f"\n[bold cyan]Processing note:[/bold cyan] {file_path}")
            self.console.print(f"[bold cyan]Content preview:[/bold cyan]")

            preview = content[:max_content_len]
            if len(content) > max_content_len:
                preview += "..."

            self.console.print(Panel(preview, border_style="dim"))
        else:
            print(f"\nProcessing note: {file_path}")
            print(f"Content:")
            preview = content[:max_content_len]
            if len(content) > max_content_len:
                preview += "..."
            print(preview)
            print()

    def print_status(self, status: str, message: str = ""):
        """Print status update."""
        if self.use_rich:
            if status == "processing":
                self.console.print(f"⏳ [yellow]{message}[/yellow]")
            elif status == "done":
                self.console.print(f"✓ [green]{message}[/green]")
            else:
                self.console.print(f"ℹ [blue]{status}:[/blue] {message}")
        else:
            if status == "processing":
                print(f"⏳ {message}")
            elif status == "done":
                print(f"✓ {message}")
            else:
                print(f"ℹ {status}: {message}")

    def print_error(self, error_message: str):
        """Print error message."""
        if self.use_rich:
            self.console.print(f"\n✗ [bold red]Error:[/bold red] {error_message}")
        else:
            print(f"\n✗ Error: {error_message}")

    def print_success(self, message: str = "Success!"):
        """Print success message."""
        if self.use_rich:
            self.console.print(f"\n✓ [bold green]{message}[/bold green]")
        else:
            print(f"\n✓ {message}")

    def print_result(self, result: Dict[str, Any]):
        """
        Print processing result.

        Args:
            result: Result data from backend
        """
        if self.use_rich:
            self.console.print("\n[bold cyan]Result:[/bold cyan]")
            # Pretty print JSON
            import json
            result_json = json.dumps(result, indent=2, ensure_ascii=False)
            syntax = Syntax(result_json, "json", theme="monokai", line_numbers=False)
            self.console.print(syntax)
        else:
            print("\nResult:")
            import json
            print(json.dumps(result, indent=2, ensure_ascii=False))

    def print_welcome(self):
        """Print welcome banner."""
        if self.use_rich:
            self.console.print("\n" + "=" * 60, style="bold blue")
            self.console.print("PipGraph CLI - Interactive Note Processor", style="bold blue", justify="center")
            self.console.print("=" * 60, style="bold blue")
            self.console.print("\nCommands:", style="bold")
            self.console.print("  • Type 'quit' or 'exit' to stop")
            self.console.print("  • Enter file path and content to process note")
            self.console.print("=" * 60 + "\n", style="bold blue")
        else:
            print("\n" + "=" * 60)
            print("PipGraph CLI - Interactive Note Processor".center(60))
            print("=" * 60)
            print("\nCommands:")
            print("  • Type 'quit' or 'exit' to stop")
            print("  • Enter file path and content to process note")
            print("=" * 60 + "\n")

    def prompt(self, message: str) -> str:
        """
        Prompt user for input.

        Args:
            message: Prompt message

        Returns:
            User input
        """
        if self.use_rich:
            return self.console.input(f"[bold cyan]{message}[/bold cyan] ")
        else:
            return input(f"{message} ")

    def print_info(self, message: str):
        """Print informational message."""
        if self.use_rich:
            self.console.print(f"[dim]{message}[/dim]")
        else:
            print(message)

    # ========================================================================
    # Workflow-specific UI methods
    # ========================================================================

    def print_workflow_started(self, file_path: str, status: str):
        """Print workflow started message."""
        if self.use_rich:
            self.console.print(f"\n[bold green]Workflow started for:[/bold green] {file_path}")
            self.console.print(f"[bold cyan]Status:[/bold cyan] {status}")
        else:
            print(f"\nWorkflow started for: {file_path}")
            print(f"Status: {status}")

    def print_workflow_status(self, status: Dict[str, Any]):
        """Print workflow status details."""
        if self.use_rich:
            self.console.print(f"\n[bold cyan]Workflow Status:[/bold cyan]")
            self.console.print(f"  File: {status.get('file_path', 'unknown')}")
            self.console.print(f"  Status: {status.get('status', 'unknown')}")
            if status.get('episode_uuid'):
                self.console.print(f"  Episode: {status.get('episode_uuid')}")
            if status.get('error'):
                self.console.print(f"  [red]Error: {status.get('error')}[/red]")
        else:
            print(f"\nWorkflow Status:")
            print(f"  File: {status.get('file_path', 'unknown')}")
            print(f"  Status: {status.get('status', 'unknown')}")
            if status.get('episode_uuid'):
                print(f"  Episode: {status.get('episode_uuid')}")
            if status.get('error'):
                print(f"  Error: {status.get('error')}")

    def print_suggestion(self, suggestion: Dict[str, Any], index: int = 0):
        """Print a single suggestion for user review."""
        if self.use_rich:
            self.console.print(f"\n[bold yellow]Suggestion #{index + 1}:[/bold yellow]")
            self.console.print(f"  Type: {suggestion.get('suggestion_type', 'unknown')}")
            self.console.print(f"  Container: {suggestion.get('container_name', 'unknown')} ({suggestion.get('container_type', '')})")
            
            reasoning = suggestion.get('reasoning')
            if reasoning:
                self.console.print(f"  Reasoning: [italic]{reasoning}[/italic]")

            confidence = suggestion.get('confidence', 0)
            color = "green" if confidence > 0.8 else "yellow" if confidence > 0.5 else "red"
            self.console.print(f"  Confidence: [{color}]{confidence:.2f}[/{color}]")

            alternatives = suggestion.get('alternatives', [])
            if alternatives:
                self.console.print(f"  Alternatives:")
                for alt in alternatives:
                    self.console.print(f"    - {alt.get('container_name', 'unknown')} ({alt.get('confidence', 0):.2f})")
        else:
            print(f"\nSuggestion #{index + 1}:")
            print(f"  Type: {suggestion.get('suggestion_type', 'unknown')}")
            print(f"  Container: {suggestion.get('container_name', 'unknown')} ({suggestion.get('container_type', '')})")
            
            reasoning = suggestion.get('reasoning')
            if reasoning:
                print(f"  Reasoning: {reasoning}")
                
            print(f"  Confidence: {suggestion.get('confidence', 0):.2f}")

            alternatives = suggestion.get('alternatives', [])
            if alternatives:
                print(f"  Alternatives:")
                for alt in alternatives:
                    print(f"    - {alt.get('container_name', 'unknown')} ({alt.get('confidence', 0):.2f})")

    def print_decision_options(self):
        """Print available decision options."""
        if self.use_rich:
            self.console.print("\n[bold]Available actions:[/bold]")
            self.console.print("  [green]confirm[/green] - Accept this suggestion")
            self.console.print("  [red]dismiss[/red] - Reject this suggestion")
            self.console.print("  [yellow]modify[/yellow] - Change the suggested value")
            self.console.print("  [blue]create_custom[/blue] - Create a new container")
        else:
            print("\nAvailable actions:")
            print("  confirm - Accept this suggestion")
            print("  dismiss - Reject this suggestion")
            print("  modify - Change the suggested value")
            print("  create_custom - Create a new container")

    def print_cascade_result(self, cascade_applied: List[Dict[str, Any]]):
        """
        Print cascade auto-resolution results.
        Expected items contain: note_path, confidence, etc.
        """
        if not cascade_applied:
            return

        if self.use_rich:
            self.console.print(f"\n[bold magenta]Cascade auto-resolved {len(cascade_applied)} similar suggestion(s):[/bold magenta]")
            for item in cascade_applied:
                path = item.get('note_path', 'unknown')
                conf = item.get('confidence', 0)
                self.console.print(f"  - {path} (confidence: {conf:.2f})")
        else:
            print(f"\nCascade auto-resolved {len(cascade_applied)} similar suggestion(s):")
            for item in cascade_applied:
                path = item.get('note_path', 'unknown')
                conf = item.get('confidence', 0)
                print(f"  - {path} (confidence: {conf:.2f})")

    def print_workflow_complete(self, episode_uuid: Optional[str] = None, file_path: Optional[str] = None):
        """Print workflow completion message."""
        if self.use_rich:
            msg = "\n[bold green]✓ Workflow completed successfully![/bold green]"
            if file_path:
                msg = f"\n[bold green]✓ Workflow completed for: {file_path}[/bold green]"
            self.console.print(msg)
            
            if episode_uuid:
                self.console.print(f"[dim]Episode UUID: {episode_uuid}[/dim]")
        else:
            msg = "\n✓ Workflow completed successfully!"
            if file_path:
                msg = f"\n✓ Workflow completed for: {file_path}"
            print(msg)
            
            if episode_uuid:
                print(f"Episode UUID: {episode_uuid}")

    def prompt_multiline(self, message: str) -> str:
        """
        Prompt user for multiline input.

        Args:
            message: Prompt message

        Returns:
            User input (end with empty line)
        """
        if self.use_rich:
            self.console.print(f"[bold cyan]{message}[/bold cyan] (end with empty line):")
        else:
            print(f"{message} (end with empty line):")

        lines = []
        while True:
            try:
                line = input()
                if not line:
                    break
                lines.append(line)
            except EOFError:
                # Handle Ctrl+D or closed input stream
                break

        return "\n".join(lines)


# Singleton instance
_ui_instance: Optional[UI] = None


def get_ui(use_rich: bool = True) -> UI:
    """
    Get or create UI singleton instance.

    Args:
        use_rich: Use rich library for formatting

    Returns:
        UI instance
    """
    global _ui_instance
    if _ui_instance is None:
        _ui_instance = UI(use_rich=use_rich)
    return _ui_instance