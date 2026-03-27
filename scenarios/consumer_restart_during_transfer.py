from __future__ import annotations

import logging
import time

from scenarios.base import ScenarioBase, render_template, timer
from scripts.fault_injectors.process_faults import restart_process_by_port

logger = logging.getLogger(__name__)


class ConsumerRestartDuringTransferScenario(ScenarioBase):
    scenario_name = "consumer_restart_during_transfer"

    def run_once(self, run_index: int) -> dict[str, object]:
        result: dict[str, object] = {
            "scenario": self.scenario_name,
            "run_index": run_index,
            "success": False,
            "fault_type": "consumer_restart",
        }

        run_ids = self.build_run_ids(run_index)
        result.update(
            {
                "asset_id": run_ids["ASSET_ID"],
                "policy_id": run_ids["POLICY_ID"],
                "contract_definition_id": run_ids["CONTRACT_DEFINITION_ID"],
                "data_size_mb": self.config.get("data_size_mb", 1),
                "consumer_recovery_port": self.config.get("consumer_recovery_port", 29193),
                "consumer_restart_workdir": self.config.get("consumer_restart_workdir"),
            }
        )

        try:
            logger.info("Creating common resources")
            self.create_common_resources(run_ids)

            logger.info("Requesting dataset")
            dataset_request_payload = render_template(
                self.config["dataset_request_template_path"],
                run_ids,
            )
            with timer() as t_catalog:
                dataset_response = self.consumer.request_dataset(dataset_request_payload)
            result["catalog_request_latency_s"] = round(t_catalog["duration_s"], 6)

            offer_id = self.extract_offer_id(dataset_response)
            result["offer_id"] = offer_id

            logger.info("Starting negotiation")
            negotiation_vars = dict(run_ids)
            negotiation_vars["CONTRACT_OFFER_ID"] = offer_id
            negotiation_payload = render_template(
                self.config["negotiation_template_path"],
                negotiation_vars,
            )

            with timer() as t_negotiation:
                negotiation_response = self.consumer.start_negotiation(negotiation_payload)
            result["contract_offer_negotiation_latency_s"] = round(
                t_negotiation["duration_s"], 6
            )

            negotiation_id = negotiation_response["@id"]
            result["negotiation_id"] = negotiation_id

            logger.info("Waiting for agreement")
            with timer() as t_agreement:
                final_negotiation = self.wait_for_negotiation(negotiation_id)
            result["contract_agreement_latency_s"] = round(
                t_agreement["duration_s"], 6
            )
            result["negotiation_state"] = final_negotiation.get("state")

            agreement_id = self.extract_agreement_id(final_negotiation)
            if not agreement_id:
                result["failed_transactions"] = 1
                result["retry_success_rate"] = 0.0
                result["degraded_mode_success_rate"] = 0.0
                result["error"] = (
                    final_negotiation.get("errorDetail")
                    or "No contract agreement id found"
                )
                return result

            result["contract_agreement_id"] = agreement_id

            logger.info("Starting transfer")
            transfer_vars = dict(run_ids)
            transfer_vars["CONTRACT_AGREEMENT_ID"] = agreement_id
            transfer_payload = render_template(
                self.config["transfer_template_path"],
                transfer_vars,
            )

            with timer() as t_transfer_initiation:
                transfer_response = self.consumer.start_transfer(transfer_payload)
            result["transfer_initiation_latency_s"] = round(
                t_transfer_initiation["duration_s"], 6
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

            fault_delay_s = float(self.config.get("fault_injection_delay_s", 2))
            logger.info("Sleeping %.2fs before consumer restart fault injection", fault_delay_s)
            time.sleep(fault_delay_s)

            logger.info("Restarting consumer now")
            restart_info = restart_process_by_port(
                port=int(self.config.get("consumer_recovery_port", 29193)),
                start_command=self.config["consumer_restart_command"],
                host=self.config.get("consumer_recovery_host", "localhost"),
                down_timeout_s=int(self.config.get("consumer_down_timeout_s", 30)),
                up_timeout_s=int(self.config.get("consumer_up_timeout_s", 120)),
                workdir=self.config.get("consumer_restart_workdir"),
            )

            result["recovery_time_s"] = restart_info["recovery_time_s"]
            result["killed_pid"] = restart_info["killed_pid"]
            result["new_pid"] = restart_info["new_pid"]
            result["listening_pid"] = restart_info["listening_pid"]

            # ---- 观察恢复，而不是强制恢复成功 ----
            retry_attempts = int(self.config.get("retry_attempts", 3))
            retry_interval_s = float(self.config.get("retry_interval_s", 5.0))
            observation_timeout_s = int(self.config.get("post_fault_observation_timeout_s", 60))

            logger.info("Consumer restarted, observing transfer recovery")
            success_states = {"COMPLETED", "FINISHED", "DEPROVISIONED"}
            failure_states = {"FAILED", "TERMINATED"}

            final_transfer = None
            observed_state = None
            successful_observations = 0

            observation_start = time.perf_counter()
            deadline = time.time() + observation_timeout_s

            for attempt in range(retry_attempts):
                if time.time() >= deadline:
                    logger.warning("Observation deadline reached before all retry attempts")
                    break

                logger.info(
                    "Polling transfer recovery attempt %s/%s",
                    attempt + 1,
                    retry_attempts,
                )

                try:
                    transfer_snapshot = self.consumer.get_transfer(transfer_id)
                    state = transfer_snapshot.get("state")
                    observed_state = state
                    logger.info("Observed transfer state=%s", state)

                    if state in success_states:
                        final_transfer = transfer_snapshot
                        successful_observations += 1
                        break

                    if state in failure_states:
                        final_transfer = transfer_snapshot
                        break

                except Exception as exc:
                    logger.warning("Transfer polling failed: %s", exc)

                time.sleep(retry_interval_s)

            if final_transfer is None:
                logger.info("Final transfer snapshot lookup after observation window")
                try:
                    final_transfer = self.consumer.get_transfer(transfer_id)
                    observed_state = final_transfer.get("state")
                    logger.info("Final observed transfer state=%s", observed_state)
                except Exception as exc:
                    logger.warning("Final transfer lookup failed: %s", exc)

            completion_latency_s = time.perf_counter() - observation_start
            result["transfer_completion_latency_s"] = round(completion_latency_s, 6)
            result["transfer_end_to_end_latency_s"] = round(
                result["transfer_initiation_latency_s"] + result["transfer_completion_latency_s"],
                6,
            )

            result["retry_success_rate"] = round(
                successful_observations / max(retry_attempts, 1),
                6,
            )

            if final_transfer is not None:
                result["transfer_state"] = final_transfer.get("state")

            if final_transfer and final_transfer.get("state") in success_states:
                result["success"] = True
                result["failed_transactions"] = 0
                result["degraded_mode_success_rate"] = 1.0

                data_size_mb = float(self.config.get("data_size_mb", 1))
                completion_duration = max(float(result["transfer_completion_latency_s"]), 1e-9)
                result["throughput_mb_s"] = round(data_size_mb / completion_duration, 6)

            else:
                result["success"] = False
                result["failed_transactions"] = 1
                result["degraded_mode_success_rate"] = 0.0

                if final_transfer is None:
                    result["transfer_state"] = observed_state or "UNKNOWN"
                    result["error"] = "Transfer did not reach a terminal success state during observation window"
                else:
                    result["error"] = (
                        final_transfer.get("errorDetail")
                        or f"Transfer ended in state={final_transfer.get('state')}"
                    )

            return result

        except Exception as exc:
            result["failed_transactions"] = 1
            result["retry_success_rate"] = 0.0
            result["degraded_mode_success_rate"] = 0.0
            result["error"] = str(exc)
            return result
