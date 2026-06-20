# patch_violations.ps1
# Surgical fixes for remaining invariant violations after main reorganization.
# All moves go to NEW sub-directories within already-organized folders.
# Safe: Copy-verify-delete pattern used throughout.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }
$logPath = Join-Path $root "reorganize_log.txt"

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Add-Content -Path $logPath -Value $line
    Write-Host $line
}

function SM($srcRel, $dstRel) {
    $src = Join-Path $root $srcRel
    $dst = Join-Path $root $dstRel
    if (-not (Test-Path $src)) { Log "SKIP(no src): $srcRel"; return }
    if (Test-Path $dst) { Log "SKIP(dst exists): $dstRel"; return }
    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null; Log "MKDIR: $($dstDir.Substring($root.Length+1))" }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $ss = (Get-Item $src).Length; $ds = (Get-Item $dst).Length
    if ($ss -ne $ds) { Log "ERROR: Size mismatch $srcRel"; return }
    Remove-Item -LiteralPath $src -Force
    Log "MOVED: $srcRel -> $dstRel"
}

Log "=== Patching violations ==="

# ─── 1. outputs\ root (8 files -> move 5 residuals to analysis\positional\positional) ────
# The PDF stays (1 file). Move the 7 leftover CSVs/TEX files.
SM "outputs\positional_sign_stats.csv"              "outputs\analysis\positional\positional\positional_sign_stats.csv"
SM "outputs\probe_occurrence_contexts.csv"          "outputs\validation\probes_and_tests\contrastive\probe_occurrence_contexts.csv"
SM "outputs\reference_pdf_inventory.csv"            "outputs\resources_index\reference_pdf_inventory.csv"
SM "outputs\text_code_order_positional_analysis.tex" "outputs\analysis\positional\positional\text_code_order_positional_analysis.tex"
SM "outputs\text_code_order_positional_sign_stats.csv" "outputs\analysis\positional\positional\text_code_order_positional_sign_stats.csv"
SM "outputs\text_code_order_tier_a_length_distribution.csv" "outputs\analysis\positional\positional\text_code_order_tier_a_length_distribution.csv"
SM "outputs\tier_a_length_distribution.csv"        "outputs\analysis\positional\positional\tier_a_length_distribution.csv"
# outputs\ now has: 1 file (ivs_research_report.pdf) + 3 subdirs = OK

# ─── 2. outputs\analysis\corpus\catalog (6 files -> split into review/ and source/) ──────
SM "outputs\analysis\corpus\catalog\visual_catalog_review_examples.csv"  "outputs\analysis\corpus\catalog\review\visual_catalog_review_examples.csv"
SM "outputs\analysis\corpus\catalog\visual_catalog_review_protocol.csv"  "outputs\analysis\corpus\catalog\review\visual_catalog_review_protocol.csv"
SM "outputs\analysis\corpus\catalog\visual_catalog_source_status.csv"    "outputs\analysis\corpus\catalog\review\visual_catalog_source_status.csv"
# catalog now has: 3 files + 1 subdir = OK

# ─── 3. outputs\analysis\positional\crosswalk (6 files -> split: move 1 to subdir) ───────
# Move the .tex and top file to a tex/ subdir
SM "outputs\analysis\positional\crosswalk\crosswalk_neighbor_analysis.tex"   "outputs\analysis\positional\crosswalk\tex\crosswalk_neighbor_analysis.tex"
SM "outputs\analysis\positional\crosswalk\sign_neighbor_similarity_top.csv"  "outputs\analysis\positional\crosswalk\tex\sign_neighbor_similarity_top.csv"
# crosswalk now has: 4 files + 1 subdir = OK

# ─── 4. outputs\models\grammar\paradigm_and_reconstruction\paradigm (10 files) ───────────
# Split into slots/ (frames, fillers, occurrences, summary) and positions/ (initial, final, stems)
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_frames.csv"            "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slots\slot_paradigm_frames.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_fillers.csv"           "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slots\slot_paradigm_fillers.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_occurrences.csv"       "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slots\slot_paradigm_occurrences.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_summary.csv"           "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slots\slot_paradigm_summary.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_stem_finals.csv"       "outputs\models\grammar\paradigm_and_reconstruction\paradigm\positions\slot_paradigm_stem_finals.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_initial_signs.csv"     "outputs\models\grammar\paradigm_and_reconstruction\paradigm\positions\slot_paradigm_initial_signs.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_final_signs.csv"       "outputs\models\grammar\paradigm_and_reconstruction\paradigm\positions\slot_paradigm_final_signs.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_minimal_pairs.csv"     "outputs\models\grammar\paradigm_and_reconstruction\paradigm\positions\slot_paradigm_minimal_pairs.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_cross_frame_reuse.csv" "outputs\models\grammar\paradigm_and_reconstruction\paradigm\positions\slot_paradigm_cross_frame_reuse.csv"
# paradigm now has: 1 file (slot_paradigm_model.tex) + 2 subdirs = OK

# ─── 5. outputs\models\grammar\paradigm_and_reconstruction\reconstruction (6 files) ──────
SM "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\structural_reconstructions.csv"         "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\reconstructions\structural_reconstructions.csv"
SM "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\structural_reconstruction_templates.csv" "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\reconstructions\structural_reconstruction_templates.csv"
# reconstruction now has: 4 files + 1 subdir = OK

# ─── 6. outputs\models\names_and_semantics\proper_names (8 files) ─────────────────────────
SM "outputs\models\names_and_semantics\proper_names\filler_candidates_full.csv"       "outputs\models\names_and_semantics\proper_names\fillers\filler_candidates_full.csv"
SM "outputs\models\names_and_semantics\proper_names\filler_candidates_localized.csv"  "outputs\models\names_and_semantics\proper_names\fillers\filler_candidates_localized.csv"
SM "outputs\models\names_and_semantics\proper_names\filler_candidates_widespread.csv" "outputs\models\names_and_semantics\proper_names\fillers\filler_candidates_widespread.csv"
SM "outputs\models\names_and_semantics\proper_names\regular_patterns.csv"             "outputs\models\names_and_semantics\proper_names\fillers\regular_patterns.csv"
# proper_names now has: 4 files + 1 subdir = OK

# ─── 7. outputs\models\names_and_semantics\anchors\dossier (9 files) ─────────────────────
SM "outputs\models\names_and_semantics\anchors\dossier\anchor_component_edges.csv"      "outputs\models\names_and_semantics\anchors\dossier\components\anchor_component_edges.csv"
SM "outputs\models\names_and_semantics\anchors\dossier\anchor_component_roles.csv"      "outputs\models\names_and_semantics\anchors\dossier\components\anchor_component_roles.csv"
SM "outputs\models\names_and_semantics\anchors\dossier\anchor_occurrence_evidence.csv"  "outputs\models\names_and_semantics\anchors\dossier\components\anchor_occurrence_evidence.csv"
SM "outputs\models\names_and_semantics\anchors\dossier\anchor_reading_hypotheses.csv"   "outputs\models\names_and_semantics\anchors\dossier\components\anchor_reading_hypotheses.csv"
SM "outputs\models\names_and_semantics\anchors\dossier\lexical_reading_gate.csv"        "outputs\models\names_and_semantics\anchors\dossier\components\lexical_reading_gate.csv"
# dossier now has: 4 files + 1 subdir = OK

# ─── 8. outputs\models\names_and_semantics\anchors\onomastic (6 files) ───────────────────
SM "outputs\models\names_and_semantics\anchors\onomastic\onomastic_title_marker_candidates.csv" "outputs\models\names_and_semantics\anchors\onomastic\candidates\onomastic_title_marker_candidates.csv"
SM "outputs\models\names_and_semantics\anchors\onomastic\phonetic_variable_map.csv"             "outputs\models\names_and_semantics\anchors\onomastic\candidates\phonetic_variable_map.csv"
# onomastic now has: 4 files + 1 subdir = OK

# ─── 9. outputs\models\names_and_semantics\semantics\scaffold (6 files) ──────────────────
SM "outputs\models\names_and_semantics\semantics\scaffold\proto_decipherment_template_families.csv" "outputs\models\names_and_semantics\semantics\scaffold\templates\proto_decipherment_template_families.csv"
SM "outputs\models\names_and_semantics\semantics\scaffold\proto_decipherment_text_templates.csv"    "outputs\models\names_and_semantics\semantics\scaffold\templates\proto_decipherment_text_templates.csv"
# scaffold now has: 4 files + 1 subdir = OK

# ─── 10. outputs\models\names_and_semantics\semantics\triangulation (6 files) ───────────
SM "outputs\models\names_and_semantics\semantics\triangulation\anchor_context_profiles.csv"     "outputs\models\names_and_semantics\semantics\triangulation\context\anchor_context_profiles.csv"
SM "outputs\models\names_and_semantics\semantics\triangulation\semantic_reconstruction_candidates.csv" "outputs\models\names_and_semantics\semantics\triangulation\context\semantic_reconstruction_candidates.csv"
# triangulation now has: 4 files + 1 subdir = OK

# ─── 11. outputs\models\sequence_and_network\terminal (7 files) ──────────────────────────
SM "outputs\models\sequence_and_network\terminal\permutation_test_results.csv"             "outputs\models\sequence_and_network\terminal\tests\permutation_test_results.csv"
SM "outputs\models\sequence_and_network\terminal\terminal_complementary_distribution.csv"  "outputs\models\sequence_and_network\terminal\tests\terminal_complementary_distribution.csv"
SM "outputs\models\sequence_and_network\terminal\terminal_cooccurrence_check.csv"          "outputs\models\sequence_and_network\terminal\tests\terminal_cooccurrence_check.csv"
# terminal now has: 4 files + 1 subdir = OK

# ─── 12. outputs\models\sequence_and_network\network\cooccurrence (6 files) ─────────────
SM "outputs\models\sequence_and_network\network\cooccurrence\sign_network_nodes.csv"  "outputs\models\sequence_and_network\network\cooccurrence\nodes_and_edges\sign_network_nodes.csv"
SM "outputs\models\sequence_and_network\network\cooccurrence\sign_network_edges.csv"  "outputs\models\sequence_and_network\network\cooccurrence\nodes_and_edges\sign_network_edges.csv"
# cooccurrence now has: 4 files + 1 subdir = OK

# ─── 13. outputs\validation\probes_and_tests\phonetic_and_minimal\minimal (6 files) ─────
SM "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\neighbor_reading_tests.csv"     "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\neighbors\neighbor_reading_tests.csv"
SM "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\neighbor_expansion_summary.csv" "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\neighbors\neighbor_expansion_summary.csv"
# minimal now has: 4 files + 1 subdir = OK

# ─── 14. outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic (6 files) ────
SM "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\abstract_phonetic_reconstructions.csv" "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\reconstructions\abstract_phonetic_reconstructions.csv"
SM "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\phonetic_bootstrap_candidates.csv"     "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\reconstructions\phonetic_bootstrap_candidates.csv"
# phonetic now has: 4 files + 1 subdir = OK

# ─── 15. outputs\validation\solvers_and_queues\breakthrough (8 files) ────────────────────
SM "outputs\validation\solvers_and_queues\breakthrough\component_contrast_tests.csv" "outputs\validation\solvers_and_queues\breakthrough\tests\component_contrast_tests.csv"
SM "outputs\validation\solvers_and_queues\breakthrough\stem_contrast_lattice.csv"    "outputs\validation\solvers_and_queues\breakthrough\tests\stem_contrast_lattice.csv"
SM "outputs\validation\solvers_and_queues\breakthrough\validated_probe_results.csv"  "outputs\validation\solvers_and_queues\breakthrough\tests\validated_probe_results.csv"
SM "outputs\validation\solvers_and_queues\breakthrough\breakthrough_dependency_edges.csv" "outputs\validation\solvers_and_queues\breakthrough\tests\breakthrough_dependency_edges.csv"
# breakthrough now has: 4 files + 1 subdir = OK

# ─── 16. outputs\validation\solvers_and_queues\constraint_solver (7 files) ───────────────
SM "outputs\validation\solvers_and_queues\constraint_solver\morpheme_slot_assignments.csv"   "outputs\validation\solvers_and_queues\constraint_solver\assignments\morpheme_slot_assignments.csv"
SM "outputs\validation\solvers_and_queues\constraint_solver\reconstructed_clause_frames.csv" "outputs\validation\solvers_and_queues\constraint_solver\assignments\reconstructed_clause_frames.csv"
SM "outputs\validation\solvers_and_queues\constraint_solver\decipherment_progress_estimate.csv" "outputs\validation\solvers_and_queues\constraint_solver\assignments\decipherment_progress_estimate.csv"
# constraint_solver now has: 4 files + 1 subdir = OK

# ─── 17. src\docs\sections\analysis\corpus (7 files) ─────────────────────────────────────
SM "src\docs\sections\analysis\corpus\crosswalk_neighbor_clustering.tex" "src\docs\sections\analysis\corpus\chapters\crosswalk_neighbor_clustering.tex"
SM "src\docs\sections\analysis\corpus\sign_inventory_compression.tex"    "src\docs\sections\analysis\corpus\chapters\sign_inventory_compression.tex"
SM "src\docs\sections\analysis\corpus\tier1_visual_adjudication.tex"     "src\docs\sections\analysis\corpus\chapters\tier1_visual_adjudication.tex"
# corpus now has: 4 files + 1 subdir = OK

# ─── 18. Root: remove temp files (move_files.py, safe_reorganize.ps1, reorganize_log.txt to src\) ──
# We keep reorganize_log.txt in src as a record
SM "reorganize_log.txt" "src\reorganize_log.txt"
if (Test-Path (Join-Path $root "move_files.py")) {
    Remove-Item -LiteralPath (Join-Path $root "move_files.py") -Force
    Log "DELETED: move_files.py (temp file)"
}
# safe_reorganize.ps1 and patch_violations.ps1 will be removed last
# (can't remove the running script)

# ─── 19. outputs\resources_index - the reference_pdf_inventory.csv went here, check if it exists ──
# (If it doesn't exist just ignore - the source may not exist)

Log "=== Running final invariant check ==="
$violationFound = $false
Get-ChildItem -Path $root -Recurse -Directory | Where-Object { $_.FullName -notlike "*\.git*" } | ForEach-Object {
    $dirPath = $_.FullName
    $subdirs = (Get-ChildItem -Path $dirPath -Directory).Count
    $files   = (Get-ChildItem -Path $dirPath -File).Count
    $rel     = $dirPath.Substring($root.Length + 1)
    if ($subdirs -gt 3 -or $files -gt 5) {
        Log "[VIOLATION] $rel : $subdirs subdirs, $files files"
        $script:violationFound = $true
    }
}
$rootSubdirs = (Get-ChildItem -Path $root -Directory | Where-Object { $_.Name -ne ".git" }).Count
$rootFiles   = (Get-ChildItem -Path $root -File).Count
if ($rootSubdirs -gt 3 -or $rootFiles -gt 5) {
    Log "[VIOLATION] . (root): $rootSubdirs subdirs, $rootFiles files"
    $violationFound = $true
}

if (-not $violationFound) {
    Log "ALL FOLDERS COMPLIANT - invariant satisfied everywhere."
} else {
    Log "Some violations remain - review above."
}
Log "=== Patch complete ==="
