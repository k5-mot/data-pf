#!/usr/bin/env python3
"""Delta Lake 操作共通ライブラリ.

Delta Lakeテーブルの作成・読み込み・書き込み・最適化を行う共通関数

作成者: Data Engineering Team
作成日: 2025-07-27
"""

import logging

from delta.tables import DeltaTable
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, current_timestamp

logger = logging.getLogger(__name__)


def write_to_delta_table(
    df: DataFrame,
    table_name: str,
    table_path: str,
    mode: str = "append",
    partition_cols: list[str] | None = None,
    merge_keys: list[str] | None = None,
    spark: SparkSession | None = None,
) -> bool:
    """Delta Lakeテーブルへの書き込み.

    Args:
        df: 書き込むDataFrame
        table_name: テーブル名 (例: "bronze.yfinance_raw")
        table_path: S3パス (例: "s3a://lakehouse/bronze/yfinance/")
        mode: 書き込みモード ("append", "overwrite", "merge")
        partition_cols: パーティションカラムリスト
        merge_keys: マージキー（mode="merge"時に使用）
        spark: SparkSession（省略時は現在のセッション使用）

    Returns:
        bool: 書き込み成功可否
    """
    try:
        if spark is None:
            spark = SparkSession.getActiveSession()

        if df.count() == 0:
            logger.warning(f"Empty DataFrame, skipping write to {table_name}")
            return False

        logger.info(f"Writing {df.count()} records to {table_name} (mode: {mode})")

        # 書き込み準備
        writer = df.write.format("delta")

        if partition_cols:
            writer = writer.partitionBy(*partition_cols)

        # モード別処理
        if mode == "merge" and merge_keys:
            return _merge_delta_table(df, table_name, table_path, merge_keys, spark)
        # 通常の書き込み
        logger.info(f"Writing to Delta table: {table_name}")
        writer.mode(mode).save(table_path)

        logger.info(f"Successfully wrote to {table_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to write to Delta table {table_name}: {e!s}")
        return False


def _merge_delta_table(
    source_df: DataFrame,
    table_name: str,
    table_path: str,
    merge_keys: list[str],
    spark: SparkSession,
) -> bool:
    """Delta Lakeテーブルへのマージ操作

    Args:
        source_df: ソースDataFrame
        table_name: ターゲットテーブル名
        table_path: テーブルパス
        merge_keys: マージキー
        spark: SparkSession

    Returns:
        bool: マージ成功可否
    """
    try:
        # ターゲットテーブルが存在しない場合は新規作成
        if not spark.catalog.tableExists(table_name):
            logger.info(f"Target table {table_name} does not exist, creating new table")
            source_df.write.format("delta").option("path", table_path).saveAsTable(
                table_name
            )
            return True

        # Delta Table取得
        delta_table = DeltaTable.forName(spark, table_name)

        # マージ条件構築
        merge_condition = " AND ".join(
            [f"target.{key} = source.{key}" for key in merge_keys]
        )

        # マージ実行
        (
            delta_table.alias("target")
            .merge(source_df.alias("source"), merge_condition)
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )

        logger.info(f"Successfully merged data into {table_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to merge Delta table {table_name}: {e!s}")
        return False


def read_from_delta_table(
    table_name: str,
    spark: SparkSession | None = None,
    date_filter: dict[str, any] | None = None,
    columns: list[str] | None = None,
) -> DataFrame | None:
    """Delta Lakeテーブルからの読み込み

    Args:
        table_name: テーブル名
        spark: SparkSession
        date_filter: 日付フィルタ辞書 {"column": "date", "start": "2025-01-01", "end": "2025-01-31"}
        columns: 選択カラムリスト

    Returns:
        DataFrame: 読み込んだデータ（失敗時はNone）
    """
    try:
        if spark is None:
            spark = SparkSession.getActiveSession()

        logger.info(f"Reading from Delta table: {table_name}")

        # テーブル存在確認
        if not spark.catalog.tableExists(table_name):
            logger.error(f"Table {table_name} does not exist")
            return None

        # データ読み込み
        df = spark.table(table_name)

        # カラム選択
        if columns:
            df = df.select(*columns)

        # 日付フィルタ適用
        if date_filter:
            date_col = date_filter.get("column", "date")
            start_date = date_filter.get("start")
            end_date = date_filter.get("end")

            if start_date:
                df = df.filter(col(date_col) >= start_date)
            if end_date:
                df = df.filter(col(date_col) <= end_date)

        record_count = df.count()
        logger.info(f"Successfully read {record_count} records from {table_name}")

        return df

    except Exception as e:
        logger.error(f"Failed to read from Delta table {table_name}: {e!s}")
        return None


def optimize_delta_table(
    table_name: str,
    spark: SparkSession | None = None,
    vacuum_hours: int = 168,  # 7 days default
) -> bool:
    """Delta Lakeテーブルの最適化

    Args:
        table_name: テーブル名
        spark: SparkSession
        vacuum_hours: VACUUM保持時間（時間単位）

    Returns:
        bool: 最適化成功可否
    """
    try:
        if spark is None:
            spark = SparkSession.getActiveSession()

        logger.info(f"Optimizing Delta table: {table_name}")

        # OPTIMIZE実行
        spark.sql(f"OPTIMIZE {table_name}")
        logger.info(f"OPTIMIZE completed for {table_name}")

        # VACUUM実行（古いファイル削除）
        spark.sql(f"VACUUM {table_name} RETAIN {vacuum_hours} HOURS")
        logger.info(
            f"VACUUM completed for {table_name} (retained {vacuum_hours} hours)"
        )

        return True

    except Exception as e:
        logger.error(f"Failed to optimize Delta table {table_name}: {e!s}")
        return False


def get_delta_table_info(
    table_name: str, spark: SparkSession | None = None
) -> dict[str, any] | None:
    """Delta Lakeテーブル情報取得

    Args:
        table_name: テーブル名
        spark: SparkSession

    Returns:
        Dict: テーブル情報（失敗時はNone）
    """
    try:
        if spark is None:
            spark = SparkSession.getActiveSession()

        # テーブル詳細情報取得
        table_detail = spark.sql(f"DESCRIBE DETAIL {table_name}").collect()[0]

        # テーブル統計情報取得
        table_stats = spark.sql(f"DESCRIBE TABLE {table_name}").collect()

        # レコード数取得
        record_count = spark.table(table_name).count()

        info = {
            "table_name": table_name,
            "format": table_detail["format"],
            "location": table_detail["location"],
            "created_at": table_detail["createdAt"],
            "last_modified": table_detail["lastModified"],
            "size_in_bytes": table_detail["sizeInBytes"],
            "num_files": table_detail["numFiles"],
            "record_count": record_count,
            "columns": [
                row["col_name"] for row in table_stats if row["col_name"] != ""
            ],
        }

        logger.info(f"Retrieved info for table {table_name}: {record_count} records")
        return info

    except Exception as e:
        logger.error(f"Failed to get info for Delta table {table_name}: {e!s}")
        return None


def create_delta_table_if_not_exists(
    spark: SparkSession,
    table_name: str,
    table_path: str,
    schema: str,
    partition_cols: list[str] | None = None,
) -> bool:
    """Delta Lakeテーブルが存在しない場合に作成

    Args:
        spark: SparkSession
        table_name: テーブル名
        table_path: S3パス
        schema: テーブルスキーマ（SQL DDL形式）
        partition_cols: パーティションカラム

    Returns:
        bool: 作成成功可否
    """
    try:
        if spark.catalog.tableExists(table_name):
            logger.info(f"Table {table_name} already exists")
            return True

        logger.info(f"Creating Delta table: {table_name}")

        # DDL構築
        partition_clause = ""
        if partition_cols:
            partition_clause = f"PARTITIONED BY ({', '.join(partition_cols)})"

        ddl = f"""
        CREATE TABLE {table_name} (
            {schema}
        ) USING DELTA
        LOCATION '{table_path}'
        {partition_clause}
        """

        spark.sql(ddl)
        logger.info(f"Successfully created Delta table: {table_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to create Delta table {table_name}: {e!s}")
        return False


def delete_from_delta_table(
    table_name: str, condition: str, spark: SparkSession | None = None
) -> bool:
    """Delta Lakeテーブルからのデータ削除

    Args:
        table_name: テーブル名
        condition: 削除条件（SQL WHERE句）
        spark: SparkSession

    Returns:
        bool: 削除成功可否
    """
    try:
        if spark is None:
            spark = SparkSession.getActiveSession()

        logger.info(
            f"Deleting from Delta table {table_name} with condition: {condition}"
        )

        # 削除実行
        spark.sql(f"DELETE FROM {table_name} WHERE {condition}")

        logger.info(f"Successfully deleted from {table_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete from Delta table {table_name}: {e!s}")
        return False


def time_travel_delta_table(
    table_name: str,
    version: int | None = None,
    timestamp: str | None = None,
    spark: SparkSession | None = None,
) -> DataFrame | None:
    """Delta Lake Time Travel機能

    Args:
        table_name: テーブル名
        version: バージョン番号
        timestamp: タイムスタンプ（ISO形式）
        spark: SparkSession

    Returns:
        DataFrame: 指定時点のデータ（失敗時はNone）
    """
    try:
        if spark is None:
            spark = SparkSession.getActiveSession()

        if version is not None:
            logger.info(f"Reading {table_name} at version {version}")
            df = (
                spark.read.format("delta")
                .option("versionAsOf", version)
                .table(table_name)
            )
        elif timestamp is not None:
            logger.info(f"Reading {table_name} at timestamp {timestamp}")
            df = (
                spark.read.format("delta")
                .option("timestampAsOf", timestamp)
                .table(table_name)
            )
        else:
            raise ValueError("Either version or timestamp must be specified")

        record_count = df.count()
        logger.info(f"Time travel query returned {record_count} records")

        return df

    except Exception as e:
        logger.error(f"Failed time travel query for {table_name}: {e!s}")
        return None
