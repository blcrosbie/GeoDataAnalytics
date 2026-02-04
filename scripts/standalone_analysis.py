#!/usr/bin/env python3
"""
Enhanced Standalone Survey Data Analysis Script
Wide-scope analysis with column overlap, PDF mapping, and year-based filtering.
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple, Set, Optional

# Add workspace directory to path to import our modules
sys.path.append(str(Path(__file__).parent))

from process_survey_data import SurveyDataProcessor

def extract_years_from_path(file_path: str) -> Set[int]:
    """Extract years from file path and name."""
    years = set()
    path_str = str(file_path).upper()
    filename = Path(file_path).name.upper()
    
    # Common year patterns in census data
    year_patterns = [
        r'20(\d{2})',  # 20XX patterns
        r'19(\d{2})',  # 19XX patterns
        r'(\d{4})',    # 4-digit years
    ]
    
    # Check filename first
    for pattern in year_patterns:
        matches = re.findall(pattern, filename)
        for match in matches:
            year = int(match)
            if 1900 <= year <= 2030:  # Reasonable year range
                years.add(year)
    
    # Check full path if no years found in filename
    if not years:
        for pattern in year_patterns:
            matches = re.findall(pattern, path_str)
            for match in matches:
                year = int(match)
                if 1900 <= year <= 2030:
                    years.add(year)
    
    return years

def filter_files_by_year_range(files: List[Any], start_year: int, end_year: int) -> List[Any]:
    """Filter files by year range extracted from paths."""
    filtered_files = []
    
    for file_info in files:
        file_years = extract_years_from_path(file_info.path)
        
        # Include file if:
        # 1. It has years within the range, OR
        # 2. It has no years (assume it's relevant), OR  
        # 3. The file modification time is within range
        include_file = False
        
        if file_years:
            for year in file_years:
                if start_year <= year <= end_year:
                    include_file = True
                    break
        else:
            # Check modification time for files without explicit years
            mod_year = datetime.fromtimestamp(file_info.modified_time).year
            if start_year <= mod_year <= end_year:
                include_file = True
        
        if include_file:
            filtered_files.append(file_info)
    
    return filtered_files

def analyze_column_overlap(csv_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze column overlap across multiple CSV files."""
    column_files = defaultdict(list)  # column -> list of files
    file_columns = {}  # file -> set of columns
    
    for analysis in csv_analyses:
        file_path = analysis.get('file_path', '')
        file_name = Path(file_path).name
        columns = analysis.get('columns', [])
        
        file_columns[file_name] = set(columns)
        
        for col in columns:
            column_files[col].append(file_name)
    
    # Calculate overlap statistics
    overlap_analysis = {
        'total_unique_columns': len(column_files),
        'total_files': len(csv_analyses),
        'column_frequency': {},
        'high_overlap_columns': [],
        'unique_columns': [],
        'common_columns': [],
        'file_similarity_matrix': {}
    }
    
    # Column frequency analysis
    for col, files in column_files.items():
        freq = len(files)
        overlap_analysis['column_frequency'][col] = {
            'frequency': freq,
            'files': files,
            'percentage': (freq / len(csv_analyses)) * 100
        }
    
    # Find high overlap columns (present in 50%+ of files)
    overlap_analysis['high_overlap_columns'] = [
        (col, info['frequency'], info['files'])
        for col, info in overlap_analysis['column_frequency'].items()
        if info['frequency'] >= len(csv_analyses) * 0.5
    ]
    overlap_analysis['high_overlap_columns'].sort(key=lambda x: x[1], reverse=True)
    
    # Find unique columns (present in only 1 file)
    overlap_analysis['unique_columns'] = [
        (col, info['files'][0])
        for col, info in overlap_analysis['column_frequency'].items()
        if info['frequency'] == 1
    ]
    
    # Find common columns (present in 80%+ of files)
    overlap_analysis['common_columns'] = [
        col for col, info in overlap_analysis['column_frequency'].items()
        if info['frequency'] >= len(csv_analyses) * 0.8
    ]
    
    # File similarity matrix (Jaccard similarity)
    file_list = list(file_columns.keys())
    for i, file1 in enumerate(file_list):
        overlap_analysis['file_similarity_matrix'][file1] = {}
        for j, file2 in enumerate(file_list):
            if i != j:
                set1, set2 = file_columns[file1], file_columns[file2]
                intersection = len(set1.intersection(set2))
                union = len(set1.union(set2))
                similarity = (intersection / union) * 100 if union > 0 else 0
                overlap_analysis['file_similarity_matrix'][file1][file2] = round(similarity, 1)
    
    return overlap_analysis

def enhance_pdf_column_mapping(processor, documents: List[Any], csv_columns: Set[str]) -> Dict[str, Any]:
    """Enhanced PDF-to-CSV column mapping with better key:value extraction."""
    mapping_results = {
        'extracted_mappings': {},
        'confidence_scores': {},
        'unmatched_columns': [],
        'potential_matches': [],
        'mapping_statistics': {}
    }
    
    # Extract enhanced column descriptions from all documents
    doc_descriptions = processor.extract_column_descriptions_from_docs(documents)
    
    # Enhanced pattern matching for better column mapping
    enhanced_patterns = [
        # Standard census patterns
        r'([A-Z][A-Z0-9_]+)[\s:=-]+\s*([^.\n\r]+)',
        r'Variable\s+([A-Z][A-Z0-9_]+)[\s:=-]+\s*([^.\n\r]+)',
        r'Column\s+([A-Z][A-Z0-9_]+)[\s:=-]+\s*([^.\n\r]+)',
        r'([A-Z]\d{5}_\d{3}[A-Z])[\s:=-]+\s*([^.\n\r]+)',
        r'([A-Z]{2,}\d*)[\s:=-]+\s*([^.\n\r]+)',
        
        # Table-style patterns
        r'\|\s*([A-Z][A-Z0-9_]*)\s*\|\s*([^|]+)\s*\|',
        r'([A-Z][A-Z0-9_]*)\s*\|\s*([^|\n\r]+)',
        
        # Definition patterns
        r'([A-Z][A-Z0-9_]+)\s*-\s*Definition[:\s]*([^.\n\r]+)',
        r'([A-Z][A-Z0-9_]+)\s*means[:\s]*([^.\n\r]+)',
        r'([A-Z][A-Z0-9_]+)\s*represents[:\s]*([^.\n\r]+)',
        
        # Parentheses explanations
        r'([A-Z][A-Z0-9_]+)\s*\(([^)]+)\)',
        
        # Equals sign patterns
        r'([A-Z][A-Z0-9_]+)\s*=\s*([^.\n\r]+)',
        
        # Bullet/list patterns
        r'•\s*([A-Z][A-Z0-9_]+):\s*([^.\n\r]+)',
        r'-\s*([A-Z][A-Z0-9_]+):\s*([^.\n\r]+)',
        r'\*\s*([A-Z][A-Z0-9_]+):\s*([^.\n\r]+)',
    ]
    
    # Process all document text with enhanced patterns
    all_extracted = {}
    
    for doc_info in documents:
        if doc_info.path in processor.document_cache:
            text = processor.document_cache[doc_info.path]
        else:
            text = processor.extract_document_text(doc_info.path)
            processor.document_cache[doc_info.path] = text
        
        # Apply all patterns
        for pattern in enhanced_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for column, description in matches:
                column = column.upper().strip()
                description = re.sub(r'\s+', ' ', description.strip())
                description = description.rstrip('.')
                
                if len(column) >= 3 and len(description) > 5:
                    if column not in all_extracted:
                        all_extracted[column] = []
                    all_extracted[column].append(description)
    
    # Match extracted descriptions to CSV columns
    matched_columns = {}
    unmatched_columns = []
    
    for csv_col in csv_columns:
        csv_col_upper = csv_col.upper()
        best_match = None
        best_score = 0
        
        # Direct match
        if csv_col_upper in all_extracted:
            # Use the longest description for direct matches
            descriptions = all_extracted[csv_col_upper]
            best_desc = max(descriptions, key=len)
            best_match = best_desc
            best_score = 100
        
        # Partial match
        else:
            for extracted_col, descriptions in all_extracted.items():
                # Check if CSV column contains extracted pattern
                if extracted_col in csv_col_upper or csv_col_upper in extracted_col:
                    # Calculate similarity score
                    score = 0
                    if extracted_col in csv_col_upper:
                        score += 70
                    if csv_col_upper in extracted_col:
                        score += 50
                    
                    # Bonus for common prefixes/suffixes
                    if csv_col_upper.startswith(extracted_col[:3]):
                        score += 10
                    if csv_col_upper.endswith(extracted_col[-3:]):
                        score += 10
                    
                    if score > best_score:
                        best_score = score
                        best_match = max(descriptions, key=len)
        
        if best_match and best_score >= 60:
            matched_columns[csv_col] = {
                'description': best_match,
                'confidence': best_score,
                'source': 'extracted'
            }
        else:
            unmatched_columns.append(csv_col)
    
    mapping_results['extracted_mappings'] = matched_columns
    mapping_results['unmatched_columns'] = unmatched_columns
    mapping_results['confidence_scores'] = {
        col: info['confidence'] for col, info in matched_columns.items()
    }
    
    # Generate potential matches for unmatched columns
    for unmatched in unmatched_columns:
        potential = []
        for extracted_col, descriptions in all_extracted.items():
            # Calculate partial similarity
            similarity = 0
            for desc in descriptions:
                # Simple string similarity
                common_chars = set(unmatched.upper()) & set(extracted_col)
                if len(common_chars) > 3:
                    similarity = len(common_chars) / max(len(unmatched), len(extracted_col)) * 50
                    break
            
            if similarity > 20:
                potential.append({
                    'column': extracted_col,
                    'description': descriptions[0],
                    'similarity': similarity
                })
        
        if potential:
            potential.sort(key=lambda x: x['similarity'], reverse=True)
            mapping_results['potential_matches'].append({
                'csv_column': unmatched,
                'matches': potential[:3]
            })
    
    # Statistics
    mapping_results['mapping_statistics'] = {
        'total_csv_columns': len(csv_columns),
        'matched_columns': len(matched_columns),
        'unmatched_columns': len(unmatched_columns),
        'match_rate': round((len(matched_columns) / len(csv_columns)) * 100, 1) if csv_columns else 0,
        'high_confidence_matches': len([c for c, s in mapping_results['confidence_scores'].items() if s >= 80]),
        'average_confidence': round(sum(mapping_results['confidence_scores'].values()) / len(mapping_results['confidence_scores']), 1) if mapping_results['confidence_scores'] else 0
    }
    
    return mapping_results

def run_wide_scope_analysis(data_dir: Optional[str] = None, start_year: int = 2020, end_year: int = 2025, 
                          max_files: int = 50):
    """Run wide-scope analysis with enhanced features."""
    
    print(f"🔍 Starting WIDE SCOPE Survey Data Analysis ({start_year}-{end_year})")
    print("=" * 60)
    
    # Determine data directory
    if data_dir is None:
        current_file = Path(__file__).resolve()
        repo_root = current_file.parent.parent
        data_dir = str(repo_root / 'data')
    
    print(f"📁 Data Directory: {data_dir}")
    print(f"📅 Year Range: {start_year}-{end_year}")
    
    # Initialize processor
    processor = SurveyDataProcessor(data_dir)
    
    # Deep filesystem scan with year filtering
    print("\n🚀 Deep Filesystem Scan with Year Filtering...")
    found_files = processor.deep_scan_filesystem(max_depth=10)
    
    # Filter files by year range
    data_files = filter_files_by_year_range(found_files.get('data', []), start_year, end_year)
    document_files = filter_files_by_year_range(found_files.get('documents', []), start_year, end_year)
    
    print(f"📋 Year-Filtered Results:")
    print(f"   • Data files in range: {len(data_files)}")
    print(f"   • Document files in range: {len(document_files)}")
    print(f"   • Total files filtered: {len(found_files.get('data', [])) + len(found_files.get('documents', [])) - len(data_files) - len(document_files)}")
    
    # Limit files for analysis
    data_files_to_analyze = data_files[:max_files]
    document_files_to_analyze = document_files[:min(20, len(document_files))]  # Limit docs to 20
    
    print(f"📊 Analyzing {len(data_files_to_analyze)} data files and {len(document_files_to_analyze)} document files...")
    
    # Analyze CSV files
    csv_analyses = []
    all_columns = set()
    
    for i, file_info in enumerate(data_files_to_analyze):
        print(f"   Analyzing file {i+1}/{len(data_files_to_analyze)}: {Path(file_info.path).name}")
        analysis = processor.analyze_csv_structure(file_info.path, sample_size=1000)
        csv_analyses.append(analysis)
        all_columns.update(analysis.get('columns', []))
    
    print(f"\n📈 Column Overlap Analysis...")
    overlap_analysis = analyze_column_overlap(csv_analyses)
    
    print(f"\n📄 Enhanced PDF Column Mapping...")
    enhanced_mapping = enhance_pdf_column_mapping(processor, document_files_to_analyze, all_columns)
    
    # Compile comprehensive results
    results = {
        'analysis_metadata': {
            'timestamp': datetime.now().isoformat(),
            'year_range': f"{start_year}-{end_year}",
            'data_dir': data_dir,
            'total_files_scanned': len(data_files) + len(document_files),
            'files_analyzed': {
                'data_files': len(data_files_to_analyze),
                'document_files': len(document_files_to_analyze)
            }
        },
        'column_overlap_analysis': overlap_analysis,
        'enhanced_column_mapping': enhanced_mapping,
        'csv_analyses': csv_analyses[:5],  # Limit to 5 for JSON size
        'all_columns_count': len(all_columns) if csv_analyses else 0,
        'recommendations': []
    }
    
    # Display results
    print(f"\n📊 WIDE SCOPE ANALYSIS RESULTS")
    print("=" * 60)
    
    # Year filtering results
    analysis_meta = results['analysis_metadata']
    print(f"📅 Analysis Scope:")
    print(f"   • Year Range: {analysis_meta['year_range']}")
    print(f"   • Data Files Analyzed: {analysis_meta['files_analyzed']['data_files']}")
    print(f"   • Document Files Analyzed: {analysis_meta['files_analyzed']['document_files']}")
    print(f"   • Total Unique Columns: {analysis_meta.get('all_columns_count', 0)}")
    
    # Column overlap results
    overlap = results['column_overlap_analysis']
    print(f"\n🔗 Column Overlap Analysis:")
    print(f"   • Total Unique Columns: {overlap['total_unique_columns']}")
    print(f"   • Files Analyzed: {overlap['total_files']}")
    print(f"   • High Overlap Columns (50%+): {len(overlap['high_overlap_columns'])}")
    print(f"   • Common Columns (80%+): {len(overlap['common_columns'])}")
    print(f"   • Unique Columns (1 file only): {len(overlap['unique_columns'])}")
    
    if overlap['high_overlap_columns'][:10]:
        print(f"\n   📊 Top Overlap Columns:")
        for col, freq, files in overlap['high_overlap_columns'][:10]:
            print(f"      • {col}: {freq} files ({len(files)} listed)")
    
    # File similarity matrix (show top 5 files)
    sim_matrix = overlap['file_similarity_matrix']
    if sim_matrix:
        file_names = list(sim_matrix.keys())[:5]
        print(f"\n   📈 File Similarity Matrix (Top 5 Files):")
        print(f"      {'File':<30} {'Most Similar':<30} {'Similarity':<10}")
        for file1 in file_names:
            if file1 in sim_matrix:
                similarities = sim_matrix[file1]
                most_similar = max(similarities.items(), key=lambda x: x[1]) if similarities else ("N/A", 0)
                print(f"      {file1[:28]:<30} {most_similar[0][:28]:<30} {most_similar[1]:<10}%")
    
    # Enhanced mapping results
    mapping = results['enhanced_column_mapping']
    mapping_stats = mapping['mapping_statistics']
    print(f"\n📄 Enhanced PDF Column Mapping:")
    print(f"   • Total CSV Columns: {mapping_stats['total_csv_columns']}")
    print(f"   • Matched Columns: {mapping_stats['matched_columns']}")
    print(f"   • Unmatched Columns: {mapping_stats['unmatched_columns']}")
    print(f"   • Match Rate: {mapping_stats['match_rate']}%")
    print(f"   • High Confidence Matches: {mapping_stats['high_confidence_matches']}")
    print(f"   • Average Confidence: {mapping_stats['average_confidence']}")
    
    # Show best matched columns
    matched_cols = mapping['extracted_mappings']
    if matched_cols:
        high_conf_matches = [(col, info['description'], info['confidence']) 
                           for col, info in matched_cols.items() 
                           if info['confidence'] >= 80]
        high_conf_matches.sort(key=lambda x: x[2], reverse=True)
        
        if high_conf_matches[:15]:
            print(f"\n   🎯 High Confidence Matches (Top 15):")
            for col, desc, conf in high_conf_matches[:15]:
                print(f"      • {col} (Conf: {conf}%): {desc[:80]}...")
    
    # Show unmatched columns with potential matches
    potential_matches = mapping['potential_matches']
    if potential_matches[:5]:
        print(f"\n   🔍 Potential Matches for Unmatched Columns:")
        for pot in potential_matches[:5]:
            csv_col = pot['csv_column']
            best_match = pot['matches'][0] if pot['matches'] else None
            if best_match:
                print(f"      • {csv_col} → {best_match['column']} (Sim: {best_match['similarity']:.1f}%)")
    
    # CSV file summaries
    print(f"\n📈 CSV File Analysis Summary:")
    for i, analysis in enumerate(csv_analyses[:3]):
        file_name = Path(analysis.get('file_path', '')).name
        print(f"   📋 {i+1}. {file_name}")
        print(f"      • Rows: {analysis.get('total_rows', 0):,}")
        print(f"      • Columns: {analysis.get('total_columns', 0)}")
        print(f"      • File size: {analysis.get('file_size', 0):,} bytes")
        
        # Data quality summary
        data_quality = analysis.get('data_quality', {})
        if data_quality:
            completeness = data_quality.get('completeness', {})
            if completeness:
                avg_complete = sum(completeness.values()) / len(completeness)
                print(f"      • Avg data completeness: {avg_complete:.1f}%")
    
    # Generate recommendations
    recommendations = []
    
    if mapping_stats['match_rate'] < 50:
        recommendations.append("Consider adding more documentation files to improve column mapping")
    
    if overlap['total_unique_columns'] > overlap['total_files'] * 50:
        recommendations.append("High column diversity detected - consider standardization across datasets")
    
    if len(overlap['common_columns']) < 5:
        recommendations.append("Low column overlap detected - datasets may be from different survey types")
    
    if mapping_stats['high_confidence_matches'] < mapping_stats['matched_columns'] * 0.5:
        recommendations.append("Many low-confidence matches - review document quality and patterns")
    
    results['recommendations'] = recommendations
    
    if recommendations:
        print(f"\n💡 Recommendations:")
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
    
    # Save comprehensive results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f"wide_scope_analysis_{start_year}_{end_year}_{timestamp}.json"
    
    print(f"\n💾 Saving comprehensive results to: {results_file}")
    
    try:
        # Convert results to JSON-serializable format
        def make_json_serializable(obj):
            if isinstance(obj, dict):
                return {k: make_json_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_json_serializable(item) for item in obj]
            elif isinstance(obj, (str, int, float, bool)) or obj is None:
                return obj
            else:
                return str(obj)
        
        json_results = make_json_serializable(results)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(json_results, f, indent=2, default=str)
            
        # Also create a summary CSV file
        summary_file = f"column_overlap_summary_{start_year}_{end_year}_{timestamp}.csv"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("Column,Frequency,Percentage,Files\n")
            for col, info in overlap['column_frequency'].items():
                files_str = "; ".join(info['files'][:5])  # Limit to 5 files per row
                f.write(f"{col},{info['frequency']},{info['percentage']:.1f},\"{files_str}\"\n")
        
        print(f"✅ Analysis complete! Results saved to:")
        print(f"   📄 {results_file}")
        print(f"   📊 {summary_file}")
        
    except Exception as e:
        print(f"⚠️  Error saving results: {e}")
    
    return results

def run_standalone_analysis(data_dir: Optional[str] = None, max_files: int = 5):
    """Legacy function - redirects to wide scope analysis."""
    return run_wide_scope_analysis(data_dir, 2020, 2025, max_files)

def quick_data_quality_check(csv_path: str):
    """Quick quality check for a single CSV file."""
    print(f"🔍 Quick Quality Check: {Path(csv_path).name}")
    
    processor = SurveyDataProcessor(str(Path(csv_path).parent.parent))
    analysis = processor.analyze_csv_structure(csv_path, sample_size=500)
    
    print(f"📊 Quality Metrics:")
    print(f"   • File size: {analysis.get('file_size', 0):,} bytes")
    print(f"   • Total rows: {analysis.get('total_rows', 0):,}")
    print(f"   • Total columns: {analysis.get('total_columns', 0)}")
    
    missing_values = analysis.get('missing_values', {})
    if missing_values:
        high_missing = [col for col, pct in missing_values.items() if pct > 20]
        if high_missing:
            print(f"   ⚠️  Columns with >20% missing values: {len(high_missing)}")
            for col in high_missing[:3]:
                print(f"      - {col}: {missing_values[col]:.1f}% missing")
    
    data_quality = analysis.get('data_quality', {})
    completeness = data_quality.get('completeness', {})
    if completeness:
        avg_complete = sum(completeness.values()) / len(completeness)
        print(f"   ✅ Average data completeness: {avg_complete:.1f}%")
    
    return analysis

def create_mapping_visualization(results: Dict[str, Any], timestamp: str):
    """Create visualization files for column mappings."""
    try:
        # Create detailed CSV mapping file
        mapping_file = f"detailed_column_mapping_{timestamp}.csv"
        enhanced_mapping = results.get('enhanced_column_mapping', {})
        
        with open(mapping_file, 'w', encoding='utf-8') as f:
            f.write("CSV_Column,Description,Confidence,Source,Match_Type\n")
            
            # Matched columns
            for csv_col, info in enhanced_mapping.get('extracted_mappings', {}).items():
                f.write(f"{csv_col},\"{info['description']}\",{info['confidence']},{info['source']},Matched\n")
            
            # Unmatched columns with potential matches
            for pot in enhanced_mapping.get('potential_matches', []):
                csv_col = pot['csv_column']
                for match in pot['matches']:
                    f.write(f"{csv_col},\"{match['description']}\",{match['similarity']:.1f},Potential,Potential\n")
        
        # Create file similarity matrix CSV
        overlap = results.get('column_overlap_analysis', {})
        sim_matrix = overlap.get('file_similarity_matrix', {})
        sim_file = None
        
        if sim_matrix:
            sim_file = f"file_similarity_matrix_{timestamp}.csv"
            files = list(sim_matrix.keys())
            
            with open(sim_file, 'w', encoding='utf-8') as f:
                f.write("File1,File2,Similarity_Percent\n")
                for file1, similarities in sim_matrix.items():
                    for file2, similarity in similarities.items():
                        f.write(f"{file1},{file2},{similarity}\n")
        
        # Create column frequency analysis CSV
        freq_file = f"column_frequency_analysis_{timestamp}.csv"
        col_freq = overlap.get('column_frequency', {})
        
        with open(freq_file, 'w', encoding='utf-8') as f:
            f.write("Column,Frequency,Percentage,Files_Count,Sample_Files\n")
            for col, info in sorted(col_freq.items(), key=lambda x: x[1]['frequency'], reverse=True):
                files_list = info['files'][:3]  # Limit to 3 files
                files_str = "; ".join(files_list)
                f.write(f"{col},{info['frequency']},{info['percentage']:.1f},{len(info['files'])},\"{files_str}\"\n")
        
        print(f"📊 Visualization files created:")
        print(f"   📄 {mapping_file}")
        if 'sim_file' in locals():
            print(f"   📈 {sim_file}")
        print(f"   📊 {freq_file}")
        
    except Exception as e:
        print(f"⚠️  Error creating visualization files: {e}")

def main():
    """Main function for wide scope analysis."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Wide Scope Survey Data Analysis')
    parser.add_argument('--data-dir', type=str, help='Data directory path')
    parser.add_argument('--csv-file', type=str, help='Single CSV file for quick quality check')
    parser.add_argument('--max-files', type=int, default=50, help='Maximum data files to analyze (default: 50)')
    parser.add_argument('--start-year', type=int, default=2020, help='Start year for filtering (default: 2020)')
    parser.add_argument('--end-year', type=int, default=2025, help='End year for filtering (default: 2025)')
    parser.add_argument('--wide-scope', action='store_true', help='Run wide scope analysis (default behavior)')
    
    args = parser.parse_args()
    
    if args.csv_file:
        quick_data_quality_check(args.csv_file)
    else:
        # Run wide scope analysis with year filtering
        results = run_wide_scope_analysis(
            args.data_dir, 
            args.start_year, 
            args.end_year, 
            args.max_files
        )
        
        # Create visualization files
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        create_mapping_visualization(results, timestamp)

if __name__ == "__main__":
    main()