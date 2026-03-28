from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from scenarios import MetricsRecorder, SCENARIO_REGISTRY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one EDC benchmark experiment.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML config file.",
    )
    return parser.parse_args()


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError(f"Config file must contain a YAML object: {path}")

    return config


def prepare_output_dir(config: dict[str, Any], config_path: str | Path) -> Path:
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    copied_config_path = output_dir / "config.yaml"
    shutil.copyfile(config_path, copied_config_path)

    return output_dir


def setup_logger(output_dir: Path) -> logging.Logger:
    logger = logging.getLogger("edc-benchmark")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(output_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]

    values = sorted(values)
    k = (len(values) - 1) * p
    f = int(k)
    c = min(f + 1, len(values) - 1)

    if f == c:
        return values[f]

    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return d0 + d1


def summarize_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "experiment_id": config.get("experiment_id"),
        "scenario": config.get("scenario"),
        "repeat": config.get("repeat", 1),
        "total_runs": len(rows),
        "success_runs": sum(1 for r in rows if r.get("success") is True),
        "failed_runs": sum(1 for r in rows if r.get("success") is not True),
    }

    if rows:
        summary["success_rate"] = round(summary["success_runs"] / len(rows), 6)
    else:
        summary["success_rate"] = 0.0

    # 统一后的核心 benchmark 指标
    benchmark_fields = [
        "catalog_request_latency_s",
        "contract_offer_negotiation_latency_s",
        "contract_agreement_latency_s",
        "transfer_initiation_latency_s",
        "transfer_completion_latency_s",
        "transfer_end_to_end_latency_s",
        "control_plane_total_latency_s",
        "throughput_mb_s",
        "policy_evaluation_latency_s",
        "resource_setup_latency_s",
        "recovery_time_s",
        "retry_success_rate",
        "degraded_mode_success_rate",
        "failed_transactions",
    ]

    aggregates: dict[str, float] = {}

    for field in benchmark_fields:
        values = []
        for row in rows:
            value = row.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))

        if values:
            aggregates[f"{field}_avg"] = round(mean(values), 6)
            aggregates[f"{field}_min"] = round(min(values), 6)
            aggregates[f"{field}_max"] = round(max(values), 6)
            aggregates[f"{field}_p50"] = round(percentile(values, 0.50), 6)
            aggregates[f"{field}_p95"] = round(percentile(values, 0.95), 6)

            # 对计数型字段，补一个 sum，更适合横向比较
            if field in {"failed_transactions"}:
                aggregates[f"{field}_sum"] = round(sum(values), 6)

    summary["aggregates"] = aggregates

    # 保留失败详情，方便后续检查
    failures = []
    for row in rows:
        if row.get("success") is not True:
            failures.append(
                {
                    "run_index": row.get("run_index"),
                    "error": row.get("error"),
                    "negotiation_state": row.get("negotiation_state"),
                    "transfer_state": row.get("transfer_state"),
                }
            )
    summary["failures"] = failures

    return summary


def validate_config(config: dict[str, Any]) -> None:
    required = [
        "experiment_id",
        "scenario",
        "repeat",
        "output_dir",
        "provider_management_url",
        "consumer_management_url",
        "provider_protocol_url",
        "consumer_protocol_url",
        "api_key",
    ]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"Missing required config keys: {missing}")

    scenario = config["scenario"]
    if scenario not in SCENARIO_REGISTRY:
        raise ValueError(
            f"Unsupported scenario={scenario}. "
            f"Expected one of {list(SCENARIO_REGISTRY.keys())}"
        )


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)
    validate_config(config)

    output_dir = prepare_output_dir(config, config_path)
    logger = setup_logger(output_dir)

    logger.info(
        "Starting experiment_id=%s scenario=%s",
        config["experiment_id"],
        config["scenario"],
    )
    logger.info("Output directory: %s", output_dir)

    scenario_cls = SCENARIO_REGISTRY[config["scenario"]]
    scenario = scenario_cls(config)
    recorder = MetricsRecorder()

    repeat = int(config.get("repeat", 1))
    for run_index in range(1, repeat + 1):
        logger.info("Running iteration %s/%s", run_index, repeat)
        row = scenario.run_once(run_index)
        recorder.add(row)

        if row.get("success"):
            logger.info("Run %s succeeded", run_index)
        else:
            logger.error("Run %s failed: %s", run_index, row.get("error"))

    metrics_path = output_dir / "metrics.csv"
    summary_path = output_dir / "summary.json"

    recorder.write_csv(metrics_path)
    summary = summarize_rows(recorder.rows, config)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("Metrics written to %s", metrics_path)
    logger.info("Summary written to %s", summary_path)
    logger.info(
        "Experiment finished: success_runs=%s failed_runs=%s success_rate=%s",
        summary["success_runs"],
        summary["failed_runs"],
        summary["success_rate"],
    )


if __name__ == "__main__":
    main()
