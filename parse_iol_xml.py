#!/usr/bin/env python3
"""
Parse IOLCon XML export and create comprehensive IOL database
"""

import xml.etree.ElementTree as ET
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class IOLModel:
    """Represents a single IOL model with all specifications."""
    id: str
    manufacturer: str
    name: str
    family: str
    type: str
    a_constants: Dict[str, float]
    specifications: Dict[str, str]
    toric_available: bool
    toric_models: List[str]


def parse_iol_xml(xml_file: str) -> List[IOLModel]:
    """Parse IOLCon XML file and extract all IOL data."""
    print(f"Parsing {xml_file}...")
    
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    iol_models = []
    
    for lens in root.findall('Lens'):
        try:
            # Basic info
            lens_id = lens.get('id', '')
            manufacturer = get_text(lens, 'Manufacturer', '').strip()
            name = get_text(lens, 'Name', '').strip()
            
            # Determine family (manufacturer + first part of name)
            family = manufacturer
            if name and len(name) > 3:
                # Extract family from name (e.g., "AcrySof IQ" from "AcrySof IQ SN60WF")
                name_parts = name.split()
                if len(name_parts) > 1:
                    family = f"{manufacturer} {' '.join(name_parts[:-1])}"
            
            # IOL type determination
            iol_type = determine_iol_type(name, lens)
            
            # A-constants from different formulas
            a_constants = extract_a_constants(lens)
            
            # Specifications
            specs = extract_specifications(lens)
            
            # Toric availability
            toric_available = is_toric_available(name, lens)
            toric_models = get_toric_models(name) if toric_available else []
            
            model = IOLModel(
                id=lens_id,
                manufacturer=manufacturer,
                name=name,
                family=family,
                type=iol_type,
                a_constants=a_constants,
                specifications=specs,
                toric_available=toric_available,
                toric_models=toric_models
            )
            
            iol_models.append(model)
            
        except Exception as e:
            print(f"Error parsing lens {lens.get('id', 'unknown')}: {e}")
            continue
    
    print(f"Parsed {len(iol_models)} IOL models")
    return iol_models


def get_text(element, tag: str, default: str = '') -> str:
    """Safely get text from XML element."""
    child = element.find(tag)
    return child.text if child is not None else default


def extract_a_constants(lens) -> Dict[str, float]:
    """Extract A-constants from different calculation formulas."""
    constants = {}
    
    # Check for Constants section
    constants_section = lens.find('Constants')
    if constants_section is not None:
        # SRK/T A-constant
        srkt = get_text(constants_section, 'SRKT', '')
        if srkt and srkt.replace('.', '').isdigit():
            constants['srkt'] = float(srkt)
        
        # Holladay 1
        holladay1 = get_text(constants_section, 'Holladay1', '')
        if holladay1 and holladay1.replace('.', '').isdigit():
            constants['holladay1'] = float(holladay1)
        
        # Haigis
        haigis = get_text(constants_section, 'Haigis', '')
        if haigis and haigis.replace('.', '').isdigit():
            constants['haigis'] = float(haigis)
        
        # Hoffer Q
        hofferq = get_text(constants_section, 'HofferQ', '')
        if hofferq and hofferq.replace('.', '').isdigit():
            constants['hofferq'] = float(hofferq)
    
    # Barrett Universal II
    barrett = get_text(lens, 'Barrett', '')
    if barrett and barrett.replace('.', '').isdigit():
        constants['barrett'] = float(barrett)
    
    return constants


def extract_specifications(lens) -> Dict[str, str]:
    """Extract physical specifications."""
    specs = {}
    
    specs_section = lens.find('Specifications')
    if specs_section is not None:
        # Material info
        specs['optic_material'] = get_text(specs_section, 'OpticMaterial', '')
        specs['haptic_material'] = get_text(specs_section, 'HapticMaterial', '')
        
        # Physical properties
        specs['optic_diameter'] = get_text(specs_section, 'OpticDiameter', '')
        specs['haptic_diameter'] = get_text(specs_section, 'HapticDiameter', '')
        specs['incision_width'] = get_text(specs_section, 'IncisionWidth', '')
        
        # Design features
        specs['foldable'] = get_text(specs_section, 'Foldable', '')
        specs['preloaded'] = get_text(specs_section, 'Preloaded', '')
        specs['single_piece'] = get_text(specs_section, 'SinglePiece', '')
        
        # Optical properties
        specs['refractive_index'] = get_text(specs_section, 'RefractiveIndex', '')
        specs['abbe_number'] = get_text(specs_section, 'AbbeNumber', '')
        specs['filter'] = get_text(specs_section, 'Filter', '')
    
    return specs


def determine_iol_type(name: str, lens) -> str:
    """Determine IOL type from name and specifications."""
    name_lower = name.lower()
    
    # Toric
    if 'toric' in name_lower:
        return 'toric'
    
    # Multifocal/Trifocal
    if any(term in name_lower for term in ['multifocal', 'trifocal', 'bifocal']):
        return 'multifocal'
    
    # Extended Depth of Focus
    if any(term in name_lower for term in ['edof', 'extended', 'depth', 'focus']):
        return 'extended_depth_of_focus'
    
    # Accommodating
    if any(term in name_lower for term in ['accommodating', 'crystalens']):
        return 'accommodating'
    
    # Default to monofocal
    return 'monofocal'


def is_toric_available(name: str, lens) -> bool:
    """Check if toric version is available."""
    name_lower = name.lower()
    
    # Already toric
    if 'toric' in name_lower:
        return True
    
    # Check if there's a toric variant mentioned
    # This is a simplified check - in reality, we'd need to cross-reference
    # with other lenses in the database
    
    # Common patterns that suggest toric availability
    toric_indicators = [
        'acrysof', 'tecnis', 'at lisa', 'en vista', 'crystalens',
        'symfony', 'panoptix', 'vivity', 'synergy'
    ]
    
    return any(indicator in name_lower for indicator in toric_indicators)


def get_toric_models(name: str) -> List[str]:
    """Get list of toric models for this IOL."""
    # This would ideally cross-reference with other lenses in the database
    # For now, return a generic toric name
    if 'toric' not in name.lower():
        return [f"{name} Toric"]
    return []


def group_by_family(iol_models: List[IOLModel]) -> Dict[str, List[IOLModel]]:
    """Group IOL models by family."""
    families = defaultdict(list)
    
    for model in iol_models:
        families[model.family].append(model)
    
    return dict(families)


def create_comprehensive_database(iol_models: List[IOLModel]) -> Dict:
    """Create comprehensive IOL database in our format."""
    
    # Group by family
    families_dict = group_by_family(iol_models)
    
    families = []
    
    for family_name, models in families_dict.items():
        if not family_name or not models:
            continue
        
        # Get representative model for family info
        representative = models[0]
        
        # Calculate average A-constant for family (using SRK/T as primary)
        srkt_constants = [
            model.a_constants.get('srkt', 0) 
            for model in models 
            if model.a_constants.get('srkt', 0) > 0
        ]
        
        avg_a_constant = sum(srkt_constants) / len(srkt_constants) if srkt_constants else 118.9
        
        # Count toric availability
        toric_available = any(model.toric_available for model in models)
        
        # Create family models list
        family_models = []
        for model in models:
            family_models.append({
                'id': model.id,
                'name': model.name,
                'type': model.type,
                'description': f"{model.type.title()} IOL",
                'toric_available': model.toric_available,
                'toric_models': model.toric_models,
                'a_constants': model.a_constants,
                'specifications': model.specifications
            })
        
        families.append({
            'id': family_name.lower().replace(' ', '_').replace('&', 'and'),
            'brand': representative.manufacturer,
            'family': family_name,
            'a_constant': round(avg_a_constant, 1),
            'model_count': len(models),
            'toric_available': toric_available,
            'models': family_models
        })
    
    # Sort families by brand and model count
    families.sort(key=lambda x: (x['brand'], -x['model_count']))
    
    return {
        'source': 'IOLCon Export - October 7, 2025',
        'total_models': len(iol_models),
        'total_families': len(families),
        'families': families
    }


def main():
    """Main function to parse XML and create database."""
    xml_file = 'IOLexport.xml'
    
    # Parse XML
    iol_models = parse_iol_xml(xml_file)
    
    # Create comprehensive database
    database = create_comprehensive_database(iol_models)
    
    # Save to JSON
    output_file = 'iol_database_comprehensive.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(database, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Comprehensive IOL database created: {output_file}")
    print(f"📊 Total families: {database['total_families']}")
    print(f"📊 Total models: {database['total_models']}")
    
    # Show top 10 families
    print(f"\n🏆 Top 10 IOL Families:")
    for i, family in enumerate(database['families'][:10], 1):
        print(f"{i:2d}. {family['brand']} {family['family']} ({family['model_count']} models, A-const: {family['a_constant']})")


if __name__ == '__main__':
    main()
