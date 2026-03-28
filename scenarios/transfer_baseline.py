from __future__ import annotations

from .base import ScenarioBase, render_template


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

            dataset_response, catalog_latency = self.measure_catalog_request(
                dataset_request_payload
            )
            result["catalog_request_latency_s"] = catalog_latency

            offer_id = self.extract_offer_id(dataset_response)
            result["offer_id"] = offer_id

            # ---- 2) Contract Offer Negotiation ----
            negotiation_vars = dict(run_ids)
            negotiation_vars["CONTRACT_OFFER_ID"] = offer_id

            negotiation_payload = render_template(
                self.config["negotiation_template_path"],
                negotiation_vars,
            )

            negotiation_response, negotiation_latency = (
                self.measure_contract_offer_negotiation(negotiation_payload)
            )

            negotiation_id = negotiation_response["@id"]
            result["negotiation_id"] = negotiation_id
            result["contract_offer_negotiation_latency_s"] = negotiation_latency

            # ---- 3) Contract Agreement ----
            final_negotiation, agreement_latency = self.measure_contract_agreement(
                negotiation_id
            )

            result["contract_agreement_latency_s"] = agreement_latency
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

            transfer_response, transfer_initiation_latency = (
                self.measure_transfer_initiation(transfer_payload)
            )

            transfer_id = transfer_response["@id"]
            result["transfer_id"] = transfer_id
            result["transfer_initiation_latency_s"] = transfer_initiation_latency

            # ---- Transfer Completion ----
            final_transfer, transfer_completion_latency = (
                self.measure_transfer_completion(transfer_id)
            )

            result["transfer_completion_latency_s"] = transfer_completion_latency
            result["transfer_state"] = final_transfer.get("state")

            # 总控制/编排耗时（四段）
            result["control_plane_total_latency_s"] = (
                self.compute_control_plane_total_latency(
                    catalog_request_latency_s=result["catalog_request_latency_s"],
                    contract_offer_negotiation_latency_s=result[
                        "contract_offer_negotiation_latency_s"
                    ],
                    contract_agreement_latency_s=result[
                        "contract_agreement_latency_s"
                    ],
                    transfer_initiation_latency_s=result[
                        "transfer_initiation_latency_s"
                    ],
                )
            )

            # 端到端传输时间（统一口径）
            result["transfer_end_to_end_latency_s"] = (
                self.compute_transfer_end_to_end_latency(
                    transfer_initiation_latency_s=result[
                        "transfer_initiation_latency_s"
                    ],
                    transfer_completion_latency_s=result[
                        "transfer_completion_latency_s"
                    ],
                )
            )

            # 吞吐量：统一基于 transfer_completion_latency_s 计算
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
