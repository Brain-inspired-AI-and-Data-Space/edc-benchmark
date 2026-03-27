from __future__ import annotations

import time

from scenarios.base import ScenarioBase, render_template, timer
from scripts.fault_injectors.network_faults import ToxiproxyClient


class TransferInterruptionScenario(ScenarioBase):
    scenario_name = "transfer_interruption"

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

        toxiproxy = ToxiproxyClient(self.config["toxiproxy_base_url"])
        proxy_name = self.config["toxiproxy_proxy_name"]
        interruption_timeout_ms = int(self.config.get("interruption_timeout_ms", 30000))

        try:
            toxiproxy.clear_toxics(proxy_name)

            # 公共资源创建（不计入四段核心时延）
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

            with timer() as t_neg:
                negotiation_response = self.consumer.start_negotiation(negotiation_payload)

            result["contract_offer_negotiation_latency_s"] = round(t_neg["duration_s"], 6)
            negotiation_id = negotiation_response["@id"]
            result["negotiation_id"] = negotiation_id

            # ---- 3) Contract Agreement ----
            with timer() as t_agreement:
                final_negotiation = self.wait_for_negotiation(negotiation_id)

            result["contract_agreement_latency_s"] = round(t_agreement["duration_s"], 6)
            result["negotiation_state"] = final_negotiation.get("state")

            agreement_id = self.extract_agreement_id(final_negotiation)
            if not agreement_id:
                result["failed_transactions"] = 1
                result["retry_success_rate"] = 0.0
                result["degraded_mode_success_rate"] = 0.0
                result["error"] = final_negotiation.get("errorDetail") or "No contract agreement id found"
                return result

            result["contract_agreement_id"] = agreement_id

            # ---- 4) Transfer Initiation ----
            transfer_vars = dict(run_ids)
            transfer_vars["CONTRACT_AGREEMENT_ID"] = agreement_id
            transfer_payload = render_template(
                self.config["transfer_template_path"],
                transfer_vars,
            )

            with timer() as t_transfer_init:
                transfer_response = self.consumer.start_transfer(transfer_payload)

            transfer_id = transfer_response["@id"]
            result["transfer_id"] = transfer_id
            result["transfer_initiation_latency_s"] = round(t_transfer_init["duration_s"], 6)

            result["control_plane_total_latency_s"] = round(
                result["catalog_request_latency_s"]
                + result["contract_offer_negotiation_latency_s"]
                + result["contract_agreement_latency_s"]
                + result["transfer_initiation_latency_s"],
                6,
            )

            # ---- 故障注入：中断传输链路 ----
            fault_delay_s = float(self.config.get("fault_injection_delay_s", 2.0))
            time.sleep(fault_delay_s)
            fault_start = time.perf_counter()
            toxiproxy.create_timeout(proxy_name, timeout_ms=interruption_timeout_ms)

            result["fault_type"] = "transfer_interruption"

            retry_attempts = int(self.config.get("retry_attempts", 3))
            retry_interval_s = float(self.config.get("retry_interval_s", 5.0))
            recovered = False
            final_transfer = None

            for _ in range(retry_attempts):
                try:
                    final_transfer = self.wait_for_transfer(transfer_id)
                    recovered = True
                    break
                except Exception:
                    time.sleep(retry_interval_s)

            result["retry_success_rate"] = round(
                (1.0 if recovered else 0.0),
                6,
            )

            result["recovery_time_s"] = round(
                time.perf_counter() - fault_start,
                6,
            )

            if final_transfer is None:
                result["failed_transactions"] = 1
                result["degraded_mode_success_rate"] = 0.0
                result["error"] = "Transfer interrupted and did not recover"
                return result

            result["transfer_state"] = final_transfer.get("state")

            # 这里把 interruption 后到最终完成的时间算进 transfer completion
            result["transfer_completion_latency_s"] = round(
                result["recovery_time_s"],
                6,
            )
            result["transfer_end_to_end_latency_s"] = round(
                result["transfer_initiation_latency_s"] + result["transfer_completion_latency_s"],
                6,
            )

            success_states = {"COMPLETED", "FINISHED", "DEPROVISIONED"}

            if final_transfer.get("state") in success_states:
                result["success"] = True
                result["failed_transactions"] = 0
                result["degraded_mode_success_rate"] = 1.0
            else:
                result["failed_transactions"] = 1
                result["degraded_mode_success_rate"] = 0.0
                result["error"] = final_transfer.get("errorDetail") or f"Transfer ended in state={final_transfer.get('state')}"

            return result

        except Exception as exc:
            result["retry_success_rate"] = 0.0
            result["degraded_mode_success_rate"] = 0.0
            result["failed_transactions"] = 1
            result["error"] = str(exc)
            return result
        finally:
            try:
                toxiproxy.clear_toxics(proxy_name)
            except Exception:
                pass
