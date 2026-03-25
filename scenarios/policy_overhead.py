from __future__ import annotations

from .base import ScenarioBase, render_template, timer


class PolicyOverheadScenario(ScenarioBase):
    scenario_name = "policy_overhead"

    def get_policy_template_path(self) -> str:
        mode = self.config.get("policy_mode", "simple")

        mapping = {
            "none": self.config["policy_template_none_path"],
            "simple": self.config["policy_template_simple_path"],
            "medium": self.config["policy_template_medium_path"],
        }

        if mode not in mapping:
            raise ValueError(
                f"Unsupported policy_mode={mode}. Expected one of {list(mapping.keys())}"
            )

        return mapping[mode]

    def run_once(self, run_index: int) -> dict[str, object]:
        result: dict[str, object] = {
            "scenario": self.scenario_name,
            "run_index": run_index,
            "policy_mode": self.config.get("policy_mode", "simple"),
            "success": False,
        }

        run_ids = self.build_run_ids(run_index)
        result.update(
            {
                "asset_id": run_ids["ASSET_ID"],
                "policy_id": run_ids["POLICY_ID"],
                "contract_definition_id": run_ids["CONTRACT_DEFINITION_ID"],
            }
        )

        try:
            # 资源准备，不纳入四段主流程，但保留
            with timer() as t_resource_setup:
                self.create_common_resources(run_ids)
            result["resource_setup_latency_s"] = round(
                t_resource_setup["duration_s"], 6
            )

            # 1) Catalog Request
            dataset_request_payload = render_template(
                self.config["dataset_request_template_path"],
                run_ids,
            )

            with timer() as t_catalog:
                dataset_response = self.consumer.request_dataset(dataset_request_payload)

            result["catalog_request_latency_s"] = round(
                t_catalog["duration_s"], 6
            )

            offer_id = self.extract_offer_id(dataset_response)
            result["offer_id"] = offer_id

            # 2) Contract Offer Negotiation
            negotiation_vars = dict(run_ids)
            negotiation_vars["CONTRACT_OFFER_ID"] = offer_id

            negotiation_payload = render_template(
                self.config["negotiation_template_path"],
                negotiation_vars,
            )

            with timer() as t_negotiation_request:
                negotiation_response = self.consumer.start_negotiation(
                    negotiation_payload
                )

            negotiation_id = negotiation_response["@id"]
            result["negotiation_id"] = negotiation_id
            result["contract_offer_negotiation_latency_s"] = round(
                t_negotiation_request["duration_s"], 6
            )

            # 3) Contract Agreement
            with timer() as t_agreement:
                final_negotiation = self.wait_for_negotiation(negotiation_id)

            result["contract_agreement_latency_s"] = round(
                t_agreement["duration_s"], 6
            )
            result["negotiation_state"] = final_negotiation.get("state")

            agreement_id = self.extract_agreement_id(final_negotiation)
            result["contract_agreement_id"] = agreement_id

            # policy 专属指标：这里先近似定义为 negotiation + agreement 两段之和
            result["policy_evaluation_latency_s"] = round(
                result["contract_offer_negotiation_latency_s"]
                + result["contract_agreement_latency_s"],
                6,
            )

            result["control_plane_total_latency_s"] = round(
                result["catalog_request_latency_s"]
                + result["contract_offer_negotiation_latency_s"]
                + result["contract_agreement_latency_s"],
                6,
            )

            state = final_negotiation.get("state")
            if agreement_id and state in {"FINALIZED", "CONFIRMED"}:
                result["success"] = True
            else:
                result["error"] = (
                    final_negotiation.get("errorDetail")
                    or f"Negotiation ended in state={state}"
                )

            return result

        except Exception as exc:
            result["error"] = str(exc)
            return result
