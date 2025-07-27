#!/usr/bin/env python3

import sys
sys.path.append('/opt/airflow/scripts')

from pyspark.sql import SparkSession
from common.spark_session import get_spark_session

def create_hive_table():
    """Create Hive table pointing to existing Delta Lake data"""
    spark = get_spark_session(SparkSession)
    
    try:
        # Create bronze schema
        spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")
        print("Bronze schema created/verified")
        
        # Drop existing table if exists
        spark.sql("DROP TABLE IF EXISTS bronze.yfinance_raw")
        print("Dropped existing table if any")
        
        # Create table pointing to Delta Lake path
        table_path = "s3a://lakehouse/bronze/yfinance/"
        spark.sql(f"""
            CREATE TABLE bronze.yfinance_raw
            USING DELTA
            LOCATION '{table_path}'
        """)
        print(f"Created Hive table bronze.yfinance_raw pointing to {table_path}")
        
        # Verify table creation
        result = spark.sql("SELECT COUNT(*) as count FROM bronze.yfinance_raw")
        result.show()
        
        # Show sample data
        sample = spark.sql("SELECT * FROM bronze.yfinance_raw LIMIT 5")
        sample.show()
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
    finally:
        spark.stop()
    
    return 0

if __name__ == "__main__":
    sys.exit(create_hive_table())