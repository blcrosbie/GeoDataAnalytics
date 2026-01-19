# Database Transfer Script

This script transfers data from a source PostgreSQL database to a target PostgreSQL database for the GeoDataAnalytics project.

## Setup

1. Copy the environment template:
```bash
cp .env.example .env
```

2. Edit `.env` with your database connection details:
   - **Source**: Remote database to transfer FROM
   - **Target**: Local database (port 5432) to transfer TO

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the transfer script:
```bash
python transfer_data.py
```

The script will:
- Test connections to both databases
- Transfer data in batches for the 3 main tables: `borders`, `hexes`, `hexes_borders`
- Clear target tables before transfer
- Show progress during transfer
- Handle dependencies in correct order

## Tables Transferred

1. `borders` - Geographic border data
2. `hexes` - Hexagonal grid data with metadata
3. `hexes_borders` - Relationship table between hexes and borders