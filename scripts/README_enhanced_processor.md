# Enhanced Survey Data Processor

An advanced Python tool for processing census survey data with OCR capabilities, deep filesystem scanning, and comprehensive data quality analysis.

## Features

### 🔍 **Deep Filesystem Scanning**
- Recursive traversal through folder structures to find all CSV/XLSX/XLS files
- Document discovery (PDF, DOCX) for column description extraction
- Configurable depth limits and file type filtering

### 📄 **OCR Document Analysis**
- Extract text from PDF and DOCX files using multiple methods
- Pattern matching to identify column descriptions in documentation
- Support for scanned PDFs via Tesseract OCR
- Intelligent fallback between pdfplumber, PyPDF2, and OCR

### 🔗 **Enhanced Column Mapping**
- Priority-based column description system:
  1. Direct documentation matches
  2. Common census mappings
  3. Pattern matching for census codes (ACS, population estimates)
- Comprehensive census code parsing (B01001_001E format)
- Geographic identifier recognition (FIPS, GEOID)

### 📊 **Data Quality Analysis**
- Statistical analysis (mean, std, min, max) for numeric columns
- Missing value analysis and completeness metrics
- Duplicate detection for key columns
- Geographic code validation (FIPS state codes)
- Data anomaly detection:
  - Statistical outliers
  - Suspicious repetitive values
  - Invalid geographic codes
  - Null-like string patterns

### 🚀 **Standalone Analysis Script**
- Quick analysis without full ETL pipeline
- JSON output with detailed results
- Command-line interface for automation
- Data quality recommendations

## Installation

### Required Dependencies

```bash
# Core dependencies
pip install pandas numpy pathlib

# OCR and document processing
pip install PyPDF2 pdfplumber pytesseract pillow python-docx

# Optional: For PDF OCR support
pip install pdf2image
# Also install system dependencies:
# - Ubuntu/Debian: sudo apt-get install tesseract-ocr poppler-utils
# - macOS: brew install tesseract poppler
# - Windows: Download and install Tesseract and add to PATH

# Data analysis
pip install scipy scikit-learn
```

### Optional GPU Acceleration
```bash
# For enhanced OCR performance (optional)
pip install torch torchvision
```

## Usage

### Basic Usage

```python
from process_survey_data import SurveyDataProcessor

# Initialize processor
processor = SurveyDataProcessor('/path/to/data')

# Deep filesystem scan
found_files = processor.deep_scan_filesystem(max_depth=5)

# Extract column descriptions from documents
doc_descriptions = processor.extract_column_descriptions_from_docs(found_files['documents'])

# Enhanced processing pipeline
results = processor.enhanced_processing_pipeline(max_depth=3)
```

### Standalone Analysis Script

```bash
# Run analysis on default data directory
python standalone_analysis.py

# Specify custom data directory
python standalone_analysis.py --data-dir /path/to/census/data

# Quick quality check on single CSV
python standalone_analysis.py --csv-file /path/to/file.csv

# Limit number of files processed
python standalone_analysis.py --max-files 10
```

### Command Line Options

```bash
python standalone_analysis.py --help
```

- `--data-dir`: Custom data directory path
- `--csv-file`: Single CSV file for quick quality check  
- `--max-files`: Maximum files to analyze (default: 5)

## Output

### Analysis Results JSON
```json
{
  "timestamp": "2024-01-15T10:30:00",
  "filesystem_scan": {
    "data_files": 45,
    "document_files": 8,
    "total_scanned": 53
  },
  "document_analysis": {
    "documents_processed": 8,
    "column_descriptions_found": 127,
    "sample_descriptions": {...}
  },
  "csv_analysis": {
    "files_analyzed": 10,
    "total_columns_found": 234,
    "sample_analyses": [...]
  },
  "column_mapping": {
    "total_columns_mapped": 234,
    "enhanced_descriptions": 89,
    "sample_mappings": {...}
  },
  "recommendations": [...]
}
```

### Data Quality Metrics
- **Completeness**: Percentage of non-null values per column
- **Consistency**: Duplicate rates for key identifiers
- **Validity**: Range validation for known columns
- **Anomaly Detection**: Statistical outliers and data issues

## File Structure

```
├── process_survey_data.py    # Main processor class
├── standalone_analysis.py    # CLI analysis tool
├── README.md                # This file
└── data/                    # Default data directory
    ├── census_surveys/       # Downloaded census data
    └── documents/           # Documentation files
```

## Example Workflow

1. **Deep Scan**: Recursively find all data and document files
2. **OCR Processing**: Extract column descriptions from PDF/DOCX files
3. **Data Analysis**: Comprehensive analysis of CSV files
4. **Enhanced Mapping**: Combine documentation with pattern matching
5. **Quality Assessment**: Detect anomalies and generate recommendations

## Configuration

### Supported File Types
- **Data**: `.csv`, `.xlsx`, `.xls`, `.txt`
- **Documents**: `.pdf`, `.docx`, `.doc`

### Column Pattern Recognition
- Geographic identifiers: `STATEFP`, `COUNTYFP`, `TRACTCE`, `BLOCKCE`, `GEO_ID`
- Population: `POP`, `POPULATION`, `MALE`, `FEMALE`
- Economic: `MEDIAN_INCOME`, `INCOME`, `EMPLOYED`, `UNEMPLOYED`
- Housing: `HOUSING_UNITS`, `OCCUPIED`, `VACANT`
- Race/Ethnicity: `WHITE`, `BLACK`, `ASIAN`, `HISPANIC`

### OCR Settings
- Multiple extraction methods with fallback
- Configurable sample sizes
- Intelligent pattern matching for documentation

## Performance Tips

1. **Limit Scan Depth**: Use `max_depth` parameter for large directories
2. **Sample Sizes**: Adjust `sample_size` for large CSV files
3. **Document Caching**: Results are cached to avoid reprocessing
4. **Batch Processing**: Use `max_files` to limit initial analysis

## Troubleshooting

### OCR Libraries Not Available
```
OCR libraries not available: No module named 'PyPDF2'
```
**Solution**: Install required OCR dependencies (see Installation)

### Permission Errors
```
Permission denied accessing: /some/directory
```
**Solution**: Check file permissions or run with appropriate user privileges

### Memory Issues
**Solution**: Reduce `sample_size` and `max_files` parameters

### Tesseract Not Found
**Solution**: Install Tesseract OCR and ensure it's in your PATH

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For issues and questions:
1. Check this README for common solutions
2. Review the code comments for detailed explanations
3. Check the JSON output for diagnostic information