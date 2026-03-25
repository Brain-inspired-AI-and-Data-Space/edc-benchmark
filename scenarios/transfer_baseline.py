from __future__ import annotations

from .base import ScenarioBase, render_template, timer


class TransferBaselineScenario(ScenarioBase):
    scenario_name = "transfer_baseline"

    def run_once(self, run_index: int) -> dict[str, object]:
        result: dict[str, object] = {
            "scenario": self.scenario_name,
            "run_index": run_index,
            "success": False,
        }

        run_ids = self.build_run_ids(run_index)
        result.update(
            {
                "asset_id": run_ids["ASSET_ID"],
                "policy_id": run_ids["POLICY_ID"],
                "contract_definition_id": run_ids["CONTRACT_DEFINITION_ID"],
                "data_size_mb": self.config.get("data_size_mb", 1),
            }
        )

        try:
            # 先准备公共资源（不计入四段控制/编排指标）
            self.create_common_resources(run_ids)

            # ---- 1) Catalog Request ----
            dataset_request_payload = render_template(
                self.config["dataset_request_template_path"],
                run_ids,
            )

            with timer() as t_catalog:
                dataset_response = self.consumer.request_dataset(dataset_request_payload)

            result["catalog_request_latency_s"] = round(t_catalog["duration_s"], 6)

            offer_id = self.extract_offer_id(dataset_response)
            result["offer_id"] = offer_id

            # ---- 2) Contract Offer Negotiation ----
            negotiation_vars = dict(run_ids)
            negotiation_vars["CONTRACT_OFFER_ID"] = offer_id

            negotiation_payload = render_template(
                self.config["negotiation_template_path"],
                negotiation_vars,
            )

            with timer() as t_negotiation_request:
                negotiation_response = self.consumer.start_negotiation(negotiation_payload)

            negotiation_id = negotiation_response["@id"]
            result["negotiation_id"] = negotiation_id
            result["contract_offer_negotiation_latency_s"] = round(
                t_negotiation_request["duration_s"], 6
            )

            # ---- 3) Contract Agreement ----
            with timer() as t_agreement:
                final_negotiation = self.wait_for_negotiation(negotiation_id)

            result["contract_agreement_latency_s"] = round(
                t_agreement["duration_s"], 6
            )
            result["negotiation_state"] = final_negotiation.get("state")

            agreement_id = self.extract_agreement_id(final_negotiation)
            if not agreement_id:
                result["error"] = (
                    final_negotiation.get("errorDetail")
                    or "No contract agreement id found"
                )
                return result

            result["contract_agreement_id"] = agreement_id

            # ---- 4) Transfer Initiation ----
            transfer_vars = dict(run_ids)
            transfer_vars["CONTRACT_AGREEMENT_ID"] = agreement_id

            transfer_payload = render_template(
                self.config["transfer_template_path"],
                transfer_vars,
            )

            with timer() as t_transfer_initiation:
                transfer_response = self.consumer.start_transfer(transfer_payload)

            transfer_id = transfer_response["@id"]
            result["transfer_id"] = transfer_id
            result["transfer_initiation_latency_s"] = round(
                t_transfer_initiation["duration_s"], 6
            )

            # 可选：继续轮询 transfer 最终状态（不计入 transfer initiation 四段指标）
            with timer() as t_transfer_completion:
                final_transfer = self.wait_for_transfer(transfer_id)

            result["transfer_completion_latency_s"] = round(
                t_transfer_completion["duration_s"], 6
            )
            result["transfer_state"] = final_transfer.get("state")

            # 总控制/编排耗时（四段）
            result["control_plane_total_latency_s"] = round(
                result["catalog_request_latency_s"]
                + result["contract_offer_negotiation_latency_s"]
                + result["contract_agreement_latency_s"]
                + result["transfer_initiation_latency_s"],
                6,
            )
            # 端到端传输时间
            result["transfer_end_to_end_latency_s"] = round(result["transfer_initiation_latency_s"] + result["transfer_completion_latency_s"],6,)

            # 额外给吞吐量（基于完成耗时，不属于四段之一）
            data_size_mb = float(self.config.get("data_size_mb", 1))
            completion_duration = max(
                float(result["transfer_completion_latency_s"]), 1e-9
            )
            result["throughput_mb_s"] = round(data_size_mb / completion_duration, 6)

            if final_transfer.get("state") in {
                "COMPLETED",
                "FINISHED",
                "DEPROVISIONED",
            }:
                result["success"] = True
            else:
                result["error"] = (
                    final_transfer.get("errorDetail")
                    or f"Transfer ended in state={final_transfer.get('state')}"
                )

            return result

        except Exception as exc:
            result["error"] = str(exc)
            return result
