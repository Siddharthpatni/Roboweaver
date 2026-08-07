"""CI acceptance: require an upstream mlir-opt run over one real RoboIR compile."""

from roboweaver.compiler import SkillCompiler


def main() -> None:
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the red cube", verbose=False,
    )
    evidence = result.native_mlir
    if evidence is None or evidence.status != "succeeded":
        raise SystemExit(f"native MLIR acceptance failed: {evidence}")
    if not evidence.output_sha256 or not evidence.version or not evidence.executable:
        raise SystemExit(f"native MLIR evidence is incomplete: {evidence}")
    print(evidence.to_dict())


if __name__ == "__main__":
    main()
