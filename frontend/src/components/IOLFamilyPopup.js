import React, { useState, useEffect } from 'react';

const IOLFamilyPopup = ({ families, selectedEye, onClose, onSelect }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedManufacturer, setSelectedManufacturer] = useState('all');
  const [filteredFamilies, setFilteredFamilies] = useState([]);
  const [manufacturers, setManufacturers] = useState([]);
  const [showAllFamilies, setShowAllFamilies] = useState(false);

  // Top 5 most popular IOL families for quick selection
  const topFamilies = [
    { brand: 'Alcon', family: 'Alcon AcrySof' },
    { brand: 'Johnson and Johnson Vision', family: 'Johnson and Johnson Vision' },
    { brand: 'Bausch + Lomb', family: 'Bausch + Lomb enVista' },
    { brand: 'Alcon', family: 'Alcon Clareon' },
    { brand: 'ZEISS', family: 'ZEISS CT LUCIA' }
  ];

  useEffect(() => {
    // Safety check for families array
    if (!families || !Array.isArray(families)) {
      console.warn('IOLFamilyPopup: families prop is not an array:', families);
      setManufacturers([]);
      setFilteredFamilies([]);
      return;
    }

    // Extract unique manufacturers
    const uniqueManufacturers = [...new Set(families.map(f => f.brand))].sort();
    setManufacturers(uniqueManufacturers);
    
    // Apply filters
    filterFamilies();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [families, searchTerm, selectedManufacturer, showAllFamilies]);

  const filterFamilies = () => {
    if (!families || !Array.isArray(families)) {
      console.warn('IOLFamilyPopup: No families data available');
      setFilteredFamilies([]);
      return;
    }
    
    console.log('IOLFamilyPopup: Filtering', families.length, 'families');
    let filtered = families;

    // Filter by manufacturer
    if (selectedManufacturer !== 'all') {
      filtered = filtered.filter(family => family.brand === selectedManufacturer);
    }

    // Filter by search term
    if (searchTerm) {
      filtered = filtered.filter(family => 
        family.brand.toLowerCase().includes(searchTerm.toLowerCase()) ||
        family.family.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Show only top 5 families initially, or all if showAllFamilies is true
    if (!showAllFamilies) {
      console.log('IOLFamilyPopup: Filtering to top families only');
      const beforeTopFilter = filtered.length;
      filtered = filtered.filter(family => 
        topFamilies.some(topFamily => 
          topFamily.brand === family.brand && topFamily.family === family.family
        )
      );
      console.log('IOLFamilyPopup: Top families filter:', beforeTopFilter, '->', filtered.length);
    }

    setFilteredFamilies(filtered);
  };

  const handleFamilySelect = (family) => {
    onSelect(family);
  };

  return (
    <div className="iol-popup-overlay">
      <div className="iol-popup-content">
        <div className="iol-popup-header">
          <h3>Select IOL Family {selectedEye && `- ${selectedEye}`}</h3>
          <button className="close-button" onClick={onClose}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div className="iol-popup-filters">
          <div className="search-box">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"></circle>
              <path d="m21 21-4.35-4.35"></path>
            </svg>
            <input
              type="text"
              placeholder="Search families..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <div className="manufacturer-filter">
            <select
              value={selectedManufacturer}
              onChange={(e) => setSelectedManufacturer(e.target.value)}
            >
              <option value="all">All Manufacturers</option>
              {manufacturers.map(manufacturer => (
                <option key={manufacturer} value={manufacturer}>
                  {manufacturer}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="iol-popup-body">
          {!families || !Array.isArray(families) ? (
            <div className="no-results">
              <p>Loading IOL families...</p>
            </div>
          ) : filteredFamilies.length === 0 ? (
            <div className="no-results">
              <p>No IOL families found matching your criteria.</p>
              <button 
                className="clear-filters-button"
                onClick={() => {
                  setSearchTerm('');
                  setSelectedManufacturer('all');
                }}
              >
                Clear Filters
              </button>
            </div>
          ) : (
            <>
              <div className="families-grid-popup">
                {filteredFamilies.map((family, index) => (
                  <div 
                    key={`${family.brand}-${family.family}-${index}`} 
                    className="family-card-popup"
                    onClick={() => handleFamilySelect(family)}
                  >
                    <div className="family-brand-popup">{family.brand}</div>
                    <div className="family-name-popup">{family.family}</div>
                    <div className="family-details-popup">
                      <div className="family-a-constant-popup">
                        A-constant: {family.a_constant}
                      </div>
                      <div className="family-model-count-popup">
                        {family.model_count} models
                      </div>
                      {family.toric_available && (
                        <div className="toric-badge-popup">Toric Available</div>
                      )}
                    </div>
                    <div className="family-select-popup">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M9 12l2 2 4-4"></path>
                        <circle cx="12" cy="12" r="10"></circle>
                      </svg>
                      Select
                    </div>
                  </div>
                ))}
              </div>
              
              {!showAllFamilies && families.length > 5 && (
                <div className="show-all-section">
                  <button 
                    className="show-all-button"
                    onClick={() => setShowAllFamilies(true)}
                  >
                    Show All {families.length} Families
                  </button>
                  <p className="show-all-note">
                    Showing top 5 most popular families. Click above to see all {families.length} available families.
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        <div className="iol-popup-footer">
          <div className="popup-stats">
            <span>{filteredFamilies.length} of {families && Array.isArray(families) ? families.length : 0} families</span>
          </div>
          <button className="cancel-button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default IOLFamilyPopup;