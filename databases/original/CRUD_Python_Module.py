"""MongoDB CRUD module for the CS 340 Module Four Milestone.

This module provides the create and read operations for the Austin Animal
Center (AAC) animals collection.
"""

from typing import Any, Dict, List
from urllib.parse import quote_plus

from pymongo import MongoClient
from pymongo.errors import PyMongoError


class AnimalShelter:
    """Provide reusable create and read operations for the AAC database."""

    def __init__(self, username: str, password: str) -> None:
        """Connect to the local MongoDB server using the supplied credentials."""
        encoded_username = quote_plus(username)
        encoded_password = quote_plus(password)

        connection_string = (
            f"mongodb://{encoded_username}:{encoded_password}"
            "@localhost:27017/?authSource=admin"
        )

        self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        self.database = self.client["aac"]
        self.collection = self.database["animals"]

        # Force MongoDB to validate the connection and credentials immediately.
        self.client.admin.command("ping")

    def create(self, data: Dict[str, Any]) -> bool:
        """Insert one document and return True when MongoDB acknowledges it."""
        if not isinstance(data, dict) or not data:
            return False

        try:
            result = self.collection.insert_one(data)
            return bool(result.acknowledged)
        except PyMongoError as error:
            print(f"Create operation failed: {error}")
            return False

    def read(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return all documents matching the query as a Python list."""
        if not isinstance(query, dict):
            return []

        try:
            cursor = self.collection.find(query)
            return list(cursor)
        except PyMongoError as error:
            print(f"Read operation failed: {error}")
            return []

    def update(self, query: Dict[str, Any], new_values: Dict[str, Any]) -> int:
        """Update matching documents and return the number of modified documents."""
        if (
            not isinstance(query, dict)
            or not query
            or not isinstance(new_values, dict)
            or not new_values
        ):
            return 0

        try:
            result = self.collection.update_many(query, {"$set": new_values})
            return int(result.modified_count)
        except PyMongoError as error:
            print(f"Update operation failed: {error}")
            return 0

    def delete(self, query: Dict[str, Any]) -> int:
        """Delete matching documents and return the number of deleted documents."""
        # Requiring a nonempty query prevents an accidental deletion of the collection.
        if not isinstance(query, dict) or not query:
            return 0

        try:
            result = self.collection.delete_many(query)
            return int(result.deleted_count)
        except PyMongoError as error:
            print(f"Delete operation failed: {error}")
            return 0
