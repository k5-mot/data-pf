#!/usr/bin/env python3
"""テクニカル指標パイプライン DAG.

yfinance API から株価データを取得し、テクニカル指標を計算する
Bronze → Silver → Gold 層の処理を実行

作成者: Data Engineering Team
作成日: 2025-07-27
"""

from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

# デフォルト引数
default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(
        year=2025, month=7, day=27, tzinfo=timezone(timedelta(hours=9))
    ),
    "email_on_failure": True,
    "email_on_retry": False,
    "email": ["data-team@company.com"],
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
    "sla": timedelta(hours=2),
}

# DAG定義
with DAG(
    "technical_indicators_pipeline",
    default_args=default_args,
    description="Fetch stock data and calculate technical indicators.",
    schedule="0 6 * * 1-5",  # 平日朝6時実行
    catchup=False,
    max_active_runs=1,
    tags=["yfinance", "technical", "bronze", "silver", "gold"],
) as dag:
    ## Step.0 Start:    Notify the start of DAG.
    start_dag = EmptyOperator(
        task_id="start_dag",
        doc_md="""
        - Step.0 Start:    Notify the start of DAG.
        - Step.1 Bronze:   Data Ingestion.
        - Step.2 Silver:   Clean and validate stock data.
        - Step.3 Gold:     Calculate technical indicators.
        - Step.4 Validate: Validate technical indicators.
        - Step.5 End:      Notify the end of DAG.
        """,
    )

    ## Step.1 Bronze: Fetch raw data from yfinance API.
    ingest_raw_data = SparkSubmitOperator(
        task_id="ingest_raw_data",
        application="/opt/airflow/scripts/bronze/ingest_yfinance.py",
        conn_id="spark_default",
        application_args=[
            "--symbols",
            "AAPL,7203.T,6758.T",  # Apple, Toyota, Sony
            "--period",
            "30d",  # 過去30日分
            "--output_table",
            "bronze.raw_yfinance",
        ],
    )

    # 品質検証: テクニカル指標の妥当性確認
    # validate_data_quality = SparkSubmitOperator(
    #     task_id="validate_data_quality",
    #     application="/opt/airflow/scripts/quality/validate_technical_features.py",
    #     conn_id="spark_default",
    #     application_args=[
    #         "--input_table",
    #         "gold.technical_features",
    #         "--validation_rules",
    #         "/opt/airflow/config/technical_validation_rules.yaml",
    #     ],
    #     doc_md="""
    #     ### テクニカル指標品質検証タスク

    #     計算されたテクニカル指標の品質を検証します。

    #     **検証項目:**
    #     - 指標値の範囲チェック（RSI: 0-100等）
    #     - 移動平均の順序関係確認
    #     - ボリンジャーバンドの上下関係
    #     - 異常値・外れ値の検出
    #     - データ完整性の確認

    #     **アラート:** 品質問題検出時にSlack通知
    #     """,
    # )

    ## Step.2 Silver:   Clean and validate stock data.
    clean_and_validate_data = SparkSubmitOperator(
        task_id="clean_and_validate_data",
        application="/opt/airflow/scripts/silver/clean_yfinance.py",
        conn_id="spark_default",
        application_args=[
            "--input_table",
            "bronze.raw_finance",
            "--output_table",
            "silver.clean_stock",
            "--quality_threshold",
            "0.8",
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
        """,
    )

    # Gold層: テクニカル指標計算
    aggregate_business_metrics = SparkSubmitOperator(
        task_id="aggregate_business_metrics",
        application="/opt/airflow/scripts/gold/aggregate_technical_indicators.py",
        conn_id="spark_default",
        conf={"spark.master": "spark://lakehouse-spark-master:7077"},
        deploy_mode="client",
        application_args=[
            "--input_table",
            "silver.stock_prices_clean",
            "--output_table",
            "gold.technical_features",
            "--indicators",
            "sma,ema,rsi,macd,bollinger,atr",
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
        """,
    )

    # 品質検証: テクニカル指標の妥当性確認
    engineer_features = SparkSubmitOperator(
        task_id="engineer_features",
        application="/opt/airflow/scripts/quality/validate_technical_features.py",
        conn_id="spark_default",
        conf={"spark.master": "spark://lakehouse-spark-master:7077"},
        deploy_mode="client",
        application_args=[
            "--input_table",
            "gold.technical_features",
            "--validation_rules",
            "/opt/airflow/config/technical_validation_rules.yaml",
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
        """,
    )

    # 終了ダミータスク
    end_dag = EmptyOperator(
        task_id="end_dag",
        doc_md="""
        ## テクニカル指標パイプライン完了

        全ての処理が正常に完了しました。

        ### 生成データ
        - bronze.yfinance_raw: 株価生データ
        - silver.stock_prices_clean: クリーン株価データ
        - gold.technical_features: テクニカル指標

        ### 次のステップ
        - マクロ指標パイプラインが自動実行されます(6:30)
        - 品質ダッシュボードで結果を確認できます
        """,
    )

    # タスク依存関係の定義
    (
        start_dag
        >> ingest_raw_data
        >> clean_and_validate_data
        >> aggregate_business_metrics
        >> engineer_features
        >> end_dag
    )
