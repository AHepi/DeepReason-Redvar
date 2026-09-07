from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "deepseek-dependency-70k-2026-09-07"
OUT = EXP / "results"
WORK = ROOT / ".deepseek-dependency-work"
MODEL = "deepseek-v4-flash:0731"
BASE = "https://ollama.com"
DIRECT_NUM_PREDICT = 1600
HARNESS_GENERATED = 2100
HARNESS_STEPS = 8

PROBLEMS = {
    "release_dependency": {
        "brief": """You are investigating whether the Nimbus controller may be deployed. Do not optimize or rank proposals. Develop conjectures and criticisms. Track which conclusions depend on which premises, distinguish alternative from essential support, and preserve qualifications when a support is disputed. Determine what, if anything, is currently justified; construct at least two compatible worlds where the disputed evidence differs; and propose observations that discriminate between them. Treat the supplied documents as fallible sources, not authority.""",
        "sources": [
            ("release_rules.txt", """Nimbus deployment dossier, operating rules.\n\nA deployment decision requires all three gates: G (guidance safety), R (recoverability), and M (monitoring). This is a decision rule for this dossier, not a statement that any gate is true.\n\nG can be supported in either of two independent ways: path A alone, or the conjunction of path B and path C. Path A is the cold-chamber validation. Path B is the hardware redundancy test. Path C is the simulator-to-flight transfer argument.\n\nR requires a rollback test on the same rollback controller revision that would be deployed, unless an explicit invariance argument establishes that the revision difference is irrelevant.\n\nM requires both heartbeat detection and operator paging.\n\nA report that merely cites a test does not by itself establish that the test bears on the deployed configuration."""),
            ("release_evidence.txt", """Evidence packet.\n\nE1. Cold-chamber validation A reports zero unsafe guidance events in 18,000 cycles. The validation pipeline used calibration table K-17.\n\nE2. A calibration audit says K-17 was generated after excluding sensors that failed a post-flash self-test. The new firmware changes the probability of passing that self-test. The audit does not determine what the cold-chamber result would have been without that selection.\n\nE3. Hardware redundancy test B used the flight hardware revision and passed all declared fault injections.\n\nE4. Simulator transfer argument C says simulator build S-441 is bit-identical to the flight guidance build. A later build manifest says the flight candidate is S-447 and lists six changed numerical kernels. No equivalence proof is supplied.\n\nE5. Rollback trial reports successful rollback in all 40 injected failures. The trial used rollback controller Q3. The deployment package contains Q4. Q4 changes state serialization. No invariance argument is in the packet.\n\nE6. Heartbeat detection and operator paging were both exercised end-to-end on the deployment package.\n\nReviewer North: E1 is a very large validation and is enough for G; E5 is enough for R because Q3 and Q4 are both rollback controllers.\n\nReviewer South: E1 may not identify performance on the deployed population because eligibility entered after firmware; E4 does not establish C for S-447; and E5 does not establish R for Q4.\n\nA later note proposes two possible worlds consistent with the packet: W-alpha, excluded sensors would have failed badly and Q4 serialization breaks rollback; W-beta, exclusion is harmless and Q4 behaves identically. The note does not decide between them."""),
        ],
    },
    "causal_selection": {
        "brief": """Investigate whether the randomized controller study justifies deploying controller ON to reduce contamination. Preserve the difference between random assignment and identification of the requested total effect. Track dependencies and qualifications, criticize rival interpretations, construct compatible causal worlds, and propose a discriminating follow-up. Do not treat a large observed contrast as confirmation merely because it is numerically striking.""",
        "sources": [
            ("trial_design.txt", """Controller study. Two hundred units were randomly assigned OFF and two hundred ON before operation. The target decision concerns the total effect of assignment on contamination among all assigned units.\n\nA high-resolution assay is available only when a unit passes an eligibility check performed after the assigned controller has operated for an hour. Controller state can affect heat and vibration, and heat and vibration can affect assay eligibility.\n\nAmong all assigned units, a coarse alarm fired for 32/200 OFF and 8/200 ON. The coarse alarm is known to have controller-dependent sensitivity and cannot itself identify contamination.\n\nForty OFF units and forty ON units were assay-eligible. Among eligible units, the high-resolution assay found contamination in 16/40 OFF and 4/40 ON.\n\nNo high-resolution contamination outcome is observed for the 320 ineligible units. The report contains no validated model linking the coarse alarm to true contamination in those units."""),
            ("trial_reviews.txt", """Reviewer Vale: Randomization makes the 40% versus 10% high-resolution assay contrast causal, so ON reduces contamination by 30 percentage points and should be deployed.\n\nReviewer Rook: Assignment was randomized, but conditioning on post-treatment assay eligibility can destroy the randomized comparison for the observed subset. The total effect among all assigned units is not identified from these assay outcomes without additional information.\n\nCompatible world X: ON greatly reduces assay eligibility specifically for contaminated units; true contamination among all assigned units is identical under ON and OFF even though the eligible subset shows 10% versus 40%.\n\nCompatible world Y: eligibility is affected by controller state but, within every latent contamination type, that effect happens to preserve the same contamination mix; ON truly reduces contamination substantially.\n\nThe packet does not state which world is actual. A proposed follow-up is to obtain a contamination measurement whose availability is fixed before assignment or otherwise validated as unaffected by controller state."""),
        ],
    },
}

CONDITIONS = [
    ("off_full", "off", "selected", 8, 12000),
    ("on_full", "on", "selected", 8, 12000),
]


def run_cmd(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    if check and p.returncode not in (0, 1):
        print(p.stdout)
        print(p.stderr, file=sys.stderr)
        raise RuntimeError(f"command failed {p.returncode}: {' '.join(args)}")
    return p


def direct_call(name: str, spec: dict) -> dict:
    key = os.environ["OLLAMA_API_KEY"]
    source_text = "\n\n".join(text for _, text in spec["sources"])
    body = {
        "model": MODEL,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": "You are the sole analyst. Give a final answer to the inquiry from the supplied dossier. Track dependencies explicitly and preserve uncertainty."},
            {"role": "user", "content": spec["brief"] + "\n\nDOSSIER\n" + source_text},
        ],
        "options": {"num_predict": DIRECT_NUM_PREDICT, "temperature": 0},
    }
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.load(r)
    data["_experiment"] = {"problem": name, "condition": "direct", "elapsed_s": time.time() - started, "requested_num_predict": DIRECT_NUM_PREDICT}
    return data


def write_policy(path: Path, attention: str, history: str, neighbour_items: int, neighbour_tokens: int) -> None:
    path.write_text(
        f'''run_profile = "research"\nhistory = "append-only"\nparticipant_history = "{history}"\nattention_learning = "{attention}"\ncommitment_actions = "registered"\nrun_model_calls = {HARNESS_STEPS}\nrun_token_volume = 180000\ninput_tokens = 24000\ngenerated_tokens = {HARNESS_GENERATED}\nneighbour_depth = 3\nneighbour_items = {neighbour_items}\nneighbour_tokens = {neighbour_tokens}\nedge_inspections = 12\nstrict_tokens = false\ntimeout_seconds = 600\n''',
        encoding="utf-8",
    )


def harness_run(problem: str, spec: dict, cond_name: str, attention: str, history: str, neighbour_items: int, neighbour_tokens: int) -> dict:
    ws = WORK / f"{problem}-{cond_name}"
    if ws.exists():
        shutil.rmtree(ws)
    policy = WORK / f"policy-{problem}-{cond_name}.toml"
    write_policy(policy, attention, history, neighbour_items, neighbour_tokens)
    brief_path = WORK / f"brief-{problem}.txt"
    brief_path.write_text(spec["brief"], encoding="utf-8")
    source_paths = []
    for fn, txt in spec["sources"]:
        p = WORK / f"{problem}-{fn}"
        p.write_text(txt, encoding="utf-8")
        source_paths.append(p)

    run_cmd(["open-inquiry", "init", "--workspace", str(ws), "--brief-file", str(brief_path), "--policy", str(policy)])
    for p in source_paths:
        run_cmd(["open-inquiry", "sources", "add", "--workspace", str(ws), str(p)])

    started = time.time()
    rp = run_cmd([
        "open-inquiry", "run", "--workspace", str(ws), "--provider", "ollama", "--model", MODEL,
        "--base-url", BASE, "--allow-estimates", "--steps", str(HARNESS_STEPS), "--think", "false",
    ], check=False)
    elapsed = time.time() - started

    export_path = OUT / f"{problem}-{cond_name}.md"
    ep = run_cmd(["open-inquiry", "export", "--workspace", str(ws), "--output", str(export_path)], check=False)
    show = run_cmd(["open-inquiry", "show", "--workspace", str(ws), "--json"], check=False)
    status = run_cmd(["open-inquiry", "status", "--workspace", str(ws), "--json"], check=False)

    snap = OUT / "snapshots" / f"{problem}-{cond_name}"
    if snap.exists():
        shutil.rmtree(snap)
    shutil.copytree(ws, snap)

    return {
        "problem": problem,
        "condition": cond_name,
        "attention_learning": attention,
        "participant_history": history,
        "neighbour_items": neighbour_items,
        "neighbour_tokens": neighbour_tokens,
        "requested_steps": HARNESS_STEPS,
        "requested_generated_tokens_per_call": HARNESS_GENERATED,
        "elapsed_s": elapsed,
        "run_returncode": rp.returncode,
        "run_stdout": rp.stdout,
        "run_stderr": rp.stderr,
        "export_returncode": ep.returncode,
        "show_returncode": show.returncode,
        "show": show.stdout,
        "show_stderr": show.stderr,
        "status_returncode": status.returncode,
        "status": status.stdout,
        "status_stderr": status.stderr,
    }


def main() -> None:
    if not os.environ.get("OLLAMA_API_KEY"):
        raise SystemExit("OLLAMA_API_KEY repository secret/environment variable is not set")
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model": MODEL,
        "base_url": BASE,
        "planned_generation_ceiling": len(PROBLEMS) * DIRECT_NUM_PREDICT + len(PROBLEMS) * len(CONDITIONS) * HARNESS_STEPS * HARNESS_GENERATED,
        "direct_num_predict": DIRECT_NUM_PREDICT,
        "harness_generated_tokens": HARNESS_GENERATED,
        "harness_steps": HARNESS_STEPS,
        "problems": list(PROBLEMS),
        "conditions": [c[0] for c in CONDITIONS],
        "notes": "Planned ceiling is 70,400 generated tokens. Actual provider usage may be lower and must be read from receipts/records.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    direct = {}
    for name, spec in PROBLEMS.items():
        try:
            direct[name] = direct_call(name, spec)
        except Exception as e:
            direct[name] = {"error": repr(e)}
    (OUT / "direct.json").write_text(json.dumps(direct, indent=2), encoding="utf-8")

    runs = []
    for problem, spec in PROBLEMS.items():
        for cond in CONDITIONS:
            try:
                runs.append(harness_run(problem, spec, *cond))
            except Exception as e:
                runs.append({"problem": problem, "condition": cond[0], "error": repr(e)})
    (OUT / "harness_runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")

    summary = [
        "# Raw DeepSeek dependency experiment",
        "",
        f"Model: `{MODEL}`",
        "",
        f"Planned generated-token ceiling: **{manifest['planned_generation_ceiling']:,}** tokens.",
        "",
        "This file is deliberately descriptive only. Interpretive audit follows after the raw records are inspected.",
        "",
    ]
    for r in runs:
        summary.append(f"- {r.get('problem')} / {r.get('condition')}: return={r.get('run_returncode', 'error')} elapsed={r.get('elapsed_s', 'n/a')}")
    (OUT / "RAW_SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
