"""Console UI helpers for PipGraph CLI."""

from typing import Optional

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
            self.console.print(f"\n[bold cyan]Testing note:[/bold cyan] {file_path}")
            self.console.print(f"[bold cyan]Content preview:[/bold cyan]")

            preview = content[:max_content_len]
            if len(content) > max_content_len:
                preview += "..."

            self.console.print(Panel(preview, border_style="dim"))
        else:
            print(f"\nTesting note: {file_path}")
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

    def print_result(self, result: dict):
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
            self.console.print("  • Type 'demo' to run demo examples")
            self.console.print("  • Type 'quit' or 'exit' to stop")
            self.console.print("  • Enter file path and content to process note")
            self.console.print("=" * 60 + "\n", style="bold blue")
        else:
            print("\n" + "=" * 60)
            print("PipGraph CLI - Interactive Note Processor".center(60))
            print("=" * 60)
            print("\nCommands:")
            print("  • Type 'demo' to run demo examples")
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
