from __future__ import annotations
from typing import List, Dict

class BaseCollector:
    """Interface base para coletores (apenas extração)."""
    def run_collection(self) -> List[Dict]:
        raise NotImplementedError("Implementar no coletor específico.")

    def close(self):
        """Liberar recursos (ex.: drivers)."""
        pass