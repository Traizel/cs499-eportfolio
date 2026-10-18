"""Validated database enhancement API, retaining the Milestone Two CRUD API."""
from .service import AnimalService
from . import search

class DatabaseService(AnimalService):
    def search(self, filters=None, **options):
        self._ensure_open()
        spec = search.specification({} if filters is None else filters, **options)
        return self._repository.search(spec)

    def rescue_summary(self, filters=None, **options):
        self._ensure_open()
        pipeline = search.summary_pipeline({} if filters is None else filters, **options)
        return self._repository.rescue_summary(pipeline)
