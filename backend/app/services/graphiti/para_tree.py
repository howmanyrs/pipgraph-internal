"""
PARA Tree Builder Module

Построение иерархического дерева PARA-контейнеров на основе связи BELONGS_TO.
Дерево отражает структуру вложенности: Areas -> Projects -> Resources/Archives.

Использование:
    builder = PARATreeBuilder(neo4j_driver)
    tree = await builder.build_tree()
    print(json.dumps(tree, indent=2, ensure_ascii=False))
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


class TreeNode:
    """Узел дерева PARA-контейнеров"""

    def __init__(self, uuid: str, name: str, node_type: str):
        self.uuid = uuid
        self.name = name
        self.node_type = node_type
        self.children: List[TreeNode] = []

    def add_child(self, child: "TreeNode"):
        """Добавить дочерний узел"""
        self.children.append(child)

    def to_dict(self) -> Dict[str, Any]:
        """Рекурсивно преобразовать узел в словарь"""
        return {
            "id": self.uuid,
            "name": self.name,
            "type": self.node_type,
            "children": [child.to_dict() for child in self.children]
        }


class PARATreeBuilder:
    """
    Построитель дерева PARA-контейнеров.

    Алгоритм:
    1. Выполняет Cypher-запрос для получения всех PARA-нод и их родителей
    2. Строит словарь нод по UUID
    3. Строит связи parent -> children
    4. Находит корневые элементы (без родителя)
    5. Рекурсивно сериализует в JSON
    """

    def __init__(self, driver: AsyncDriver):
        """
        Инициализация построителя.

        Args:
            driver: Асинхронный Neo4j драйвер
        """
        self.driver = driver

    async def build_tree(self) -> List[Dict[str, Any]]:
        """
        Построить дерево PARA-контейнеров.

        Returns:
            List[Dict]: Список корневых элементов дерева в формате JSON
        """
        logger.info("Starting PARA tree build process")

        # Шаг 1: Получить данные из Neo4j
        raw_data = await self._fetch_para_nodes()
        logger.info(f"Fetched {len(raw_data)} PARA nodes from database")

        # Шаг 2: Построить граф в памяти
        nodes_map, root_uuids = self._build_graph(raw_data)
        logger.info(f"Built graph with {len(root_uuids)} root nodes")

        # Шаг 3: Сериализовать корневые элементы
        tree = [nodes_map[uuid].to_dict() for uuid in root_uuids]
        logger.info("Tree serialization complete")

        return tree

    async def _fetch_para_nodes(self) -> List[Dict[str, Any]]:
        """
        Выполнить Cypher-запрос для получения PARA-нод и их родителей.

        Returns:
            List[Dict]: Список записей вида {node: {uuid, name, labels}, parent_id: uuid|None}
        """
        query = """
        // 1. Находим все PARA ноды (Проекты, Области, Ресурсы, Архивы)
        MATCH (container:Entity)
        WHERE container:Project OR container:Area OR container:Resource OR container:Archive

        // 2. Ищем родителя по иерархии (куда этот контейнер вложен?)
        OPTIONAL MATCH (container)-[:BELONGS_TO]->(parent:Entity)

        // Возвращаем плоскую таблицу: Контейнер и его Родитель (если есть)
        RETURN
          container { .uuid, .name, labels: labels(container) } AS node,
          parent.uuid AS parent_id
        """

        async with self.driver.session() as session:
            result = await session.run(query)
            records = await result.data()
            return records

    def _build_graph(
        self, raw_data: List[Dict[str, Any]]
    ) -> tuple[Dict[str, TreeNode], List[str]]:
        """
        Построить граф в памяти из плоских данных.

        Args:
            raw_data: Список записей из Neo4j

        Returns:
            tuple: (словарь {uuid -> TreeNode}, список UUID корневых элементов)
        """
        nodes_map: Dict[str, TreeNode] = {}
        parent_child_map: Dict[str, List[str]] = {}  # parent_uuid -> [child_uuids]
        root_uuids: List[str] = []

        # Шаг 1: Создать все узлы
        for record in raw_data:
            node_data = record["node"]
            uuid = node_data["uuid"]
            name = node_data["name"]

            # Извлечь тип PARA (убрать 'Entity' из labels)
            labels = node_data["labels"]
            para_type = self._extract_para_type(labels)

            # Создать узел
            tree_node = TreeNode(uuid=uuid, name=name, node_type=para_type)
            nodes_map[uuid] = tree_node

        # Шаг 2: Построить связи parent -> children
        for record in raw_data:
            node_data = record["node"]
            child_uuid = node_data["uuid"]
            parent_uuid = record.get("parent_id")

            if parent_uuid:
                # Добавить ребенка к родителю
                if parent_uuid not in parent_child_map:
                    parent_child_map[parent_uuid] = []
                parent_child_map[parent_uuid].append(child_uuid)
            else:
                # Это корневой элемент
                root_uuids.append(child_uuid)

        # Шаг 3: Связать узлы в дереве
        for parent_uuid, child_uuids in parent_child_map.items():
            parent_node = nodes_map.get(parent_uuid)
            if not parent_node:
                logger.warning(f"Parent node {parent_uuid} not found in nodes_map")
                continue

            for child_uuid in child_uuids:
                child_node = nodes_map.get(child_uuid)
                if child_node:
                    parent_node.add_child(child_node)
                else:
                    logger.warning(f"Child node {child_uuid} not found in nodes_map")

        return nodes_map, root_uuids

    @staticmethod
    def _extract_para_type(labels: List[str]) -> str:
        """
        Извлечь тип PARA из списка лейблов.

        Args:
            labels: Список лейблов Neo4j (например, ['Entity', 'Project'])

        Returns:
            str: Тип PARA (Project, Area, Resource, Archive)
        """
        # Убираем 'Entity' и берем оставшийся лейбл
        para_types = [label for label in labels if label != "Entity"]
        return para_types[0] if para_types else "Unknown"


async def main():
    """
    Консольная точка входа для тестирования построения дерева.

    Использование:
        cd backend
        python -m app.services.graphiti.para_tree
    """
    import sys
    from neo4j import AsyncGraphDatabase
    from config.settings import settings

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger.info("Connecting to Neo4j...")
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    try:
        # Проверка подключения
        await driver.verify_connectivity()
        logger.info("✓ Neo4j connection established")

        # Построение дерева
        builder = PARATreeBuilder(driver)
        tree = await builder.build_tree()

        # Вывод результата
        print("\n" + "="*60)
        print("PARA TREE STRUCTURE")
        print("="*60 + "\n")
        print(json.dumps(tree, indent=2, ensure_ascii=False))
        print("\n" + "="*60)
        print(f"Total root nodes: {len(tree)}")
        print("="*60)

    except Exception as e:
        logger.error(f"Error building tree: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await driver.close()
        logger.info("Neo4j connection closed")


if __name__ == "__main__":
    asyncio.run(main())
