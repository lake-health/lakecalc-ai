"""
IOL Database Service
Comprehensive IOL family and model management for the calculator agent.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class IOLModel:
    """Represents a specific IOL model."""
    id: str
    name: str
    type: str
    description: str
    toric_available: bool
    toric_models: List[str]


@dataclass
class IOLFamily:
    """Represents an IOL family with consistent A-constant."""
    id: str
    brand: str
    family: str
    a_constant: float
    models: List[IOLModel]


class IOLDatabase:
    """IOL Database service for managing IOL families and models."""
    
    def __init__(self, database_path: str = "iol_database_comprehensive.json"):
        self.database_path = Path(database_path)
        self._families: Dict[str, IOLFamily] = {}
        self._cache: Dict[str, any] = {}
        self._last_loaded: float = 0
        self._cache_ttl: float = 300  # 5 minutes cache TTL
        self._load_database()
    
    def _load_database(self):
        """Load IOL database from JSON file with caching."""
        current_time = time.time()
        
        # Check if cache is still valid
        if (self._last_loaded > 0 and 
            current_time - self._last_loaded < self._cache_ttl and 
            self._families):
            return
        
        try:
            start_time = time.time()
            with open(self.database_path, 'r') as f:
                data = json.load(f)
            
            self._families.clear()
            for family_data in data.get('families', []):
                models = [
                    IOLModel(
                        id=model['id'],
                        name=model['name'],
                        type=model['type'],
                        description=model['description'],
                        toric_available=model['toric_available'],
                        toric_models=model.get('toric_models', [])
                    )
                    for model in family_data['models']
                ]
                
                family = IOLFamily(
                    id=family_data['id'],
                    brand=family_data['brand'],
                    family=family_data['family'],
                    a_constant=family_data['a_constant'],
                    models=models
                )
                
                self._families[family.id] = family
            
            self._last_loaded = current_time
            load_time = time.time() - start_time
            print(f"IOL database loaded in {load_time:.3f}s - {len(self._families)} families")
                
        except Exception as e:
            print(f"Error loading IOL database: {e}")
            self._families = {}
    
    def _get_cached_result(self, cache_key: str, compute_func, *args, **kwargs):
        """Get cached result or compute and cache it."""
        current_time = time.time()
        
        if (cache_key in self._cache and 
            current_time - self._cache[cache_key]['timestamp'] < self._cache_ttl):
            return self._cache[cache_key]['data']
        
        result = compute_func(*args, **kwargs)
        self._cache[cache_key] = {
            'data': result,
            'timestamp': current_time
        }
        return result
    
    def get_all_families(self) -> List[Dict]:
        """Get all IOL families with summary information."""
        def _compute_families():
            families = []
            for family_id, family in self._families.items():
                families.append({
                    'id': family.id,
                    'brand': family.brand,
                    'family': family.family,
                    'a_constant': family.a_constant,
                    'model_count': len(family.models),
                    'toric_available': any(model.toric_available for model in family.models)
                })
            return families
        
        return self._get_cached_result('all_families', _compute_families)
    
    def get_family_by_id(self, family_id: str) -> Optional[IOLFamily]:
        """Get specific IOL family by ID."""
        return self._families.get(family_id)
    
    def get_family_models(self, family_id: str) -> List[Dict]:
        """Get all models for a specific family."""
        family = self.get_family_by_id(family_id)
        if not family:
            return []
        
        return [
            {
                'id': model.id,
                'name': model.name,
                'type': model.type,
                'description': model.description,
                'toric_available': model.toric_available,
                'toric_models': model.toric_models
            }
            for model in family.models
        ]
    
    def get_models_by_type(self, family_id: str, model_type: str) -> List[Dict]:
        """Get models of specific type (monofocal, toric, etc.) from a family."""
        family = self.get_family_by_id(family_id)
        if not family:
            return []
        
        return [
            {
                'id': model.id,
                'name': model.name,
                'type': model.type,
                'description': model.description,
                'toric_available': model.toric_available,
                'toric_models': model.toric_models
            }
            for model in family.models
            if model.type == model_type
        ]
    
    def get_toric_models(self, family_id: str) -> List[Dict]:
        """Get all toric models from a family."""
        family = self.get_family_by_id(family_id)
        if not family:
            return []
        
        toric_models = []
        for model in family.models:
            if model.toric_available:
                for toric_name in model.toric_models:
                    toric_models.append({
                        'id': f"{model.id}_toric",
                        'name': toric_name,
                        'type': 'toric',
                        'description': f"Toric version of {model.name}",
                        'base_model': model.name,
                        'toric_available': True,
                        'toric_models': []
                    })
        
        return toric_models
    
    def get_model_by_id(self, family_id: str, model_id: str) -> Optional[Dict]:
        """Get specific model by family and model ID."""
        family = self.get_family_by_id(family_id)
        if not family:
            return None
        
        for model in family.models:
            if model.id == model_id:
                return {
                    'id': model.id,
                    'name': model.name,
                    'type': model.type,
                    'description': model.description,
                    'toric_available': model.toric_available,
                    'toric_models': model.toric_models,
                    'a_constant': family.a_constant
                }
        
        return None
    
    def get_a_constant(self, family_id: str) -> Optional[float]:
        """Get A-constant for a specific family."""
        family = self.get_family_by_id(family_id)
        return family.a_constant if family else None
    
    def search_models(self, query: str) -> List[Dict]:
        """Search for models across all families."""
        results = []
        query_lower = query.lower()
        
        for family_id, family in self._families.items():
            for model in family.models:
                if (query_lower in model.name.lower() or 
                    query_lower in model.description.lower() or
                    query_lower in model.type.lower()):
                    results.append({
                        'family_id': family_id,
                        'family_name': f"{family.brand} {family.family}",
                        'model': {
                            'id': model.id,
                            'name': model.name,
                            'type': model.type,
                            'description': model.description,
                            'toric_available': model.toric_available,
                            'a_constant': family.a_constant
                        }
                    })
        
        return results
    
    def get_families_for_recommendation(self, recommend_toric: bool) -> List[Dict]:
        """Get families suitable for toric or non-toric recommendations."""
        families = self.get_all_families()
        
        if recommend_toric:
            # Return families that have toric models
            return [f for f in families if f['toric_available']]
        else:
            # Return all families (they all have non-toric options)
            return families


# Global database instance
iol_database = IOLDatabase()


def get_iol_database() -> IOLDatabase:
    """Get the global IOL database instance."""
    return iol_database

