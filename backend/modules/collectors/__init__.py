# Pacote de coletores (ML, Amazon, etc.)
from .base import BaseCollector
from .ml_collector import MLCollector
from .amazon_collector import AmazonCollector

__all__ = ['BaseCollector', 'MLCollector', 'AmazonCollector']