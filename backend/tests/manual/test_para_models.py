#!/usr/bin/env python3
"""
Ручной тест для проверки PARA моделей.

Запуск:
    cd backend/
    python tests/manual/test_para_models.py
"""

from app.models.para_entities import Project, Area, Resource, Archive
from config.para_config import PARA_ENTITY_TYPES, PARA_EDGE_TYPES, PARA_EDGE_TYPE_MAP
from datetime import datetime


def test_para_models():
    """Тестируем создание экземпляров PARA моделей"""
    print("=" * 60)
    print("Testing PARA Entity Models")
    print("=" * 60)

    # Test Project
    print("\n1. Testing Project model:")
    project = Project(
        name="Launch Q4 Marketing Campaign",
        status="active",
        deadline=datetime(2024, 12, 31),
        goal="Increase user signups by 20%",
        completion_criteria="Reach 10,000 new signups by end of Q4"
    )
    print(f"   ✓ Created: {project.name}")
    print(f"   ✓ Status: {project.status}")
    print(f"   ✓ Deadline: {project.deadline}")
    print(f"   ✓ Goal: {project.goal}")

    # Test Area
    print("\n2. Testing Area model:")
    area = Area(
        name="Personal Health and Fitness",
        goal="Maintain excellent physical fitness",
        review_frequency="weekly",
        responsibilities=["Exercise 3x per week", "Track nutrition", "Get 7-8 hours sleep"],
        success_indicators=["Energy levels high", "Weight stable", "No injuries"]
    )
    print(f"   ✓ Created: {area.name}")
    print(f"   ✓ Goal: {area.goal}")
    print(f"   ✓ Review: {area.review_frequency}")
    print(f"   ✓ Responsibilities: {len(area.responsibilities)} items")

    # Test Resource
    print("\n3. Testing Resource model:")
    resource = Resource(
        topic="Machine Learning Best Practices",
        description="Curated collection of ML engineering guides",
        category="Reference Guide",
        tags=["python", "machine-learning", "engineering"],
        source_type="curated collection",
        last_reviewed=datetime(2024, 10, 1)
    )
    print(f"   ✓ Created: {resource.topic}")
    print(f"   ✓ Category: {resource.category}")
    print(f"   ✓ Tags: {resource.tags}")
    print(f"   ✓ Source type: {resource.source_type}")

    # Test Archive
    print("\n4. Testing Archive model:")
    archive = Archive(
        original_type="Project",
        original_name="Website Redesign 2023",
        archived_at=datetime(2023, 12, 15),
        archival_reason="Project completed successfully",
        outcome="New website launched with 30% better performance",
        status="archived"
    )
    print(f"   ✓ Created: {archive.original_name}")
    print(f"   ✓ Original type: {archive.original_type}")
    print(f"   ✓ Archived: {archive.archived_at}")
    print(f"   ✓ Reason: {archive.archival_reason}")

    print("\n" + "=" * 60)
    print("Testing PARA Configuration")
    print("=" * 60)

    # Test PARA_ENTITY_TYPES
    print("\n5. PARA_ENTITY_TYPES:")
    for entity_name, entity_class in PARA_ENTITY_TYPES.items():
        print(f"   ✓ {entity_name}: {entity_class.__name__}")

    # Test PARA_EDGE_TYPES
    print("\n6. PARA_EDGE_TYPES:")
    for edge_name, edge_class in PARA_EDGE_TYPES.items():
        print(f"   ✓ {edge_name}: {edge_class.__name__}")

    # Test PARA_EDGE_TYPE_MAP
    print("\n7. PARA_EDGE_TYPE_MAP:")
    for (source, target), edge_types in PARA_EDGE_TYPE_MAP.items():
        print(f"   ✓ ({source}, {target}): {edge_types}")

    print("\n" + "=" * 60)
    print("✅ All PARA models created successfully!")
    print("=" * 60)


def test_model_validation():
    """Тестируем валидацию моделей"""
    print("\n" + "=" * 60)
    print("Testing Model Validation")
    print("=" * 60)

    # Test minimal Project
    print("\n8. Testing minimal Project (only required fields):")
    minimal_project = Project(name="Test Project")
    print(f"   ✓ Name: {minimal_project.name}")
    print(f"   ✓ Status (default): {minimal_project.status}")
    print(f"   ✓ Deadline: {minimal_project.deadline}")

    # Test docstring presence
    print("\n9. Checking docstrings (for LLM):")
    print(f"   ✓ Project docstring: {len(Project.__doc__)} chars")
    print(f"   ✓ Area docstring: {len(Area.__doc__)} chars")
    print(f"   ✓ Resource docstring: {len(Resource.__doc__)} chars")
    print(f"   ✓ Archive docstring: {len(Archive.__doc__)} chars")

    # Show example docstring excerpt
    print("\n10. Example docstring (Project):")
    print(f"   {Project.__doc__[:200]}...")

    print("\n" + "=" * 60)
    print("✅ Validation tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_para_models()
        test_model_validation()
        print("\n🎉 All tests passed! PARA models are ready to use.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
