from __future__ import annotations

import csv
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests


class EDCError(Exception):
    pass


class EDCManagementClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Api-Key": api_key,
                "Content-Type": "application/json",
            }
        )

    def _handle_response(self, response: requests.Response) -> Any:
        text = response.text.strip()

        if not response.ok:
            raise EDCError(
                f"HTTP {response.status_code} calling {response.request.method} "
                f"{response.request.url}: {text}"
            )

        if not text:
            return None

        try:
            return response.json()
        except Exception as exc:
            raise EDCError(f"Invalid JSON response: {text}") from exc

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.session.post(
            f"{self.base_url}{path}",
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def get(self, path: str) -> Any:
        response = self.session.get(
            f"{self.base_url}{path}",
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.session.put(
            f"{self.base_url}{path}",
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def delete(self, path: str) -> Any:
        response = self.session.delete(
            f"{self.base_url}{path}",
            timeout=self.timeout,
        )
        return self._handle_response(response)

    # ---- EDC Management API helpers ----

    def create_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/v3/assets", payload)

    def create_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/v3/policydefinitions", payload)

    def create_contract_definition(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/v3/contractdefinitions", payload)

    def request_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        # 对应 sample 中 /catalog/dataset/request
        return self.post("/v3/catalog/dataset/request", payload)

    def start_negotiation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/v3/contractnegotiations", payload)

    def get_negotiation(self, negotiation_id: str) -> dict[str, Any]:
        return self.get(f"/v3/contractnegotiations/{negotiation_id}")

    def start_transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/v3/transferprocesses", payload)

    def get_transfer(self, transfer_id: str) -> dict[str, Any]:
        return self.get(f"/v3/transferprocesses/{transfer_id}")


@dataclass
class MetricsRecorder:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def add(self, row: dict[str, Any]) -> None:
        self.rows.append(row)

    def write_csv(self, output_path: str | Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.rows:
            output_path.write_text("", encoding="utf-8")
            return

        fieldnames: list[str] = sorted(
            {key for row in self.rows for key in row.keys()}
        )

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.rows)


@contextmanager
def timer() -> Any:
    start = time.perf_counter()
    result = {"duration_s": None}
    try:
        yield result
    finally:
        result["duration_s"] = time.perf_counter() - start


def wait_until(
    fn: Callable[[], dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
    timeout_s: int = 60,
    interval_s: float = 2.0,
) -> dict[str, Any]:
    start = time.time()
    last_result: dict[str, Any] | None = None

    while time.time() - start < timeout_s:
        last_result = fn()
        if predicate(last_result):
            return last_result
        time.sleep(interval_s)

    raise TimeoutError(
        f"Polling timed out after {timeout_s}s. Last result={last_result}"
    )


def load_json_template(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _replace_in_obj(obj: Any, variables: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        return {k: _replace_in_obj(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_in_obj(v, variables) for v in obj]
    if isinstance(obj, str):
        replaced = obj
        for key, value in variables.items():
            replaced = replaced.replace(f"{{{{{key}}}}}", str(value))
        return replaced
    return obj


def render_template(path: str | Path, variables: dict[str, str]) -> dict[str, Any]:
    raw = load_json_template(path)
    return _replace_in_obj(raw, variables)


class ScenarioBase:
    scenario_name = "base"

    def __init__(self, config: dict[str, Any]):
        self.config = config

        self.provider = EDCManagementClient(
            base_url=config["provider_management_url"],
            api_key=config["api_key"],
            timeout=config.get("request_timeout_s", 30),
        )
        self.consumer = EDCManagementClient(
            base_url=config["consumer_management_url"],
            api_key=config["api_key"],
            timeout=config.get("request_timeout_s", 30),
        )

        self.provider_protocol_url = config["provider_protocol_url"]
        self.consumer_protocol_url = config["consumer_protocol_url"]
        self.provider_public_url = config.get("provider_public_url", "")

        self.poll_interval_s = float(config.get("poll_interval_s", 2.0))
        self.poll_timeout_s = int(config.get("poll_timeout_s", 120))

    def build_run_ids(self, run_index: int) -> dict[str, str]:
        exp_id = self.config["experiment_id"]
        unique_suffix = uuid.uuid4().hex[:8]
        return {
            "ASSET_ID": f"{exp_id}-asset-{run_index}-{unique_suffix}",
            "POLICY_ID": f"{exp_id}-policy-{run_index}-{unique_suffix}",
            "CONTRACT_DEFINITION_ID": f"{exp_id}-contract-{run_index}-{unique_suffix}",
            "PROVIDER_PROTOCOL_URL": self.provider_protocol_url,
            "CONSUMER_PROTOCOL_URL": self.consumer_protocol_url,
            "PROVIDER_PUBLIC_URL": self.provider_public_url,
            "ASSET_BASE_URL": self.config.get("asset_base_url", ""),
        }

    def get_policy_template_path(self) -> str:
        return self.config["policy_template_path"]

    def create_common_resources(self, run_ids: dict[str, str]) -> dict[str, Any]:
        asset_payload = render_template(
            self.config["asset_template_path"],
            run_ids,
        )
        policy_payload = render_template(
            self.get_policy_template_path(),
            run_ids,
        )
        contract_payload = render_template(
            self.config["contract_definition_template_path"],
            run_ids,
        )

        asset_resp = self.provider.create_asset(asset_payload)
        policy_resp = self.provider.create_policy(policy_payload)
        contract_resp = self.provider.create_contract_definition(contract_payload)

        return {
            "asset_response": asset_resp,
            "policy_response": policy_resp,
            "contract_definition_response": contract_resp,
        }

    def extract_offer_id(self, dataset_response: dict[str, Any]) -> str:
        """
        尽量兼容几种 EDC sample 常见返回结构：
        1. dataset_response["dcat:dataset"]["odrl:hasPolicy"]["@id"]
        2. dataset_response["odrl:hasPolicy"]["@id"]
        3. dataset_response["dcat:dataset"] 为 list 时，取第一个 dataset
        """
        dataset = dataset_response.get("dcat:dataset", dataset_response)

        if isinstance(dataset, list) and dataset:
            dataset = dataset[0]

        if isinstance(dataset, dict):
            policy = dataset.get("odrl:hasPolicy")
            if isinstance(policy, dict) and policy.get("@id"):
                return policy["@id"]

        top_policy = dataset_response.get("odrl:hasPolicy")
        if isinstance(top_policy, dict) and top_policy.get("@id"):
            return top_policy["@id"]

        raise EDCError(
            f"Cannot extract contract offer id from dataset response: {dataset_response}"
        )

    def extract_agreement_id(self, negotiation_response: dict[str, Any]) -> str | None:
        """
        兼容几种常见的 EDC negotiation 查询结果：
        - contractAgreementId
        - agreementId
        - contractAgreement.@id
        - contractAgreement.id
        """
        for key in ("contractAgreementId", "agreementId"):
            if key in negotiation_response and negotiation_response[key]:
                return negotiation_response[key]

        agreement = negotiation_response.get("contractAgreement")
        if isinstance(agreement, dict):
            if agreement.get("@id"):
                return agreement["@id"]
            if agreement.get("id"):
                return agreement["id"]

        return None

    def wait_for_negotiation(self, negotiation_id: str) -> dict[str, Any]:
        def _fetch() -> dict[str, Any]:
            return self.consumer.get_negotiation(negotiation_id)

        def _done(resp: dict[str, Any]) -> bool:
            state = resp.get("state", "")
            return state in {"FINALIZED", "CONFIRMED", "TERMINATED", "DECLINED"}

        return wait_until(
            _fetch,
            _done,
            timeout_s=self.poll_timeout_s,
            interval_s=self.poll_interval_s,
        )

    def wait_for_transfer(self, transfer_id: str) -> dict[str, Any]:
        def _fetch() -> dict[str, Any]:
            return self.consumer.get_transfer(transfer_id)

        def _done(resp: dict[str, Any]) -> bool:
            state = resp.get("state", "")
            return state in {
                "COMPLETED",
                "FINISHED",
                "TERMINATED",
                "DEPROVISIONED",
                "FAILED",
            }

        return wait_until(
            _fetch,
            _done,
            timeout_s=self.poll_timeout_s,
            interval_s=self.poll_interval_s,
        )

    # ------------------------------------------------------------------
    # 统一指标口径 helper
    # ------------------------------------------------------------------

    def measure_catalog_request(
        self, dataset_request_payload: dict[str, Any]
    ) -> tuple[dict[str, Any], float]:
        """
        统一口径：
        catalog_request_latency_s =
        从 consumer 发起 dataset/catalog request 开始，
        到收到完整 dataset 响应为止。
        """
        with timer() as t:
            dataset_response = self.consumer.request_dataset(dataset_request_payload)
        return dataset_response, round(t["duration_s"], 6)

    def measure_contract_offer_negotiation(
        self, negotiation_payload: dict[str, Any]
    ) -> tuple[dict[str, Any], float]:
        """
        统一口径：
        contract_offer_negotiation_latency_s =
        从 consumer 发起 POST /contractnegotiations 开始，
        到收到 negotiation_id 为止。
        """
        with timer() as t:
            negotiation_response = self.consumer.start_negotiation(negotiation_payload)
        return negotiation_response, round(t["duration_s"], 6)

    def measure_contract_agreement(
        self, negotiation_id: str
    ) -> tuple[dict[str, Any], float]:
        """
        统一口径：
        contract_agreement_latency_s =
        从开始轮询 negotiation 状态开始，
        到 agreement 可被提取出来（或 negotiation 结束）为止。
        """
        with timer() as t:
            final_negotiation = self.wait_for_negotiation(negotiation_id)
        return final_negotiation, round(t["duration_s"], 6)

    def measure_transfer_initiation(
        self, transfer_payload: dict[str, Any]
    ) -> tuple[dict[str, Any], float]:
        """
        统一口径：
        transfer_initiation_latency_s =
        从 consumer 发起 POST /transferprocesses 开始，
        到收到 transfer_id 为止。
        """
        with timer() as t:
            transfer_response = self.consumer.start_transfer(transfer_payload)
        return transfer_response, round(t["duration_s"], 6)

    def measure_transfer_completion(
        self, transfer_id: str
    ) -> tuple[dict[str, Any], float]:
        """
        统一口径：
        transfer_completion_latency_s =
        从 transfer_id 已经拿到之后开始，
        到 transfer 进入最终状态（成功/失败）为止。

        注意：
        baseline、network delay、packet loss、restart、interruption
        都必须用这个同一口径，才能直接比较。
        """
        with timer() as t:
            final_transfer = self.wait_for_transfer(transfer_id)
        return final_transfer, round(t["duration_s"], 6)

    def compute_control_plane_total_latency(
        self,
        catalog_request_latency_s: float | None = None,
        contract_offer_negotiation_latency_s: float | None = None,
        contract_agreement_latency_s: float | None = None,
        transfer_initiation_latency_s: float | None = None,
    ) -> float:
        values = [
            catalog_request_latency_s,
            contract_offer_negotiation_latency_s,
            contract_agreement_latency_s,
            transfer_initiation_latency_s,
        ]
        total = sum(v for v in values if isinstance(v, (int, float)))
        return round(total, 6)

    def compute_transfer_end_to_end_latency(
        self,
        transfer_initiation_latency_s: float | None,
        transfer_completion_latency_s: float | None,
    ) -> float | None:
        """
        统一口径：
        transfer_end_to_end_latency_s =
        transfer_initiation_latency_s + transfer_completion_latency_s
        """
        if not isinstance(transfer_initiation_latency_s, (int, float)):
            return None
        if not isinstance(transfer_completion_latency_s, (int, float)):
            return None

        return round(
            float(transfer_initiation_latency_s)
            + float(transfer_completion_latency_s),
            6,
        )

    def run_once(self, run_index: int) -> dict[str, Any]:
        raise NotImplementedError
