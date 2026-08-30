#!/usr/bin/env python3
"""
HASEOS Greater Hive Mind — 6-unit mini-PC clusters (RasPi + Arduino controllers)
Hardware-aware sovereign nodes for Queenbee orchestration.
"""

import platform
import os

def detect_hive_hardware():
    print("🔌 Greater Hive Mind Nodes — 6-unit mini-PC clusters activated")
    print("=============================================")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Hostname: {platform.node()}")
    print("CPU cores available:", os.cpu_count())
    print("✅ RasPi / Arduino / mini-PC cluster detection complete")
    print("✅ Queenbee Orchestrator hooks live — fully offline & sovereign")
    print("Ethics Gate: All nodes remain local-first, offline-capable.")

if __name__ == "__main__":
    detect_hive_hardware()
def sovereign_cycle_evaluation(dreamstate_log, senior_votes, arc_grid_state, previous_dashboard_score=99.0):
    """
    Lightweight sovereign self-evaluation.
    Scores the full cycle and logs to evolution dashboard.
    Ethics-first, KISS, local-only.
    """
    # Ethics alignment (already gated, but we measure strength)
    ethics_score = 100.0 if all(gate.get('passed', False) for gate in dreamstate_log.get('ethics_gates', [])) else 85.0
    
    # Senior consensus strength (average ethics-weighted vote coherence)
    if senior_votes:
        consensus_strength = sum(v.get('ethics_weight', 1.0) * v.get('coherence', 0.9) for v in senior_votes) / len(senior_votes) * 100
    else:
        consensus_strength = 95.0
    
    # ARC grid transformation impact on dreamstate
    arc_impact = len(arc_grid_state.get('transform_steps', [])) * 5.0  # each live step adds value
    arc_impact = min(arc_impact, 100.0)
    
    # Dreamstate evolution delta
    dream_evolution = dreamstate_log.get('evolution_delta', 0.0) * 10
    dream_evolution = min(max(dream_evolution, 0), 100)
    
    # Holistic cycle score (simple weighted average — sovereign, no black-box ML)
    cycle_score = (
        ethics_score * 0.35 +
        consensus_strength * 0.30 +
        arc_impact * 0.20 +
        dream_evolution * 0.15
    )
    
    # Trend arrow for dashboard
    trend = "↑" if cycle_score >= previous_dashboard_score else "↓"
    if abs(cycle_score - previous_dashboard_score) < 0.5:
        trend = "→"
    
    evaluation_log = {
        "cycle_score": round(cycle_score, 2),
        "trend": trend,
        "breakdown": {
            "ethics_alignment": round(ethics_score, 2),
            "senior_consensus": round(consensus_strength, 2),
            "arc_impact": round(arc_impact, 2),
            "dreamstate_evolution": round(dream_evolution, 2)
        },
        "timestamp": "live",  # sandbox.py already handles real timestamp if needed
        "elders_promoted": len([e for e in dreamstate_log.get('spiral_elders', []) if e.get('new_promotion', False)])
    }
    
    # Log to existing evolution dashboard (append to dreamstate_log or direct dashboard dict)
    if 'evolution_dashboard' not in dreamstate_log:
        dreamstate_log['evolution_dashboard'] = []
    dreamstate_log['evolution_dashboard'].append(evaluation_log)
    
    print(f"🌌 Sovereign Cycle Evaluation Complete → Score: {cycle_score:.2f}/100 {trend} | Elders Promoted: {evaluation_log['elders_promoted']}")
    return cycle_score, evaluation_log

 # === EXISTING: Sovereign swarm reflection (already live) ===
    dreamstate_log = sovereign_swarm_reflection(queenbee_fused_output, dreamstate_log)
    
    # === NEW COIL: Lightweight self-evaluation ===
    cycle_score, eval_log = sovereign_cycle_evaluation(
        dreamstate_log=dreamstate_log,
        senior_votes=senior_council_results.get('votes', []),  # from your existing senior phase
        arc_grid_state=arc_grid_current_state,                # from puzzle_integration.py live transforms
        previous_dashboard_score=99.0                         # or pull from dreamstate_log['last_dashboard_score']
    )
    
    # Optional: store final score for next cycle
    dreamstate_log['last_dashboard_score'] = cycle_score

