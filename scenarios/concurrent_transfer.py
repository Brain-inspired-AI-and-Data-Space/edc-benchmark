from __future__ import annotations

import concurrent.futures
from typing import Any
from .base import ScenarioBase, render_template, timer


class TransferConcurrentScenario(ScenarioBase):
    scenario_name = "concurrent_transfer"

    def run_once(self, run_index: int) -> dict[str, Any]:
        result: dict[str, Any] = {
            "scenario": self.scenario_name,
            "run_index": run_index,
            "success": False,
        }

        concurrency = int(self.config.get("concurrent_transfers", 2))
        data_size_mb = float(self.config.get("data_size_mb", 1))
        run_ids_list = [self.build_run_ids(run_index) for _ in range(concurrency)]

        # 用于收集每个 worker 的 row
        rows: list[dict[str, Any]] = []

        def single_transfer_task(run_ids: dict[str, str]) -> dict[str, Any]:
            row = {
                "scenario": self.scenario_name,
                "run_index": run_index,
                "success": False,
                "asset_id": run_ids["ASSET_ID"],
                "policy_id": run_ids["POLICY_ID"],
                "contract_definition_id": run_ids["CONTRACT_DEFINITION_ID"],
                "data_size_mb": data_size_mb,
            }
            try:
                # 1. 创建资源（asset/policy/contract）
                self.create_common_resources(run_ids)

                # ---- 1) Catalog Request ----
                dataset_request_payload = render_template(
                    self.config["dataset_request_template_path"],
                    run_ids,
                )
                with timer() as t_catalog:
                    dataset_response = self.consumer.request_dataset(dataset_request_payload)
                row["catalog_request_latency_s"] = round(t_catalog["duration_s"], 6)
                offer_id = self.extract_offer_id(dataset_response)
                row["offer_id"] = offer_id

                # ---- 2) Contract Offer Negotiation ----
                negotiation_vars = dict(run_ids)
                negotiation_vars["CONTRACT_OFFER_ID"] = offer_id
                negotiation_payload = render_template(
                    self.config["negotiation_template_path"], negotiation_vars
                )
                with timer() as t_negotiation_request:
                    negotiation_response = self.consumer.start_negotiation(negotiation_payload)
                negotiation_id = negotiation_response["@id"]
                row["negotiation_id"] = negotiation_id
                row["contract_offer_negotiation_latency_s"] = round(t_negotiation_request["duration_s"], 6)

                # ---- 3) Contract Agreement ----
                with timer() as t_agreement:
                    final_negotiation = self.wait_for_negotiation(negotiation_id)
                row["contract_agreement_latency_s"] = round(t_agreement["duration_s"], 6)
                row["negotiation_state"] = final_negotiation.get("state")
                agreement_id = self.extract_agreement_id(final_negotiation)
                if not agreement_id:
                    row["error"] = "No contract agreement id found"
                    return row
                row["contract_agreement_id"] = agreement_id

                # ---- 4) Transfer Initiation ----
                transfer_vars = dict(run_ids)
                transfer_vars["CONTRACT_AGREEMENT_ID"] = agreement_id
                transfer_payload = render_template(
                    self.config["transfer_template_path"], transfer_vars
                )
                with timer() as t_transfer_initiation:
                    transfer_response = self.consumer.start_transfer(transfer_payload)
                transfer_id = transfer_response["@id"]
                row["transfer_id"] = transfer_id
                row["transfer_initiation_latency_s"] = round(t_transfer_initiation["duration_s"], 6)

                # ---- Transfer Completion ----
                with timer() as t_transfer_completion:
                    final_transfer = self.wait_for_transfer(transfer_id)
                row["transfer_completion_latency_s"] = round(t_transfer_completion["duration_s"], 6)
                row["transfer_state"] = final_transfer.get("state")

                # ---- Control plane & end-to-end ----
                row["control_plane_total_latency_s"] = round(
                    row["catalog_request_latency_s"]
                    + row["contract_offer_negotiation_latency_s"]
                    + row["contract_agreement_latency_s"]
                    + row["transfer_initiation_latency_s"], 6
                )
                row["transfer_end_to_end_latency_s"] = round(
                    row["transfer_initiation_latency_s"] + row["transfer_completion_latency_s"], 6
                )
                # 吞吐量
                completion_duration = max(row["transfer_completion_latency_s"], 1e-9)
                row["throughput_mb_s"] = round(data_size_mb / completion_duration, 6)

                if final_transfer.get("state") in {"COMPLETED", "FINISHED", "DEPROVISIONED"}:
                    row["success"] = True
                else:
                    row["error"] = f"Transfer ended in state={final_transfer.get('state')}"
                return row

            except Exception as exc:
                row["error"] = str(exc)
                return row

        # ---- 并发执行 ----
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_rows = [executor.submit(single_transfer_task, run_ids) for run_ids in run_ids_list]
            for future in concurrent.futures.as_completed(future_rows):
                rows.append(future.result())

        # 汇总并发任务的指标，取平均/总和/成功率等
        aggregated_row: dict[str, Any] = {
            "scenario": self.scenario_name,
            "run_index": run_index,
            "success": all(r.get("success") for r in rows),
            "concurrent_runs": len(rows),
        }
        # 选取数值型指标平均值
        numeric_fields = [
            "catalog_request_latency_s",
            "contract_offer_negotiation_latency_s",
            "contract_agreement_latency_s",
            "transfer_initiation_latency_s",
            "transfer_completion_latency_s",
            "transfer_end_to_end_latency_s",
            "control_plane_total_latency_s",
            "throughput_mb_s",
        ]
        for field in numeric_fields:
            values = [r.get(field) for r in rows if isinstance(r.get(field), (int, float))]
            if values:
                aggregated_row[field] = round(sum(values) / len(values), 6)
        # 保留失败详情
        failures = [r for r in rows if not r.get("success")]
        aggregated_row["failed_runs"] = len(failures)
        aggregated_row["success_runs"] = len(rows) - len(failures)
        aggregated_row["failures"] = failures

        return aggregated_row
