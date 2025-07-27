#!/usr/bin/env python3

import sys
sys.path.append('/opt/airflow/scripts')

from pyspark.sql import SparkSession
from common.spark_session import get_spark_session

def debug_clean_data():
    """Debug clean_stock_data issue"""
    spark = get_spark_session(SparkSession)
    
    try:
        # Check if bronze schema exists
        schemas = spark.sql("SHOW SCHEMAS").collect()
        print("Available schemas:")
        for schema in schemas:
            print(f"  - {schema[0]}")
        
        # Check if bronze.yfinance_raw table exists
        if spark.catalog.tableExists("bronze.yfinance_raw"):
            print("\n✅ Table bronze.yfinance_raw exists")
            
            # Get count
            count = spark.sql("SELECT COUNT(*) as count FROM bronze.yfinance_raw").collect()[0]['count']
            print(f"Record count: {count}")
            
            # Show sample data
            print("\nSample data:")
            spark.sql("SELECT * FROM bronze.yfinance_raw LIMIT 3").show()
            
        else:
            print("\n❌ Table bronze.yfinance_raw does not exist")
            
            # Try reading from Delta Lake path directly
            table_path = "s3a://lakehouse/bronze/yfinance/"
            print(f"Trying to read from Delta Lake path: {table_path}")
            
            try:
                df = spark.read.format("delta").load(table_path)
                count = df.count()
                print(f"✅ Delta Lake data found: {count} records")
                df.show(3)
                
                # Create the table
                print("Creating Hive table...")
                spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")
                spark.sql(f"""
                    CREATE TABLE bronze.yfinance_raw
                    USING DELTA
                    LOCATION '{table_path}'
                """)
                print("✅ Hive table created successfully")
                
            except Exception as e:
                print(f"❌ Failed to read from Delta Lake path: {str(e)}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
    finally:
        spark.stop()
    
    return 0

if __name__ == "__main__":
    sys.exit(debug_clean_data())