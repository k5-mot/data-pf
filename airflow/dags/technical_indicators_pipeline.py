#!/usr/bin/env python3
"""
テクニカル指標パイプライン DAG

yfinance API から株価データを取得し、テクニカル指標を計算する
Bronze → Silver → Gold 層の処理を実行

作成者: Data Engineering Team
作成日: 2025-07-27
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from airflow.operators.empty import EmptyOperator

# デフォルト引数
default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'start_date': datetime(2025, 7, 27),
    'email_on_failure': True,
    'email_on_retry': False,
    'email': ['data-team@company.com'],
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(hours=1),
    'sla': timedelta(hours=2)
}

# DAG定義
with DAG(
    'technical_indicators_pipeline',
    default_args=default_args,
    description='株価データ取得とテクニカル指標計算パイプライン',
    schedule='0 6 * * 1-5',  # 平日朝6時実行
    catchup=False,
    max_active_runs=1,
    tags=['yfinance', 'technical', 'bronze', 'silver', 'gold']
) as dag:

    # 開始ダミータスク
    start_task = EmptyOperator(
        task_id='start_technical_pipeline',
        doc_md="""
        ## テクニカル指標パイプライン開始

        yfinanceから株価データを取得し、テクニカル指標を計算するパイプラインを開始します。

        ### 処理フロー
        1. Bronze層: yfinance API データ取得
        2. Silver層: データクリーニング・品質チェック
        3. Gold層: テクニカル指標計算
        4. 品質検証: 計算結果の妥当性確認
        """
    )

    # 初期化: Deltaテーブルの作成
    # jars="/opt/airflow/jars/hadoop-aws-3.3.6.jar,/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar,/opt/airflow/jars/delta-hive_2.12-3.3.2.jar,/opt/airflow/jars/delta-spark_2.12-3.3.2.jar,/opt/airflow/jars/delta-storage-3.3.2.jar,/opt/airflow/jars/mysql-connector-java-8.0.19.jar",
    # packages="org.apache.hadoop:hadoop-aws:3.3.6",
    # packages="org.apache.hadoop:hadoop-aws:3.3.6,com.amazonaws:aws-java-sdk-bundle:1.12.367,io.delta:delta-hive_2.12:3.3.2,io.delta:delta-spark_2.12:3.3.2,io.delta:delta-storage:3.3.2,mysql:mysql-connector-java:8.0.19",
    # jars="/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar,/opt/airflow/jars/delta-spark_2.12-3.3.2.jar,/opt/airflow/jars/delta-storage-3.3.2.jar,/opt/airflow/jars/hadoop-aws-3.2.3.jar,/opt/airflow/jars/mysql-connector-java-8.0.19.jar,/opt/airflow/jars/delta-hive_2.12-3.3.2.jar",
    # conf={
    #     "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
    #     "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog",
    #     "spark.hadoop.fs.s3a.endpoint": "http://minio:9000",
    #     "spark.hadoop.fs.s3a.access.key": "admin",
    #     "spark.hadoop.fs.s3a.secret.key": "adminpass",
    #     "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
    #     "spark.hadoop.fs.s3a.path.style.access": "true",
    #     "spark.hadoop.fs.s3a.connection.ssl.enabled": "false",
    #     "spark.hadoop.fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
    #     "spark.sql.warehouse.dir": "s3a://lakehouse/",
    #     "hive.metastore.uris": "thrift://hive-metastore:9083"
    # }
    setup_table = SparkSubmitOperator(
        task_id='setup_table',
        application="/opt/airflow/scripts/create_schema.py",
        conn_id="spark_default",
        deploy_mode="client",
        jars="/opt/airflow/jars/hadoop-aws-3.3.6.jar,/opt/airflow/jars/hadoop-common-3.3.6.jar,/opt/airflow/jars/hadoop-hdfs-3.3.6.jar,/opt/airflow/jars/aws-java-sdk-bundle-1.12.367.jar,/opt/airflow/jars/s3-2.31.78.jar,/opt/airflow/jars/delta-hive_2.12-3.3.2.jar,/opt/airflow/jars/delta-spark_2.12-3.3.2.jar,/opt/airflow/jars/delta-storage-3.3.2.jar,/opt/airflow/jars/mysql-connector-java-8.0.19.jar",
        packages="org.apache.hadoop:hadoop-aws:3.3.6,org.apache.hadoop:hadoop-common:3.3.6,com.amazonaws:aws-java-sdk-bundle:1.12.367,software.amazon.awssdk:s3:2.31.78,io.delta:delta-hive_2.12:3.3.2,io.delta:delta-spark_2.12:3.3.2,io.delta:delta-storage:3.3.2,mysql:mysql-connector-java:8.0.19",
        conf={
            "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
            "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog"
        }
    )

    # Bronze層: yfinance データ取得
    ingest_yfinance_data = SparkSubmitOperator(
        task_id='ingest_yfinance_data',
        application='/opt/airflow/scripts/bronze/ingest_yfinance.py',
        conn_id='spark_default',
        deploy_mode='client',
        # packages='io.delta:delta-spark_2.12:3.0.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.367',
        # conf={
        #     'spark.sql.extensions': 'io.delta.sql.DeltaSparkSessionExtension',
        #     'spark.sql.catalog.spark_catalog': 'org.apache.spark.sql.delta.catalog.DeltaCatalog',
        #     'spark.serializer': 'org.apache.spark.serializer.KryoSerializer',
        #     'spark.sql.adaptive.enabled': 'true',
        #     'spark.sql.adaptive.coalescePartitions.enabled': 'true',
        #     'spark.hadoop.fs.s3a.endpoint': 'http://minio:9000',
        #     'spark.hadoop.fs.s3a.access.key': 'admin',
        #     'spark.hadoop.fs.s3a.secret.key': 'adminpass',
        #     'spark.hadoop.fs.s3a.path.style.access': 'true',
        #     'spark.hadoop.fs.s3a.impl': 'org.apache.hadoop.fs.s3a.S3AFileSystem'
        # },
        application_args=[
            '--symbols', 'AAPL,7203.T,6758.T',  # Apple, Toyota, Sony
            '--period', '30d',  # 過去30日分
            '--output_table', 'bronze.yfinance_raw'
        ],
        doc_md="""
        ### yfinance データ取得タスク

        Yahoo Finance API から株価データを取得し、Bronze層に保存します。

        **取得データ:**
        - OHLCV（始値、高値、安値、終値、出来高）
        - 分割・配当情報
        - 調整後終値

        **対象銘柄:**
        - AAPL: Apple Inc.
        - 7203.T: トヨタ自動車
        - 6758.T: ソニーグループ

        **保存先:** bronze.yfinance_raw
        """
    )

    # Silver層: データクリーニング
    clean_stock_data = SparkSubmitOperator(
        task_id='clean_stock_data',
        application='/opt/airflow/scripts/silver/clean_stock_data.py',
        conn_id='spark_default',
        deploy_mode='client',
        packages='io.delta:delta-spark_2.12:3.0.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.367',
        conf={
            'spark.sql.extensions': 'io.delta.sql.DeltaSparkSessionExtension',
            'spark.sql.catalog.spark_catalog': 'org.apache.spark.sql.delta.catalog.DeltaCatalog',
            'spark.serializer': 'org.apache.spark.serializer.KryoSerializer',
            'spark.sql.adaptive.enabled': 'true',
            'spark.hadoop.fs.s3a.endpoint': 'http://minio:9000',
            'spark.hadoop.fs.s3a.access.key': 'admin',
            'spark.hadoop.fs.s3a.secret.key': 'adminpass',
            'spark.hadoop.fs.s3a.path.style.access': 'true',
            'spark.hadoop.fs.s3a.impl': 'org.apache.hadoop.fs.s3a.S3AFileSystem'
        },
        application_args=[
            '--input_table', 'bronze.yfinance_raw',
            '--output_table', 'silver.stock_prices_clean',
            '--quality_threshold', '0.8'
        ],
        doc_md="""
        ### 株価データクリーニングタスク

        Bronze層の生データをクリーニングし、Silver層に保存します。

        **処理内容:**
        - データ品質チェック（Deequ使用）
        - 外れ値検出・補正
        - 欠損値処理
        - 価格の論理整合性確認（high >= low等）
        - 通貨・取引所情報の標準化

        **品質スコア閾値:** 0.8以上
        **保存先:** silver.stock_prices_clean
        """
    )

    # Gold層: テクニカル指標計算
    calculate_technical_features = SparkSubmitOperator(
        task_id='calculate_technical_features',
        application='/opt/airflow/scripts/gold/calculate_technical_features.py',
        conn_id='spark_default',
        deploy_mode='client',
        packages='io.delta:delta-spark_2.12:3.0.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.367',
        conf={
            'spark.sql.extensions': 'io.delta.sql.DeltaSparkSessionExtension',
            'spark.sql.catalog.spark_catalog': 'org.apache.spark.sql.delta.catalog.DeltaCatalog',
            'spark.serializer': 'org.apache.spark.serializer.KryoSerializer',
            'spark.sql.adaptive.enabled': 'true',
            'spark.hadoop.fs.s3a.endpoint': 'http://minio:9000',
            'spark.hadoop.fs.s3a.access.key': 'admin',
            'spark.hadoop.fs.s3a.secret.key': 'adminpass',
            'spark.hadoop.fs.s3a.path.style.access': 'true',
            'spark.hadoop.fs.s3a.impl': 'org.apache.hadoop.fs.s3a.S3AFileSystem'
        },
        application_args=[
            '--input_table', 'silver.stock_prices_clean',
            '--output_table', 'gold.technical_features',
            '--indicators', 'sma,ema,rsi,macd,bollinger,atr'
        ],
        doc_md="""
        ### テクニカル指標計算タスク

        Silver層のクリーンデータから各種テクニカル指標を計算し、Gold層に保存します。

        **計算指標:**
        - 移動平均: SMA(5,20,50), EMA(12,26)
        - オシレーター: RSI(14), MACD, ストキャスティクス
        - ボラティリティ: ボリンジャーバンド, ATR(14)
        - 出来高: Volume SMA(20), Volume Ratio
        - モメンタム: Price Momentum(5d,20d), Volatility(20d)

        **保存先:** gold.technical_features
        """
    )

    # 品質検証: テクニカル指標の妥当性確認
    validate_technical_features = SparkSubmitOperator(
        task_id='validate_technical_features',
        application='/opt/airflow/scripts/quality/validate_technical_features.py',
        conn_id='spark_default',
        deploy_mode='client',
        packages='io.delta:delta-spark_2.12:3.0.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.367',
        conf={
            'spark.sql.extensions': 'io.delta.sql.DeltaSparkSessionExtension',
            'spark.sql.catalog.spark_catalog': 'org.apache.spark.sql.delta.catalog.DeltaCatalog',
            'spark.serializer': 'org.apache.spark.serializer.KryoSerializer',
            'spark.sql.adaptive.enabled': 'true',
            'spark.hadoop.fs.s3a.endpoint': 'http://minio:9000',
            'spark.hadoop.fs.s3a.access.key': 'admin',
            'spark.hadoop.fs.s3a.secret.key': 'adminpass',
            'spark.hadoop.fs.s3a.path.style.access': 'true',
            'spark.hadoop.fs.s3a.impl': 'org.apache.hadoop.fs.s3a.S3AFileSystem'
        },
        application_args=[
            '--input_table', 'gold.technical_features',
            '--validation_rules', '/opt/airflow/config/technical_validation_rules.yaml'
        ],
        doc_md="""
        ### テクニカル指標品質検証タスク

        計算されたテクニカル指標の品質を検証します。

        **検証項目:**
        - 指標値の範囲チェック（RSI: 0-100等）
        - 移動平均の順序関係確認
        - ボリンジャーバンドの上下関係
        - 異常値・外れ値の検出
        - データ完整性の確認

        **アラート:** 品質問題検出時にSlack通知
        """
    )

    # 終了ダミータスク
    end_task = EmptyOperator(
        task_id='end_technical_pipeline',
        doc_md="""
        ## テクニカル指標パイプライン完了

        全ての処理が正常に完了しました。

        ### 生成データ
        - bronze.yfinance_raw: 株価生データ
        - silver.stock_prices_clean: クリーン株価データ
        - gold.technical_features: テクニカル指標

        ### 次のステップ
        - マクロ指標パイプラインが自動実行されます（6:30）
        - 品質ダッシュボードで結果を確認できます
        """
    )

    # タスク依存関係の定義
    start_task >> setup_table >> ingest_yfinance_data >> clean_stock_data >> calculate_technical_features >> validate_technical_features >> end_task
