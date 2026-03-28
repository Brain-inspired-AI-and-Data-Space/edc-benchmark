from __future__ import annotations

from scenarios.base import ScenarioBase, render_template, timer
from scripts.fault_injectors.network_faults import ToxiproxyClient


class PacketLossTransferScenario(ScenarioBase):
    scenario_name = "packet_loss_transfer"

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
        protocol_proxy_name = self.config["toxiproxy_protocol_proxy_name"]
        public_proxy_name = self.config["toxiproxy_public_proxy_name"]

        average_size = int(self.config.get("packet_slicer_average_size", 512))
        size_variation = int(self.config.get("packet_slicer_size_variation", 128))
        delay_us = int(self.config.get("packet_slicer_delay_us", 0))

        try:
            toxiproxy.clear_toxics(protocol_proxy_name)
            toxiproxy.clear_toxics(public_proxy_name)

            # 对 protocol 和 public 两条链路都加“伪丢包/分片扰动”
            toxiproxy.create_packet_loss(
                protocol_proxy_name,
                average_size=average_size,
                size_variation=size_variation,
                delay_us=delay_us,
            )
            toxiproxy.create_packet_loss(
                public_proxy_name,
                average_size=average_size,
                size_variation=size_variation,
                delay_us=delay_us,
            )

            result["fault_type"] = "packet_loss"
            result["packet_slicer_average_size"] = average_size
            result["packet_slicer_size_variation"] = size_variation
            result["packet_slicer_delay_us"] = delay_us

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

            result["contract_offer_negotiation_latency_s"] = round(
                t_neg["duration_s"], 6
            )
            negotiation_id = negotiation_response["@id"]
            result["negotiation_id"] = negotiation_id

            # ---- 3) Contract Agreement ----
            with timer() as t_agreement:
                final_negotiation = self.wait_for_negotiation(negotiation_id)

            result["contract_agreement_latency_s"] = round(
                t_agreement["duration_s"], 6
            )
            result["negotiation_state"] = final_negotiation.get("state")

            agreement_id = self.extract_agreement_id(final_negotiation)
            if not agreement_id:
                result["retry_success_rate"] = 0.0
                result["degraded_mode_success_rate"] = 0.0
                result["failed_transactions"] = 1
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

            with timer() as t_transfer_init:
                transfer_response = self.consumer.start_transfer(transfer_payload)

            result["transfer_initiation_latency_s"] = round(
                t_transfer_init["duration_s"], 6
            )

            transfer_id = transfer_response["@id"]
            result["transfer_id"] = transfer_id

            result["control_plane_total_latency_s"] = round(
                result["catalog_request_latency_s"]
                + result["contract_offer_negotiation_latency_s"]
                + result["contract_agreement_latency_s"]
                + result["transfer_initiation_latency_s"],
                6,
            )

            # ---- Transfer Completion / Retry ----
            retry_attempts = int(self.config.get("retry_attempts", 3))
            retry_interval_s = float(self.config.get("retry_interval_s", 5.0))

            final_transfer = None
            retry_success_count = 0

            with timer() as t_transfer_completion:
                for _ in range(retry_attempts):
                    try:
                        final_transfer = self.wait_for_transfer(transfer_id)
                        retry_success_count += 1
                        break
                    except Exception:
                        import time
                        time.sleep(retry_interval_s)

            result["transfer_completion_latency_s"] = round(
                t_transfer_completion["duration_s"], 6
            )
            result["transfer_end_to_end_latency_s"] = round(
                result["transfer_initiation_latency_s"]
                + result["transfer_completion_latency_s"],
                6,
            )

            result["retry_success_rate"] = round(
                retry_success_count / max(retry_attempts, 1),
                6,
            )

            if final_transfer is None:
                result["transfer_state"] = "UNKNOWN"
                result["degraded_mode_success_rate"] = 0.0
                result["failed_transactions"] = 1
                result["error"] = "Transfer did not complete under packet loss scenario"
                return result

            result["transfer_state"] = final_transfer.get("state")

            success_states = {"COMPLETED", "FINISHED", "DEPROVISIONED"}
            if final_transfer.get("state") in success_states:
                result["success"] = True
                result["degraded_mode_success_rate"] = 1.0
                result["failed_transactions"] = 0
            else:
                result["degraded_mode_success_rate"] = 0.0
                result["failed_transactions"] = 1
                result["error"] = (
                    final_transfer.get("errorDetail")
                    or f"Transfer ended in state={final_transfer.get('state')}"
                )

            return result

        except Exception as exc:
            result["retry_success_rate"] = 0.0
            result["degraded_mode_success_rate"] = 0.0
            result["failed_transactions"] = 1
            result["error"] = str(exc)
            return result

        finally:
            try:
                toxiproxy.clear_toxics(protocol_proxy_name)
            except Exception:
                pass
            try:
                toxiproxy.clear_toxics(public_proxy_name)
            except Exception:
                pass
