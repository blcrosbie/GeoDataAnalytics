FROM postgis/postgis:15-3.3

# Install additional dependencies
RUN apt-get update && apt-get install -y \
    postgresql-contrib \
    postgresql-15-pgrouting \
    postgresql-15-pointcloud \
    postgresql-15-hypopg \
    curl \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for PostGIS functions
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    && pip3 install \
    pandas \
    numpy \
    geopandas \
    shapely \
    fiona \
    psycopg2 \
    && rm -rf /var/lib/apt/lists/*

# Create custom directories
RUN mkdir -p /docker-entrypoint-initdb.d/custom \
    /var/lib/postgresql/data/backups \
    /var/lib/postgresql/data/logs

# Copy custom initialization scripts
COPY init.sql /docker-entrypoint-initdb.d/
COPY custom_functions.sql /docker-entrypoint-initdb.d/custom/

# Set permissions
RUN chmod +x /docker-entrypoint-initdb.d/*.sql

# Configure PostgreSQL for performance
RUN echo "shared_preload_libraries = 'pg_stat_statements,auto_explain'" >> /usr/share/postgresql/15/postgresql.conf.sample \
    && echo "pg_stat_statements.track = ALL" >> /usr/share/postgresql/15/postgresql.conf.sample \
    && echo "auto_explain.log_min_duration = 1000" >> /usr/share/postgresql/15/postgresql.conf.sample

# Expose ports for additional services
EXPOSE 5432

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pg_isready -U postgres -d geodata_analytics

# Set default user
USER postgres

# Set working directory
WORKDIR /var/lib/postgresql/data