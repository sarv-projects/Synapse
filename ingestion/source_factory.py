"""Factory for creating source fetchers from YAML configuration."""
import yaml
from typing import List, Dict, Any
import os

from ingestion.generic_source import GenericSourceFetcher
from ingestion.circuit_breaker_wrapper import get_all_circuit_states

class SourceFactory:
    """Factory for creating and managing source fetchers from configuration."""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            # Default to AI domain sources
            config_path = os.path.join(os.path.dirname(__file__), "..", "domains", "ai", "sources.yaml")
        
        self.config_path = config_path
        self.sources_config = self._load_sources_config()
        self.active_fetchers: Dict[str, GenericSourceFetcher] = {}
    
    def _load_sources_config(self) -> Dict[str, Any]:
        """Load sources configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            raise RuntimeError(f"Failed to load sources config from {self.config_path}: {e}")
    
    def create_fetcher(self, source_name: str) -> GenericSourceFetcher:
        """Create a fetcher for a specific source."""
        if source_name not in self.active_fetchers:
            source_config = self._get_source_config(source_name)
            if not source_config:
                raise ValueError(f"Source '{source_name}' not found in configuration")
            
            self.active_fetchers[source_name] = GenericSourceFetcher(source_config)
        
        return self.active_fetchers[source_name]
    
    def _get_source_config(self, source_name: str) -> Dict[str, Any]:
        """Get configuration for a specific source."""
        sources = self.sources_config.get("sources", [])
        for source in sources:
            if source.get("name") == source_name:
                return source
        return None
    
    def get_all_source_names(self) -> List[str]:
        """Get all configured source names."""
        sources = self.sources_config.get("sources", [])
        return [source.get("name") for source in sources if source.get("name")]
    
    def create_all_fetchers(self) -> Dict[str, GenericSourceFetcher]:
        """Create fetchers for all configured sources."""
        fetchers = {}
        for source_name in self.get_all_source_names():
            try:
                fetchers[source_name] = self.create_fetcher(source_name)
            except Exception as e:
                print(f"Failed to create fetcher for {source_name}: {e}")
        
        return fetchers
    
    def get_source_priority(self) -> Dict[str, List[str]]:
        """Get source priority configuration."""
        return self.sources_config.get("source_priority", {})
    
    def get_entity_coverage(self, source_name: str) -> List[str]:
        """Get entity types covered by a source."""
        source_config = self._get_source_config(source_name)
        return source_config.get("entity_coverage", []) if source_config else []
    
    def get_circuit_states(self) -> Dict[str, Dict[str, Any]]:
        """Get circuit breaker states for all sources."""
        return get_all_circuit_states()
    
    def reload_config(self):
        """Reload the configuration from file."""
        self.sources_config = self._load_sources_config()
        # Clear active fetchers to force recreation with new config
        self.active_fetchers.clear()

# Global factory instance
_source_factory = None

def get_source_factory() -> SourceFactory:
    """Get the global source factory instance."""
    global _source_factory
    if _source_factory is None:
        _source_factory = SourceFactory()
    return _source_factory

def create_fetcher(source_name: str) -> GenericSourceFetcher:
    """Convenience function to create a fetcher."""
    return get_source_factory().create_fetcher(source_name)

def create_all_fetchers() -> Dict[str, GenericSourceFetcher]:
    """Convenience function to create all fetchers."""
    return get_source_factory().create_all_fetchers()
