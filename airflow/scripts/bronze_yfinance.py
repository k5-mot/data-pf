#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
from pyspark.sql import SparkSession

from spark_session import get_spark_session


spark = get_spark_session(SparkSession)

def main():
    # 1. yfinanceで株価データ取得
    data = yf.download('AAPL', start='2024-01-01', end='2024-01-31', auto_adjust=False)
    data.reset_index(inplace=True)

    # 列名を平坦化（multi-level columnを処理）
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] if col[1] == '' else col[0] for col in data.columns]

    # データの列名とサイズを確認
    print(f"Data columns: {data.columns.tolist()}")
    print(f"Data shape: {data.shape}")

    # 2. Sparkセッション作成（既に設定済みの場合）
    # spark = SparkSession.builder.getOrCreate()

    # 3. pandasからSparkへの変換（自動スキーマ推論）
    sdf = spark.createDataFrame(data)

    # 4. Delta Lake形式でMinIOに保存
    sdf.write.format("delta").mode("overwrite").save("s3a://bronze/yfinance_aapl")

    # 5. Hiveメタストア登録（必要なら）
    # spark.sql("CREATE TABLE IF NOT EXISTS bronze.yfinance_aapl USING DELTA LOCATION 's3a://bronze/yfinance_aapl'")

    spark.stop()
    print("YFinance data ingestion completed successfully!")

if __name__ == "__main__":
    main()
