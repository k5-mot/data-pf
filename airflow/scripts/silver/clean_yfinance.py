#!/usr/bin/env python3
"""Silver層: 株価データクリーニングスクリプト

Bronze層の生データをクリーニングし、品質チェック後にSilver層に保存

Usage:
    spark-submit clean_stock_data.py --input_table bronze.yfinance_raw --output_table silver.stock_prices_clean --quality_threshold 0.8
"""

import argparse
import logging

# 既存のspark_session.pyとDelta Lake共通ライブラリを使用
import os
import sys
from datetime import datetime
from typing import Any, Dict, Tuple

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import abs as spark_abs
from pyspark.sql.functions import (
    array,
    avg,
    col,
    count,
    current_timestamp,
    date_format,
    dayofmonth,
    explode,
    isnan,
    isnull,
    lit,
    monotonically_increasing_id,
    month,
    percentile_approx,
    regexp_replace,
    split,
    stddev,
    struct,
    trim,
    upper,
    when,
    year,
)
from pyspark.sql.types import (
    ArrayType,
    DateType,
    DecimalType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

sys.path.append("/opt/airflow/scripts")
from common.delta_utils import read_from_delta_table, write_to_delta_table

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def define_clean_stock_schema() -> StructType:
    """クリーン株価データのスキーマ定義"""
    return StructType(
        [
            StructField("symbol", StringType(), False),
            StructField("trade_date", DateType(), False),
            StructField("open_price", DecimalType(10, 2), True),
            StructField("high_price", DecimalType(10, 2), True),
            StructField("low_price", DecimalType(10, 2), True),
            StructField("close_price", DecimalType(10, 2), True),
            StructField("adjusted_close", DecimalType(10, 2), True),
            StructField("volume", LongType(), True),
            StructField("split_ratio", DecimalType(10, 6), True),
            StructField("dividend_amount", DecimalType(10, 4), True),
            StructField("currency", StringType(), True),
            StructField("exchange", StringType(), True),
            StructField("data_quality_score", DoubleType(), True),
            StructField("anomaly_flags", ArrayType(StringType()), True),
            StructField("validation_timestamp", TimestampType(), False),
            StructField("source_record_id", StringType(), True),
        ]
    )


def perform_basic_data_quality_checks(df: DataFrame) -> dict[str, Any]:
    """基本的なデータ品質チェック

    Args:
        df: チェック対象DataFrame

    Returns:
        Dict: 品質メトリクス
    """
    logger.info("Performing basic data quality checks...")

    total_count = df.count()

    if total_count == 0:
        return {"total_records": 0, "quality_score": 0.0}

    # 各カラムの欠損値率
    null_counts = {}
    numeric_columns = ["open", "high", "low", "close", "adj_close", "volume"]

    for col_name in numeric_columns:
        null_count = df.filter(
            col(col_name).isNull() | isnan(col(col_name)) | (col(col_name) <= 0)
        ).count()
        null_counts[col_name] = null_count / total_count

    # 論理整合性チェック
    logical_errors = df.filter(
        (col("high") < col("low"))
        | (col("high") < col("open"))
        | (col("high") < col("close"))
        | (col("low") > col("open"))
        | (col("low") > col("close"))
    ).count()

    logical_error_rate = logical_errors / total_count

    # 重複レコードチェック
    unique_count = df.select("symbol", "date").distinct().count()
    duplicate_rate = (total_count - unique_count) / total_count

    # 全体品質スコア計算
    avg_null_rate = sum(null_counts.values()) / len(null_counts)
    quality_score = max(0.0, 1.0 - avg_null_rate - logical_error_rate - duplicate_rate)

    metrics = {
        "total_records": total_count,
        "null_rates": null_counts,
        "logical_error_rate": logical_error_rate,
        "duplicate_rate": duplicate_rate,
        "quality_score": quality_score,
    }

    logger.info(f"Quality metrics: {metrics}")
    return metrics


def detect_anomalies(df: DataFrame) -> DataFrame:
    """統計的異常値検出（簡略化版）

    Args:
        df: 検出対象DataFrame

    Returns:
        DataFrame: 異常値フラグ付きDataFrame
    """
    logger.info("Detecting anomalies (simplified)...")

    # 簡単な異常値フラグを初期化（空の配列）
    df = df.withColumn("anomaly_flags", array())

    # 基本的な異常値のみ検出（負の価格など）
    df = df.withColumn(
        "anomaly_flags",
        when(
            (col("open") <= 0)
            | (col("high") <= 0)
            | (col("low") <= 0)
            | (col("close") <= 0)
            | (col("high") < col("low")),
            array(lit("invalid_price")),
        ).otherwise(array()),
    )

    logger.info("Anomaly detection completed (simplified)")
    return df


def apply_data_cleaning_rules(df: DataFrame) -> DataFrame:
    """データクリーニングルール適用

    Args:
        df: クリーニング対象DataFrame

    Returns:
        DataFrame: クリーニング済みDataFrame
    """
    logger.info("Applying data cleaning rules...")

    # 1. 価格データの論理整合性修正
    df = df.withColumn(
        "high",
        when(col("high") < col("low"), col("low"))
        .when(col("high") < col("open"), col("open"))
        .when(col("high") < col("close"), col("close"))
        .otherwise(col("high")),
    )

    # 2. ゼロ・負の値を欠損値に変換
    price_columns = ["open", "high", "low", "close", "adj_close"]
    for col_name in price_columns:
        df = df.withColumn(
            col_name, when(col(col_name) <= 0, None).otherwise(col(col_name))
        )

    # 3. 出来高のゼロ値は妥当（祝日等）なのでそのまま保持
    df = df.withColumn("volume", when(col("volume") < 0, 0).otherwise(col("volume")))

    # 4. 分割・配当情報のクリーニング
    df = df.withColumn(
        "splits",
        when(col("splits").isNull(), 1.0)
        .when(col("splits") <= 0, 1.0)
        .otherwise(col("splits")),
    )

    df = df.withColumn(
        "dividends",
        when(col("dividends").isNull(), 0.0)
        .when(col("dividends") < 0, 0.0)
        .otherwise(col("dividends")),
    )

    return df


def standardize_metadata(df: DataFrame) -> DataFrame:
    """メタデータ標準化

    Args:
        df: 標準化対象DataFrame

    Returns:
        DataFrame: 標準化済みDataFrame
    """
    logger.info("Standardizing metadata...")

    # 通貨情報推定（銘柄コードから）
    df = df.withColumn(
        "currency",
        when(col("symbol").endswith(".T"), "JPY")
        .when(col("symbol").endswith(".HK"), "HKD")
        .when(col("symbol").endswith(".L"), "GBP")
        .otherwise("USD"),
    )

    # 取引所情報推定
    df = df.withColumn(
        "exchange",
        when(col("symbol").endswith(".T"), "TSE")
        .when(col("symbol").endswith(".HK"), "HKEX")
        .when(col("symbol").endswith(".L"), "LSE")
        .otherwise("NASDAQ"),
    )

    return df


def calculate_quality_score(df: DataFrame) -> DataFrame:
    """各レコードの品質スコア計算

    Args:
        df: スコア計算対象DataFrame

    Returns:
        DataFrame: 品質スコア付きDataFrame
    """
    logger.info("Calculating quality scores...")

    # 各チェック項目の重み
    weights = {
        "price_completeness": 0.4,  # 価格データ完整性
        "volume_completeness": 0.2,  # 出来高完整性
        "logical_consistency": 0.3,  # 論理整合性
        "anomaly_penalty": 0.1,  # 異常値ペナルティ
    }

    # 価格データ完整性（主要価格フィールドの欠損なし）
    price_complete = (
        col("open").isNotNull()
        & col("high").isNotNull()
        & col("low").isNotNull()
        & col("close").isNotNull()
    ).cast("double")

    # 出来高データ完整性
    volume_complete = col("volume").isNotNull().cast("double")

    # 論理整合性（high >= low, high >= open, high >= close, low <= open, low <= close）
    logical_consistent = (
        (col("high") >= col("low"))
        & (col("high") >= col("open"))
        & (col("high") >= col("close"))
        & (col("low") <= col("open"))
        & (col("low") <= col("close"))
    ).cast("double")

    # 異常値ペナルティ（簡略化）
    anomaly_penalty = when(col("anomaly_flags").getItem(0).isNotNull(), 0.5).otherwise(
        1.0
    )

    # 総合品質スコア
    quality_score = (
        price_complete * weights["price_completeness"]
        + volume_complete * weights["volume_completeness"]
        + logical_consistent * weights["logical_consistency"]
        + anomaly_penalty * weights["anomaly_penalty"]
    )

    df = df.withColumn("data_quality_score", quality_score)

    return df


def transform_to_silver_schema(df: DataFrame) -> DataFrame:
    """Silver層スキーマに変換

    Args:
        df: 変換対象DataFrame

    Returns:
        DataFrame: Silver層スキーマのDataFrame
    """
    logger.info("Transforming to silver schema...")

    # カラム名変更・型変換
    silver_df = df.select(
        col("symbol"),
        col("date").alias("trade_date"),
        col("open").cast(DecimalType(10, 2)).alias("open_price"),
        col("high").cast(DecimalType(10, 2)).alias("high_price"),
        col("low").cast(DecimalType(10, 2)).alias("low_price"),
        col("close").cast(DecimalType(10, 2)).alias("close_price"),
        col("adj_close").cast(DecimalType(10, 2)).alias("adjusted_close"),
        col("volume"),
        col("splits").cast(DecimalType(10, 6)).alias("split_ratio"),
        col("dividends").cast(DecimalType(10, 4)).alias("dividend_amount"),
        col("currency"),
        col("exchange"),
        col("data_quality_score"),
        col("anomaly_flags"),
        current_timestamp().alias("validation_timestamp"),
        col("source_file").alias("source_record_id"),
    )

    return silver_df


def save_to_silver_table(spark: SparkSession, df: DataFrame, table_name: str) -> bool:
    """Silver層テーブルに保存

    Args:
        spark: SparkSession
        df: 保存するDataFrame
        table_name: 保存先テーブル名

    Returns:
        bool: 保存成功可否
    """
    try:
        if df.count() == 0:
            logger.warning("DataFrame is empty, skipping save")
            return False

        # パーティションカラム追加
        df_with_partitions = df.withColumn("year", year("trade_date")).withColumn(
            "month", month("trade_date")
        )

        # Delta Lake共通ライブラリを使用
        table_path = "s3a://lakehouse/silver/stock_prices/"

        return write_to_delta_table(
            df=df_with_partitions,
            table_name=table_name,
            table_path=table_path,
            mode="merge",
            partition_cols=["year", "month", "symbol"],
            merge_keys=["symbol", "trade_date"],
            spark=spark,
        )

    except Exception as e:
        logger.error(f"Error saving to silver table: {e!s}")
        return False


def create_silver_schema(spark: SparkSession):
    """Silver スキーマ作成"""
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS silver")
        logger.info("Silver schema created/verified")
    except Exception as e:
        logger.error(f"Error creating silver schema: {e!s}")


def create_bronze_schema(spark: SparkSession):
    """Bronze スキーマ作成"""
    try:
        spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")
        logger.info("Bronze schema created/verified")
    except Exception as e:
        logger.error(f"Error creating bronze schema: {e!s}")


def main() -> int:
    """メイン処理."""
    # 引数を取得.
    parser = argparse.ArgumentParser(description="Stock Data Cleaning")
    parser.add_argument("--input_table", required=True, help="入力テーブル名")
    parser.add_argument("--output_table", required=True, help="出力テーブル名")
    parser.add_argument(
        "--quality_threshold",
        type=float,
        default=0.8,
        help="品質閾値 (デフォルト: 0.8)",
    )
    args = parser.parse_args()

    # 引数を解析.
    input_table = str(args.input_table)
    output_table = str(args.output_table)
    quality_threshold = str(args.quality_threshold)

    # Sparkセッションを取得.
    spark = SparkSession.builder.getOrCreate()

    try:
        # Bronzeレイヤのテーブルを存在確認.
        if not spark.catalog.tableExists(input_table):
            logger.error(
                'Table "%s" does not exist.',
                input_table,
            )
            return 1

        bronze_df = read_from_delta_table(input_table, spark)

        if bronze_df is None:
            logger.error(f"Failed to read data from {args.input_table}")
            return 1

        # データ品質チェック
        quality_metrics = perform_basic_data_quality_checks(bronze_df)

        if quality_metrics["quality_score"] < args.quality_threshold:
            logger.warning(
                f"Data quality score {quality_metrics['quality_score']:.3f} below threshold {args.quality_threshold}"
            )

        # データクリーニング実行
        cleaned_df = apply_data_cleaning_rules(bronze_df)

        # 異常値検出
        anomaly_df = detect_anomalies(cleaned_df)

        # メタデータ標準化
        standardized_df = standardize_metadata(anomaly_df)

        # 品質スコア計算
        scored_df = calculate_quality_score(standardized_df)

        # Silver層スキーマに変換
        silver_df = transform_to_silver_schema(scored_df)

        # 品質フィルタリング（必要に応じて）
        filtered_df = silver_df.filter(
            col("data_quality_score") >= args.quality_threshold
        )

        logger.info(f"Records after quality filtering: {filtered_df.count()}")

        # Silver層テーブルに保存
        if save_to_silver_table(spark, filtered_df, args.output_table):
            # 結果統計表示
            result_stats = spark.sql(f"""
                SELECT
                    symbol,
                    COUNT(*) as record_count,
                    AVG(data_quality_score) as avg_quality_score,
                    MIN(trade_date) as min_date,
                    MAX(trade_date) as max_date
                FROM {args.output_table}
                GROUP BY symbol
                ORDER BY symbol
            """)

            logger.info("Silver table statistics:")
            result_stats.show()

            return 0
        logger.error("Failed to save to silver table")
        return 1

    except Exception as e:
        logger.error(f"Fatal error in cleaning process: {e!s}")
        return 1

    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
