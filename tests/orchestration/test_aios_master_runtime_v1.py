import ast
import json
from pathlib import Path

import pytest

from automation.orchestration.aios_master_runtime_v1 import AIOSMasterRuntime, ResumeRejected, STAGES
from automation.orchestration.platform import OrchestrationPlatform


def runtime(tmp_path: Path) -> AIOSMasterRuntime:
    active = AIOSMasterRuntime(".")
    active.state_path = tmp_path / "master-runtime-v1.json"
    return active


def test_plan_is_deterministic_and_complete(tmp_path: Path) -> None:
    active = runtime(tmp_path)
    first = active.execute(command="plan")
    second = active.execute(command="plan")
    assert first["normalized_fingerprint"] == second["normalized_fingerprint"]
    assert [item["stage_id"] for item in first["stages"]] == list(STAGES)
    assert active.validate_state(first)["status"] == "PASS"
    assert not any(first["protected_actions"].values())
    assert first["composition"].keys() >= {
        "spine", "braid", "queue", "dispatcher", "packet_builder",
        "packet_resolver", "autonomy_governor", "countdown",
    }


def test_checkpoint_resume_and_incompatible_head(tmp_path: Path) -> None:
    active = runtime(tmp_path)
    active.execute(command="run", checkpoint=True)
    assert active.resume()["status"] == "PASS"
    saved = json.loads(active.state_path.read_text())
    saved["identity"]["head"] = "0" * 40
    active.state_path.write_text(json.dumps(saved))
    with pytest.raises(ResumeRejected, match="INCOMPATIBLE_HEAD"):
        active.resume()


def test_platform_integration_and_schema() -> None:
    state = OrchestrationPlatform(".").master_runtime(command="plan")
    schema = json.loads(Path("schemas/orchestration/aios_master_runtime_v1.schema.json").read_text())
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator(schema).validate(state)


def test_repository_local_schema_contract() -> None:
    state = OrchestrationPlatform(".").master_runtime(command="plan")
    assert state["schema"] == "AIOS_MASTER_RUNTIME.v1"
    assert len(state["stages"]) == 13
    assert all(value is False for value in state["permissions"].values())


def test_runtime_has_no_arbitrary_shell_execution_surface() -> None:
    tree = ast.parse(Path("automation/orchestration/aios_master_runtime_v1.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(call.func, ast.Attribute)
        and call.func.attr in {"system", "popen"}
        for call in calls
    )
    assert not any(
        keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
        for call in calls for keyword in call.keywords
    )


def test_duplicate_capability_owner_fails_closed(tmp_path: Path) -> None:
    active = runtime(tmp_path)
    source, test = next(iter(active.CAPABILITIES.values()))
    active.CAPABILITIES = {"first": (source, test), "duplicate": (source, test)}
    with pytest.raises(Exception, match="DUPLICATE_CAPABILITY_OWNER"):
        active.capabilities()
