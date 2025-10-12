#!/usr/bin/env python3
"""
Parse IOLexport.xml to extract IOL-specific constants for each lens.
This will provide manufacturer-optimized constants for more accurate calculations.
"""

import xml.etree.ElementTree as ET
import json
from typing import Dict, List, Optional

def parse_iol_constants(xml_file: str) -> Dict:
    """Parse IOL constants from XML file."""
    print(f"Parsing IOL constants from {xml_file}...")
    
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    constants_data = {
        "lenses": {},
        "summary": {
            "total_lenses": 0,
            "lenses_with_haigis": 0,
            "lenses_with_srkt": 0,
            "lenses_with_barrett": 0
        }
    }
    
    for lens in root.findall('Lens'):
        lens_id = lens.get('id')
        manufacturer = lens.find('Manufacturer').text if lens.find('Manufacturer') is not None else "Unknown"
        name = lens.find('Name').text if lens.find('Name') is not None else "Unknown"
        
        # Extract specifications
        specs = {}
        specs_elem = lens.find('Specifications')
        if specs_elem is not None:
            for spec in specs_elem:
                if spec.text:
                    specs[spec.tag] = spec.text
        
        # Extract constants (try ULIB first, then nominal)
        constants = {}
        constants_elem = lens.find('Constants[@type="ULIB"]')
        if constants_elem is None:
            constants_elem = lens.find('Constants[@type="nominal"]')
        if constants_elem is not None:
            # SRK/T constant
            srkt_elem = constants_elem.find('SRKt')
            if srkt_elem is not None and srkt_elem.text:
                constants['srkt_a'] = float(srkt_elem.text)
                constants_data["summary"]["lenses_with_srkt"] += 1
            
            # Haigis constants
            haigis_elem = constants_elem.find('Haigis')
            if haigis_elem is not None:
                a0 = haigis_elem.find('a0')
                a1 = haigis_elem.find('a1') 
                a2 = haigis_elem.find('a2')
                
                if a0 is not None and a0.text and a1 is not None and a1.text and a2 is not None and a2.text:
                    constants['haigis'] = {
                        'a0': float(a0.text),
                        'a1': float(a1.text),
                        'a2': float(a2.text)
                    }
                    constants_data["summary"]["lenses_with_haigis"] += 1
            
            # Barrett constants
            barrett_elem = constants_elem.find('Barrett')
            if barrett_elem is not None:
                lf = barrett_elem.find('LF')
                df = barrett_elem.find('DF')
                
                barrett_constants = {}
                if lf is not None and lf.text:
                    barrett_constants['LF'] = float(lf.text)
                if df is not None and df.text:
                    barrett_constants['DF'] = float(df.text)
                
                if barrett_constants:
                    constants['barrett'] = barrett_constants
                    constants_data["summary"]["lenses_with_barrett"] += 1
            
            # Holladay1 constant
            holladay1_elem = constants_elem.find('Holladay1')
            if holladay1_elem is not None and holladay1_elem.text:
                constants['holladay1_sf'] = float(holladay1_elem.text)
            
            # HofferQ constant
            hofferq_elem = constants_elem.find('HofferQ')
            if hofferq_elem is not None and hofferq_elem.text:
                constants['hofferq_pacd'] = float(hofferq_elem.text)
        
        # Store lens data
        lens_data = {
            "manufacturer": manufacturer,
            "name": name,
            "specifications": specs,
            "constants": constants
        }
        
        constants_data["lenses"][lens_id] = lens_data
        constants_data["summary"]["total_lenses"] += 1
    
    return constants_data

def save_constants_json(constants_data: Dict, output_file: str):
    """Save parsed constants to JSON file."""
    print(f"Saving constants to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(constants_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved {constants_data['summary']['total_lenses']} lenses to {output_file}")

def print_summary(constants_data: Dict):
    """Print summary of parsed constants."""
    summary = constants_data["summary"]
    
    print("\n" + "="*60)
    print("📊 IOL CONSTANTS PARSING SUMMARY")
    print("="*60)
    print(f"Total Lenses: {summary['total_lenses']}")
    print(f"Lenses with Haigis constants: {summary['lenses_with_haigis']}")
    print(f"Lenses with SRK/T constants: {summary['lenses_with_srkt']}")
    print(f"Lenses with Barrett constants: {summary['lenses_with_barrett']}")
    
    # Show sample of lenses with Haigis constants
    print("\n🔍 SAMPLE LENSES WITH HAIGIS CONSTANTS:")
    print("-" * 60)
    
    count = 0
    for lens_id, lens_data in constants_data["lenses"].items():
        if "haigis" in lens_data["constants"]:
            haigis = lens_data["constants"]["haigis"]
            print(f"{lens_data['manufacturer']} {lens_data['name']}: a₀={haigis['a0']}, a₁={haigis['a1']}, a₂={haigis['a2']}")
            count += 1
            if count >= 10:  # Show first 10
                break
    
    if summary['lenses_with_haigis'] > 10:
        print(f"... and {summary['lenses_with_haigis'] - 10} more")

if __name__ == "__main__":
    # Parse the XML file
    xml_file = "IOLexport.xml"
    constants_data = parse_iol_constants(xml_file)
    
    # Save to JSON
    output_file = "iol_constants_parsed.json"
    save_constants_json(constants_data, output_file)
    
    # Print summary
    print_summary(constants_data)
    
    print(f"\n✅ Constants parsing complete!")
    print(f"📁 Output file: {output_file}")

