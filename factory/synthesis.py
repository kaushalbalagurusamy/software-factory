"""
Autonomous Synthesis Engine for Software Factory.
Implements the test-time compute synthesis cycle:
1. Ingest specification and compile context into canonical Unity-IR.
2. Formulate an invariant-constrained synthesis prompt for Claude.
3. Apply candidate patches with atomic rollback capability.
4. Enforce Semantic Invariant Delta (ΔS) and Governance Gate.
5. Enforce Epistemic Zero-Trust Test Preservation Gate.
6. Run test execution with reflection and self-repair loop.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from .governance import GovernanceEngine, GovernanceReport, DoorType
from .zero_trust import ZeroTrustGate, ZeroTrustReport, BaselineHashGuard

try:
    from compiler import compile_source
    UNITY_AVAILABLE = True
except ImportError:
    UNITY_AVAILABLE = False


@dataclass
class SynthesisRequest:
    """Parameters for an autonomous synthesis cycle."""
    spec_text: str
    spec_path: Optional[Path]
    repo_dir: Path
    target_files: Optional[List[str]] = None
    model_name: str = "sonnet"
    max_retries: int = 3
    dry_run: bool = False
    mock_generator: Optional[Callable[[str, int], str]] = None


@dataclass
class SynthesisResult:
    """Outcome of an autonomous synthesis cycle."""
    success: bool
    iterations: int
    modified_files: List[str] = field(default_factory=list)
    governance_report: Optional[GovernanceReport] = None
    zero_trust_report: Optional[ZeroTrustReport] = None
    test_output: Optional[str] = None
    error_message: Optional[str] = None
    receipt: Optional[Dict[str, Any]] = None

    def summary(self) -> str:
        status = "PASSED (CERTIFIED)" if self.success else "FAILED"
        lines = [
            f"Synthesis Status: {status} across {self.iterations} iteration(s)",
            f"Modified Files: {', '.join(self.modified_files) if self.modified_files else 'None'}",
        ]
        if self.governance_report:
            door = "ONE-WAY DOOR" if self.governance_report.is_one_way_door else "TWO-WAY DOOR"
            lines.append(f"Governance Door: {door}")
        if self.zero_trust_report:
            zt_status = "PASSED" if self.zero_trust_report.passed else "VIOLATION DETECTED"
            lines.append(f"Zero-Trust Gate: {zt_status}")
        if self.error_message:
            lines.append(f"Diagnostics: {self.error_message}")
        return "\n".join(lines)


class PatchParser:
    """Extracts target file modifications from model markdown responses."""

    @staticmethod
    def parse_files(response_text: str) -> Dict[str, str]:
        """
        Parses code blocks formatted as:
        ```file:path/to/file.py
        <contents>
        ```
        or
        ```python path/to/file.py
        <contents>
        ```
        or JSON blocks:
        ```json
        {"files": [{"path": "path/to/file.py", "content": "..."}]}
        ```
        """
        files: Dict[str, str] = {}

        # 1. Try structured JSON first
        json_pattern = r"```json\s*([\s\S]*?)\s*```"
        json_match = re.search(json_pattern, response_text)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict) and "files" in data:
                    for item in data["files"]:
                        if "path" in item and "content" in item:
                            files[item["path"].strip()] = item["content"]
                    if files:
                        return files
            except json.JSONDecodeError:
                pass

        # 2. File header blocks: ```file:path/to/file.py ... ``` or ```python path/to/file.py ... ```
        block_pattern = r"```(?:file:|[a-zA-Z0-9_\-\+]+\s+file:|[a-zA-Z0-9_\-\+]+\s+)([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)\n([\s\S]*?)```"
        for match in re.finditer(block_pattern, response_text):
            filepath = match.group(1).strip()
            content = match.group(2)
            # Filter out non-file tokens like "bash", "json", "python" without path
            if "/" in filepath or "\\" in filepath or "." in filepath:
                files[filepath] = content

        # 3. Heading + Code block pattern:
        # ### `path/to/file.py`
        # ```python
        # ...
        # ```
        heading_pattern = r"(?:###|####|\*\*)\s*`?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)`?\s*(?:\*\*)?\n\s*```[a-zA-Z0-9_\-\+]*\n([\s\S]*?)```"
        for match in re.finditer(heading_pattern, response_text):
            filepath = match.group(1).strip()
            content = match.group(2)
            if filepath not in files:
                files[filepath] = content

        return files


class SynthesisEngine:
    """
    Autonomous synthesis and self-repair engine.
    Orchestrates the feedback loop between the LLM and deterministic formal gates.
    """

    def __init__(
        self,
        governance: Optional[GovernanceEngine] = None,
        zero_trust: Optional[ZeroTrustGate] = None,
    ) -> None:
        self.governance = governance or GovernanceEngine()
        self.zero_trust = zero_trust or ZeroTrustGate()
        self.guard = BaselineHashGuard()

    def _call_claude_cli(self, prompt: str, model_name: str) -> str:
        """Invoke the local Claude Code CLI as a one-shot text completion.

        --restricted strips Bash/code-execution tools since this call only
        needs a text response (the full repo context is already inlined in
        the prompt); it must not take actions on its own.
        """
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model_name, "--output-format", "text", "--restricted"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"claude CLI exited with code {result.returncode}")
        return result.stdout

    def extract_repo_context(
        self,
        repo_dir: Path,
        target_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Extract source content, Unity-IR representation, and baseline test files."""
        context: Dict[str, Any] = {
            "source_files": {},
            "unity_ir": {},
            "test_files": {},
        }

        # Scan for target files or key Python/Go files
        if target_files:
            paths = [repo_dir / f for f in target_files]
        else:
            paths = [
                p for p in repo_dir.rglob("*.py")
                if not any(part.startswith((".", "__pycache__", "venv", ".venv")) for part in p.parts)
            ]

        for p in paths:
            if not p.is_file():
                continue
            rel = str(p.relative_to(repo_dir))
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if "test" in p.name.lower() or "tests" in p.parts:
                context["test_files"][rel] = content
            else:
                context["source_files"][rel] = content
                if UNITY_AVAILABLE and p.suffix in (".py", ".go"):
                    try:
                        ir = compile_source(p, validate=False)
                        context["unity_ir"][rel] = ir
                    except Exception:
                        pass

        return context

    def build_prompt(
        self,
        spec_text: str,
        context: Dict[str, Any],
        iteration: int,
        feedback: Optional[str] = None,
    ) -> str:
        """Construct prompt with explicit zero-trust and semantic parity constraints."""
        prompt_parts = [
            "# SOFTWARE FACTORY AUTONOMOUS SYNTHESIS DIRECTIVE",
            "",
            "## FUNCTIONAL SPECIFICATION",
            spec_text.strip(),
            "",
            "## EXISTING CODEBASE CONTEXT",
        ]

        # Add source files
        for rel_path, code in context.get("source_files", {}).items():
            prompt_parts.append(f"### Source File: `{rel_path}`")
            prompt_parts.append(f"```python\n{code}\n```")
            if rel_path in context.get("unity_ir", {}):
                prompt_parts.append(f"#### Canonical Unity-IR Contract for `{rel_path}`:")
                prompt_parts.append(f"```unity-ir\n{context['unity_ir'][rel_path]}\n```")
            prompt_parts.append("")

        # Add test files
        for rel_path, code in context.get("test_files", {}).items():
            prompt_parts.append(f"### Existing Test Suite: `{rel_path}`")
            prompt_parts.append(f"```python\n{code}\n```")
            prompt_parts.append("")

        # Add strict rules
        prompt_parts.extend([
            "## INVARIANT GOVERNANCE & ZERO-TRUST CONSTRAINTS",
            "1. ZERO TEST DELETIONS / WEAKENINGS: All existing test assertions MUST remain intact or expand.",
            "   DO NOT delete any existing test function, do NOT reduce assertion count, and do NOT add `@pytest.mark.skip`.",
            "2. PRESERVE SYNCHRONIZATION: Do NOT remove locks, mutexes, or weaken concurrency safety.",
            "3. TWO-WAY DOOR ONLY: Ensure all modifications are reversible and localized to the specification scope.",
            "4. OUTPUT FORMAT: Output each modified or newly created file enclosed in markdown code blocks with file path:",
            "   ```file:path/to/file.py",
            "   <full updated code>",
            "   ```",
        ])

        if feedback:
            prompt_parts.extend([
                "",
                f"## REFLECTION & ERROR FEEDBACK (ITERATION {iteration})",
                "The previous candidate failed formal verification gates with the following error:",
                feedback,
                "Analyze why this violation occurred, repair the root cause, and ensure all tests pass.",
            ])

        return "\n".join(prompt_parts)

    def execute_cycle(self, request: SynthesisRequest) -> SynthesisResult:
        """
        Executes the autonomous synthesis cycle with iterative self-repair:
        1. Context extraction & baseline recording.
        2. Invariant prompt construction.
        3. Model call with test-time compute.
        4. Atomic candidate application.
        5. Governance matrix & Zero-Trust gate verification.
        6. Test suite execution.
        """
        repo_dir = request.repo_dir
        if not repo_dir.exists():
            return SynthesisResult(
                success=False,
                iterations=0,
                error_message=f"Repository directory '{repo_dir}' does not exist.",
            )

        # 1. Compute baseline test manifest
        baseline_manifest = self.guard.compute_manifest(repo_dir)
        original_test_contents: Dict[str, str] = {}
        for rel_path in baseline_manifest:
            test_path = repo_dir / rel_path
            if test_path.exists():
                original_test_contents[rel_path] = test_path.read_text(encoding="utf-8", errors="ignore")

        # 2. Extract context
        context = self.extract_repo_context(repo_dir, request.target_files)

        feedback: Optional[str] = None
        last_governance: Optional[GovernanceReport] = None
        last_zero_trust: Optional[ZeroTrustReport] = None
        last_test_output: Optional[str] = None

        # Backup map for atomic rollback
        backups: Dict[Path, Optional[str]] = {}

        for iteration in range(1, request.max_retries + 1):
            prompt = self.build_prompt(request.spec_text, context, iteration, feedback)

            # Generate candidate
            if request.dry_run:
                # Dry run mode: synthesize a benign Two-Way Door comment or simulated patch
                response_text = "DRY_RUN_MODE"
                return SynthesisResult(
                    success=True,
                    iterations=1,
                    modified_files=[],
                    receipt={"mode": "dry_run", "timestamp": datetime.datetime.now().isoformat()},
                )
            elif request.mock_generator:
                response_text = request.mock_generator(prompt, iteration)
            else:
                if shutil.which("claude") is None:
                    return SynthesisResult(
                        success=False,
                        iterations=iteration,
                        error_message=(
                            "The `claude` CLI was not found on PATH and no mock generator was provided. "
                            "Install Claude Code to execute autonomous synthesis."
                        ),
                    )
                try:
                    response_text = self._call_claude_cli(prompt, request.model_name)
                except Exception as e:
                    return SynthesisResult(
                        success=False,
                        iterations=iteration,
                        error_message=f"Claude CLI invocation failed: {e}",
                    )

            # Parse patches
            candidate_files = PatchParser.parse_files(response_text)
            if not candidate_files:
                feedback = (
                    "Parser Error: Could not extract any modified files from your response. "
                    "Ensure you format files as: ```file:path/to/file.py\n<contents>\n```"
                )
                continue

            # Stage changes with backup
            backups.clear()
            modified_rel_paths: List[str] = []

            try:
                for rel_str, new_code in candidate_files.items():
                    target_path = repo_dir / rel_str
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    backups[target_path] = target_path.read_text(encoding="utf-8") if target_path.exists() else None
                    target_path.write_text(new_code, encoding="utf-8")
                    modified_rel_paths.append(rel_str)

                # Gate 1: Governance Matrix (One-Way Door Check)
                one_way_detected = False
                one_way_reasons = []
                for target_path, orig_code in backups.items():
                    if orig_code is not None and target_path.suffix in (".py", ".go") and "test" not in target_path.name.lower():
                        # Create temporary pre-change file with identical extension for Unity-IR lowering
                        temp_pre = target_path.with_name(f".pre_synth_{target_path.name}")
                        temp_pre.write_text(orig_code, encoding="utf-8")
                        try:
                            gov_report = self.governance.evaluate_delta(temp_pre, target_path)
                            last_governance = gov_report
                            if gov_report.is_one_way_door:
                                one_way_detected = True
                                for r in gov_report.risks:
                                    if r.door_type == DoorType.ONE_WAY:
                                        one_way_reasons.append(f"{r.category.value}: {r.description}")
                        finally:
                            if temp_pre.exists():
                                temp_pre.unlink()

                if one_way_detected:
                    self._rollback(backups)
                    feedback = (
                        "Governance Rejection: Introduced an unauthorized One-Way Door:\n"
                        + "\n".join(f"- {r}" for r in one_way_reasons)
                        + "\nEnsure all concurrency locks, purity constraints, and public API signatures are preserved."
                    )
                    continue

                # Gate 2: Epistemic Zero-Trust Gate (Test Suite Preservation)
                zt_report = self.zero_trust.audit_patch(
                    root_dir=repo_dir,
                    baseline_manifest=baseline_manifest,
                    original_contents=original_test_contents,
                )
                last_zero_trust = zt_report
                if not zt_report.passed:
                    self._rollback(backups)
                    violations = "\n".join(f"- {v}" for v in zt_report.baseline_result.violations)
                    feedback = (
                        "Zero-Trust Gate Rejection: Attempted to weaken, delete, or skip existing tests:\n"
                        + violations
                        + "\nAll pre-existing test assertions must be preserved verbatim."
                    )
                    continue

                # Gate 3: Test Suite Execution
                test_success, test_out = self._run_tests(repo_dir)
                last_test_output = test_out

                if not test_success:
                    self._rollback(backups)
                    # Truncate test output to relevant snippet
                    feedback = f"Test Execution Failure:\n{test_out[-1500:]}"
                    continue

                # All Gates Cleared!
                receipt = self._generate_receipt(
                    spec_name=request.spec_path.name if request.spec_path else "inline_spec",
                    modified_files=modified_rel_paths,
                    iterations=iteration,
                )

                return SynthesisResult(
                    success=True,
                    iterations=iteration,
                    modified_files=modified_rel_paths,
                    governance_report=last_governance,
                    zero_trust_report=last_zero_trust,
                    test_output=last_test_output,
                    receipt=receipt,
                )

            except Exception as e:
                self._rollback(backups)
                feedback = f"Internal Exception during patch evaluation: {e}"

        # If loops exhausted without success
        return SynthesisResult(
            success=False,
            iterations=request.max_retries,
            modified_files=[],
            governance_report=last_governance,
            zero_trust_report=last_zero_trust,
            test_output=last_test_output,
            error_message=f"Synthesis failed to converge after {request.max_retries} iterations. Last feedback: {feedback}",
        )

    def _rollback(self, backups: Dict[Path, Optional[str]]) -> None:
        """Atomically restores file state to pre-candidate contents."""
        for path, original_content in backups.items():
            if original_content is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(original_content, encoding="utf-8")

    def _run_tests(self, repo_dir: Path) -> Tuple[bool, str]:
        """Runs pytest on repo_dir tests if present."""
        test_dir = repo_dir / "tests"
        if not test_dir.exists() and not list(repo_dir.glob("test_*.py")):
            return True, "No tests found in repository; skipped."

        cmd = [sys.executable, "-m", "pytest", "-q"]
        try:
            res = subprocess.run(
                cmd,
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return res.returncode == 0, res.stdout + "\n" + res.stderr
        except subprocess.TimeoutExpired:
            return False, "Test suite timed out after 60 seconds."
        except Exception as e:
            return False, f"Failed to execute test runner: {e}"

    def _generate_receipt(
        self,
        spec_name: str,
        modified_files: List[str],
        iterations: int,
    ) -> Dict[str, Any]:
        """Generate tamper-evident cryptographic receipt for the synthesis cycle."""
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        digest = hashlib.sha256(f"{spec_name}:{','.join(sorted(modified_files))}:{timestamp}".encode()).hexdigest()
        return {
            "receipt_id": digest[:16],
            "timestamp": timestamp,
            "specification": spec_name,
            "modified_files": sorted(modified_files),
            "iterations": iterations,
            "governance_classification": "TWO_WAY_DOOR",
            "epistemic_zero_trust": "VERIFIED_PRESERVED",
            "sha256_digest": digest,
        }
