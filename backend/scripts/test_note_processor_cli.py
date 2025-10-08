"""
Консольный тестовый модуль для быстрого тестирования note_processor
Использование:
    python app/services/test_note_processor_cli.py
    python app/services/test_note_processor_cli.py --interactive
    python app/services/test_note_processor_cli.py --file path/to/note.md
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию backend в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.note import NotePayload
from app.services.note_processor import process_and_store_note


async def test_single_note(file_path: str, content: str):
    """Тестирует обработку одной заметки"""
    print(f"\n{'='*60}")
    print(f"Testing note: {file_path}")
    print(f"{'='*60}")
    print(f"Content:\n{content[:200]}{'...' if len(content) > 200 else ''}\n")

    note = NotePayload(file_path=file_path, content=content)

    try:
        result = await process_and_store_note(note)
        print(f"\n✓ Success!")
        print(f"Result: {result}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


async def interactive_mode():
    """Интерактивный режим для ввода заметок"""
    print("\n" + "="*60)
    print("Interactive Note Processor Test")
    print("="*60)
    print("Enter notes to process. Type 'quit' or 'exit' to stop.")
    print("Enter 'demo' to run demo examples.")
    print("="*60 + "\n")

    while True:
        print("\n" + "-"*60)
        file_path = input("Enter file path (or command): ").strip()

        if file_path.lower() in ['quit', 'exit', 'q']:
            print("Exiting...")
            break

        if file_path.lower() == 'demo':
            await run_demo_examples()
            continue

        if not file_path:
            print("File path cannot be empty!")
            continue

        print("Enter note content (press Ctrl+D or Ctrl+Z when done):")
        print("-"*60)

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
            print("\nCancelled.")
            continue

        if not content.strip():
            print("Content cannot be empty!")
            continue

        await test_single_note(file_path, content)


async def run_demo_examples():
    """Запускает несколько демонстрационных примеров"""
    examples = [
        {
            "file_path": "notes/people/john_doe.md",
            "content": """# John Doe

John Doe is a software engineer at TechCorp.
He works on backend systems and has expertise in Python and FastAPI.
John graduated from MIT in 2015 with a degree in Computer Science.
"""
        },
        {
            "file_path": "notes/projects/pipgraph.md",
            "content": """# PipGraph Project

PipGraph is an Obsidian plugin that uses Neo4j graph database.
The project uses FastAPI for the backend and TypeScript for the frontend.
It integrates with Graphiti for entity extraction and knowledge graph building.
"""
        },
        {
            "file_path": "notes/meetings/standup_2024_01_15.md",
            "content": """# Daily Standup - January 15, 2024

Attendees: Alice, Bob, Charlie

Alice:
- Completed the authentication module
- Working on user profile page

Bob:
- Fixed bugs in the payment system
- Planning to start integration tests

Charlie:
- Researching graph database options
- Meeting with the design team tomorrow
"""
        }
    ]

    print("\n" + "="*60)
    print("Running Demo Examples")
    print("="*60)

    for example in examples:
        await test_single_note(example["file_path"], example["content"])
        await asyncio.sleep(1)  # Небольшая пауза между примерами


async def test_from_file(file_path: str):
    """Тестирует обработку заметки из файла"""
    path = Path(file_path)

    if not path.exists():
        print(f"Error: File not found: {file_path}")
        return

    content = path.read_text(encoding='utf-8')
    await test_single_note(str(path), content)


async def main():
    """Главная функция"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test note_processor with console input"
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

    args = parser.parse_args()

    if args.file:
        await test_from_file(args.file)
    elif args.demo:
        await run_demo_examples()
    elif args.interactive:
        await interactive_mode()
    else:
        # По умолчанию запускаем демо
        print("No arguments provided. Running demo examples...")
        print("Use --help to see available options.\n")
        await run_demo_examples()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)
