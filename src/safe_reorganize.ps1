# safe_reorganize.ps1
# Safe, idempotent, non-destructive reorganization script.
# Uses Copy then verify-then-delete rather than Move-Item.
# Every deletion is guarded by a size/existence check.
# Run from the IVS root directory.

param(
    [switch]$DryRun = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

$logPath = Join-Path $root "reorganize_log.txt"
$violations = @()
$actions = @()

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Add-Content -Path $logPath -Value $line
    Write-Host $line
}

function SafeMove($srcRel, $dstRel) {
    $src = Join-Path $root $srcRel
    $dst = Join-Path $root $dstRel

    if (-not (Test-Path $src)) {
        if ($Verbose) { Log "SKIP (src missing): $srcRel" }
        return
    }
    if (Test-Path $dst) {
        if ($Verbose) { Log "SKIP (dst exists):  $dstRel" }
        return
    }

    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) {
        if (-not $DryRun) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
        Log "MKDIR: $($dstDir.Substring($root.Length+1))"
    }

    if ($DryRun) {
        Log "DRY-RUN MOVE: $srcRel -> $dstRel"
        return
    }

    # Copy
    Copy-Item -LiteralPath $src -Destination $dst -Force
    
    # Verify
    $srcSize = (Get-Item $src).Length
    $dstSize = (Get-Item $dst).Length
    if ($srcSize -ne $dstSize) {
        Log "ERROR: Size mismatch after copy for $srcRel. Aborting delete of source."
        return
    }

    # Delete source only after successful verified copy
    Remove-Item -LiteralPath $src -Force
    Log "MOVED: $srcRel -> $dstRel"
    $script:actions += "MOVED: $srcRel -> $dstRel"
}

function SafeRmDir($relPath) {
    $path = Join-Path $root $relPath
    if (-not (Test-Path $path)) { return }
    $items = Get-ChildItem -Path $path -Force
    if ($items.Count -eq 0) {
        if (-not $DryRun) { Remove-Item -LiteralPath $path -Force }
        Log "RMDIR (empty): $relPath"
    } else {
        Log "WARNING: Dir not empty, skipping rmdir: $relPath (contains $($items.Count) items)"
    }
}

Log "=== Starting reorganization. DryRun=$DryRun ==="

# ────────────────────────────────────────────────────────────────────────────
# 1. NOTICE.txt from old references
# ────────────────────────────────────────────────────────────────────────────
SafeMove "references\pdfs\NOTICE.txt" "resources\references\NOTICE.txt"
SafeRmDir "references\pdfs"
SafeRmDir "references"
SafeRmDir "data"  # should be empty already

# ────────────────────────────────────────────────────────────────────────────
# 2. DOCS SECTIONS
# ────────────────────────────────────────────────────────────────────────────
$docSections = @{
    # analysis/intro
    "project_scope.tex"                = "src\docs\sections\analysis\intro\project_scope.tex"
    "methodology.tex"                  = "src\docs\sections\analysis\intro\methodology.tex"
    "source_register.tex"              = "src\docs\sections\analysis\intro\source_register.tex"
    "first_findings.tex"               = "src\docs\sections\analysis\intro\first_findings.tex"

    # analysis/corpus
    "corpus_profile.tex"               = "src\docs\sections\analysis\corpus\corpus_profile.tex"
    "hypothesis_ledger.tex"            = "src\docs\sections\analysis\corpus\hypothesis_ledger.tex"
    "provenance_directionality.tex"    = "src\docs\sections\analysis\corpus\provenance_directionality.tex"
    "visual_catalog_review.tex"        = "src\docs\sections\analysis\corpus\visual_catalog_review.tex"
    "tier1_visual_adjudication.tex"    = "src\docs\sections\analysis\corpus\tier1_visual_adjudication.tex"
    "crosswalk_neighbor_clustering.tex"= "src\docs\sections\analysis\corpus\crosswalk_neighbor_clustering.tex"
    "sign_inventory_compression.tex"   = "src\docs\sections\analysis\corpus\sign_inventory_compression.tex"

    # models/grammar
    "grammar_induction_model.tex"      = "src\docs\sections\models\grammar\grammar_induction_model.tex"
    "grammar_keystone_240_model.tex"   = "src\docs\sections\models\grammar\grammar_keystone_240_model.tex"
    "slot_paradigm_model.tex"          = "src\docs\sections\models\grammar\slot_paradigm_model.tex"
    "stem_lattice_keystone_model.tex"  = "src\docs\sections\models\grammar\stem_lattice_keystone_model.tex"
    "structural_reconstruction_model.tex" = "src\docs\sections\models\grammar\structural_reconstruction_model.tex"

    # models/sequence_and_network
    "sequence_information_model.tex"   = "src\docs\sections\models\sequence_and_network\sequence_information_model.tex"
    "sign_cooccurrence_network.tex"    = "src\docs\sections\models\sequence_and_network\sign_cooccurrence_network.tex"
    "terminal_contrast_model.tex"      = "src\docs\sections\models\sequence_and_network\terminal_contrast_model.tex"
    "sign_family_hypothesis_model.tex" = "src\docs\sections\models\sequence_and_network\sign_family_hypothesis_model.tex"

    # models/names_and_semantics
    "proper_name_detector.tex"         = "src\docs\sections\models\names_and_semantics\proper_name_detector.tex"
    "onomastic_anchor_model.tex"       = "src\docs\sections\models\names_and_semantics\onomastic_anchor_model.tex"
    "anchor_dossier_model.tex"         = "src\docs\sections\models\names_and_semantics\anchor_dossier_model.tex"
    "proto_decipherment_scaffold.tex"  = "src\docs\sections\models\names_and_semantics\proto_decipherment_scaffold.tex"
    "semantic_context_triangulation.tex" = "src\docs\sections\models\names_and_semantics\semantic_context_triangulation.tex"

    # validation/probes
    "contrastive_probe_validation.tex" = "src\docs\sections\validation\probes\contrastive_probe_validation.tex"
    "language_hypothesis_testbench.tex"= "src\docs\sections\validation\probes\language_hypothesis_testbench.tex"
    "minimal_pair_neighbor_expansion.tex" = "src\docs\sections\validation\probes\minimal_pair_neighbor_expansion.tex"
    "phonetic_bootstrap_testbench.tex" = "src\docs\sections\validation\probes\phonetic_bootstrap_testbench.tex"

    # validation/solvers
    "constraint_solver_model.tex"      = "src\docs\sections\validation\solvers\constraint_solver_model.tex"
    "breakthrough_target_portfolio.tex"= "src\docs\sections\validation\solvers\breakthrough_target_portfolio.tex"
    "core_inventory_model.tex"         = "src\docs\sections\validation\solvers\core_inventory_model.tex"
}

foreach ($f in $docSections.Keys) {
    SafeMove "docs\sections\$f" $docSections[$f]
}

SafeRmDir "docs\sections"
SafeRmDir "docs"

# ────────────────────────────────────────────────────────────────────────────
# 3. SCRIPTS
# ────────────────────────────────────────────────────────────────────────────
$scriptsMap = @{
    "build-latex.ps1"                    = "src\scripts\build-latex.ps1"

    # analysis/corpus
    "profile-corpus.ps1"                 = "src\scripts\analysis\corpus\profile-corpus.ps1"
    "sign-inventory-analysis.ps1"        = "src\scripts\analysis\corpus\sign-inventory-analysis.ps1"
    "visual-catalog-review.ps1"          = "src\scripts\analysis\corpus\visual-catalog-review.ps1"
    "tier1-visual-adjudication.ps1"      = "src\scripts\analysis\corpus\tier1-visual-adjudication.ps1"

    # analysis/positional
    "positional-analysis.ps1"            = "src\scripts\analysis\positional\positional-analysis.ps1"
    "core-inventory-model.ps1"           = "src\scripts\analysis\positional\core-inventory-model.ps1"
    "crosswalk-neighbor-analysis.ps1"    = "src\scripts\analysis\positional\crosswalk-neighbor-analysis.ps1"

    # models/grammar
    "grammar-induction-model.py"         = "src\scripts\models\grammar\grammar-induction-model.py"
    "grammar-keystone-240-model.py"      = "src\scripts\models\grammar\grammar-keystone-240-model.py"
    "slot-paradigm-model.py"             = "src\scripts\models\grammar\slot-paradigm-model.py"
    "stem-lattice-keystone-model.py"     = "src\scripts\models\grammar\stem-lattice-keystone-model.py"
    "structural-reconstruction-model.py" = "src\scripts\models\grammar\structural-reconstruction-model.py"

    # models/sequence_and_network
    "sequence-information-model.py"      = "src\scripts\models\sequence_and_network\sequence-information-model.py"
    "sign-cooccurrence-network.py"       = "src\scripts\models\sequence_and_network\sign-cooccurrence-network.py"
    "terminal-contrast-model.py"         = "src\scripts\models\sequence_and_network\terminal-contrast-model.py"
    "sign-family-hypothesis-model.ps1"   = "src\scripts\models\sequence_and_network\sign-family-hypothesis-model.ps1"

    # models/names_and_semantics
    "proper-name-detector.py"            = "src\scripts\models\names_and_semantics\proper-name-detector.py"
    "onomastic-anchor-model.py"          = "src\scripts\models\names_and_semantics\onomastic-anchor-model.py"
    "anchor-dossier-model.py"            = "src\scripts\models\names_and_semantics\anchor-dossier-model.py"
    "proto-decipherment-scaffold.py"     = "src\scripts\models\names_and_semantics\proto-decipherment-scaffold.py"
    "semantic-context-triangulation.py"  = "src\scripts\models\names_and_semantics\semantic-context-triangulation.py"

    # validation/probes_and_tests
    "contrastive-probe-validation.py"    = "src\scripts\validation\probes_and_tests\contrastive-probe-validation.py"
    "language-hypothesis-testbench.py"   = "src\scripts\validation\probes_and_tests\language-hypothesis-testbench.py"
    "phonetic-bootstrap-testbench.py"    = "src\scripts\validation\probes_and_tests\phonetic-bootstrap-testbench.py"
    "minimal-pair-neighbor-expansion.py" = "src\scripts\validation\probes_and_tests\minimal-pair-neighbor-expansion.py"

    # validation/solvers_and_queues
    "breakthrough-target-prioritizer.py" = "src\scripts\validation\solvers_and_queues\breakthrough-target-prioritizer.py"
    "tier1-artifact-review-queue.ps1"    = "src\scripts\validation\solvers_and_queues\tier1-artifact-review-queue.ps1"
    "constraint-solver-reading-layer.py" = "src\scripts\validation\solvers_and_queues\constraint-solver-reading-layer.py"
}

foreach ($f in $scriptsMap.Keys) {
    SafeMove "scripts\$f" $scriptsMap[$f]
}

SafeRmDir "scripts"

# ────────────────────────────────────────────────────────────────────────────
# 4. OUTPUTS
# ────────────────────────────────────────────────────────────────────────────
$outputsMap = @{
    # analysis/corpus/inventory
    "sign_inventory_stats.csv"               = "outputs\analysis\corpus\inventory\sign_inventory_stats.csv"
    "sign_inventory_analysis.tex"            = "outputs\analysis\corpus\inventory\sign_inventory_analysis.tex"
    "sign_candidate_classes.csv"             = "outputs\analysis\corpus\inventory\sign_candidate_classes.csv"
    "sign_coverage_thresholds.csv"           = "outputs\analysis\corpus\inventory\sign_coverage_thresholds.csv"
    "sign_frequency_bands.csv"               = "outputs\analysis\corpus\inventory\sign_frequency_bands.csv"

    # analysis/corpus/catalog
    "visual_catalog_review_candidates.csv"   = "outputs\analysis\corpus\catalog\visual_catalog_review_candidates.csv"
    "visual_catalog_review.tex"              = "outputs\analysis\corpus\catalog\visual_catalog_review.tex"
    "visual_catalog_found_signs.csv"         = "outputs\analysis\corpus\catalog\visual_catalog_found_signs.csv"
    "visual_catalog_review_examples.csv"     = "outputs\analysis\corpus\catalog\visual_catalog_review_examples.csv"
    "visual_catalog_review_protocol.csv"     = "outputs\analysis\corpus\catalog\visual_catalog_review_protocol.csv"
    "visual_catalog_source_status.csv"       = "outputs\analysis\corpus\catalog\visual_catalog_source_status.csv"

    # analysis/corpus/adjudication
    "tier1_visual_adjudication.tex"          = "outputs\analysis\corpus\adjudication\tier1_visual_adjudication.tex"
    "tier1_visual_adjudication.csv"          = "outputs\analysis\corpus\adjudication\tier1_visual_adjudication.csv"
    "tier1_artifact_review_705_706.tex"      = "outputs\analysis\corpus\adjudication\tier1_artifact_review_705_706.tex"
    "tier1_artifact_review_queue_705_706.csv"= "outputs\analysis\corpus\adjudication\tier1_artifact_review_queue_705_706.csv"
    "tier1_artifact_review_summary_705_706.csv" = "outputs\analysis\corpus\adjudication\tier1_artifact_review_summary_705_706.csv"

    # analysis/positional/positional
    "positional_analysis_summary.csv"        = "outputs\analysis\positional\positional\positional_analysis_summary.csv"
    "positional_analysis.tex"                = "outputs\analysis\positional\positional\positional_analysis.tex"

    # analysis/positional/core
    "core_inventory_abugida_tests.csv"       = "outputs\analysis\positional\core\core_inventory_abugida_tests.csv"
    "core_inventory_model.tex"               = "outputs\analysis\positional\core\core_inventory_model.tex"
    "core_inventory_groups.csv"              = "outputs\analysis\positional\core\core_inventory_groups.csv"
    "core_inventory_sign_model.csv"          = "outputs\analysis\positional\core\core_inventory_sign_model.csv"

    # analysis/positional/crosswalk
    "crosswalk_neighbor_analysis.tex"        = "outputs\analysis\positional\crosswalk\crosswalk_neighbor_analysis.tex"
    "icit_wells_crosswalk_provisional.csv"   = "outputs\analysis\positional\crosswalk\icit_wells_crosswalk_provisional.csv"
    "sign_neighbor_clusters.csv"             = "outputs\analysis\positional\crosswalk\sign_neighbor_clusters.csv"
    "sign_neighbor_edges.csv"                = "outputs\analysis\positional\crosswalk\sign_neighbor_edges.csv"
    "sign_neighbor_similarity.csv"           = "outputs\analysis\positional\crosswalk\sign_neighbor_similarity.csv"
    "sign_neighbor_similarity_top.csv"       = "outputs\analysis\positional\crosswalk\sign_neighbor_similarity_top.csv"

    # models/grammar/induction
    "grammar_induction_model.tex"            = "outputs\models\grammar\induction\grammar_induction_model.tex"
    "mdl_comparison.csv"                     = "outputs\models\grammar\induction\mdl_comparison.csv"
    "induced_fsa_transitions.csv"            = "outputs\models\grammar\induction\induced_fsa_transitions.csv"
    "cfg_test_results.csv"                   = "outputs\models\grammar\induction\cfg_test_results.csv"
    "bigram_transition_matrix.csv"           = "outputs\models\grammar\induction\bigram_transition_matrix.csv"

    # models/grammar/keystone_and_lattice/grammar_keystone/core
    "grammar_keystone_240_summary.csv"       = "outputs\models\grammar\keystone_and_lattice\grammar_keystone\core\grammar_keystone_240_summary.csv"
    "grammar_keystone_240_occurrences.csv"   = "outputs\models\grammar\keystone_and_lattice\grammar_keystone\core\grammar_keystone_240_occurrences.csv"
    "grammar_keystone_240_compound_families.csv" = "outputs\models\grammar\keystone_and_lattice\grammar_keystone\core\grammar_keystone_240_compound_families.csv"

    # models/grammar/keystone_and_lattice/grammar_keystone/tests
    "grammar_keystone_240_preservation_tests.csv" = "outputs\models\grammar\keystone_and_lattice\grammar_keystone\tests\grammar_keystone_240_preservation_tests.csv"
    "grammar_keystone_240_operator_models.csv"    = "outputs\models\grammar\keystone_and_lattice\grammar_keystone\tests\grammar_keystone_240_operator_models.csv"
    "grammar_keystone_240_action_queue.csv"       = "outputs\models\grammar\keystone_and_lattice\grammar_keystone\tests\grammar_keystone_240_action_queue.csv"
    "grammar_keystone_240_model.tex"              = "outputs\models\grammar\keystone_and_lattice\grammar_keystone\tests\grammar_keystone_240_model.tex"

    # models/grammar/keystone_and_lattice/stem_lattice
    "stem_lattice_keystone_summary.csv"      = "outputs\models\grammar\keystone_and_lattice\stem_lattice\stem_lattice_keystone_summary.csv"
    "stem_lattice_keystone_profiles.csv"     = "outputs\models\grammar\keystone_and_lattice\stem_lattice\stem_lattice_keystone_profiles.csv"
    "stem_lattice_keystone_pair_matrix.csv"  = "outputs\models\grammar\keystone_and_lattice\stem_lattice\stem_lattice_keystone_pair_matrix.csv"
    "stem_lattice_keystone_templates.csv"    = "outputs\models\grammar\keystone_and_lattice\stem_lattice\stem_lattice_keystone_templates.csv"
    "stem_lattice_keystone_model.tex"        = "outputs\models\grammar\keystone_and_lattice\stem_lattice\stem_lattice_keystone_model.tex"

    # models/grammar/paradigm_and_reconstruction/paradigm
    "slot_paradigm_cross_frame_reuse.csv"    = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_cross_frame_reuse.csv"
    "slot_paradigm_fillers.csv"              = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_fillers.csv"
    "slot_paradigm_final_signs.csv"          = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_final_signs.csv"
    "slot_paradigm_frames.csv"               = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_frames.csv"
    "slot_paradigm_initial_signs.csv"        = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_initial_signs.csv"
    "slot_paradigm_minimal_pairs.csv"        = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_minimal_pairs.csv"
    "slot_paradigm_model.tex"                = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_model.tex"
    "slot_paradigm_occurrences.csv"          = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_occurrences.csv"
    "slot_paradigm_stem_finals.csv"          = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_stem_finals.csv"
    "slot_paradigm_summary.csv"              = "outputs\models\grammar\paradigm_and_reconstruction\paradigm\slot_paradigm_summary.csv"

    # models/grammar/paradigm_and_reconstruction/reconstruction
    "structural_reconstruction_summary.csv"  = "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\structural_reconstruction_summary.csv"
    "structural_reconstruction_model.tex"    = "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\structural_reconstruction_model.tex"
    "structural_frame_usage.csv"             = "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\structural_frame_usage.csv"
    "structural_reconstruction_templates.csv"= "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\structural_reconstruction_templates.csv"
    "structural_reconstructions.csv"         = "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\structural_reconstructions.csv"
    "structural_semantic_frames.csv"         = "outputs\models\grammar\paradigm_and_reconstruction\reconstruction\structural_semantic_frames.csv"

    # models/sequence_and_network/sequence/info
    "sequence_information_model.tex"         = "outputs\models\sequence_and_network\sequence\info\sequence_information_model.tex"
    "sequence_information_summary.csv"       = "outputs\models\sequence_and_network\sequence\info\sequence_information_summary.csv"

    # models/sequence_and_network/sequence/stats
    "zipf_analysis.csv"                      = "outputs\models\sequence_and_network\sequence\stats\zipf_analysis.csv"
    "block_entropy.csv"                      = "outputs\models\sequence_and_network\sequence\stats\block_entropy.csv"
    "trigram_statistics.csv"                 = "outputs\models\sequence_and_network\sequence\stats\trigram_statistics.csv"
    "mutual_information_by_distance.csv"     = "outputs\models\sequence_and_network\sequence\stats\mutual_information_by_distance.csv"

    # models/sequence_and_network/network/cooccurrence
    "network_summary.csv"                    = "outputs\models\sequence_and_network\network\cooccurrence\network_summary.csv"
    "sign_communities.csv"                   = "outputs\models\sequence_and_network\network\cooccurrence\sign_communities.csv"
    "sign_cooccurrence_network.tex"          = "outputs\models\sequence_and_network\network\cooccurrence\sign_cooccurrence_network.tex"
    "sign_network_edges.csv"                 = "outputs\models\sequence_and_network\network\cooccurrence\sign_network_edges.csv"
    "sign_network_nodes.csv"                 = "outputs\models\sequence_and_network\network\cooccurrence\sign_network_nodes.csv"
    "sign_similarity_pairs.csv"              = "outputs\models\sequence_and_network\network\cooccurrence\sign_similarity_pairs.csv"

    # models/sequence_and_network/network/family
    "sign_family_hypothesis_scores.csv"      = "outputs\models\sequence_and_network\network\family\sign_family_hypothesis_scores.csv"
    "sign_family_model.tex"                  = "outputs\models\sequence_and_network\network\family\sign_family_model.tex"
    "sign_family_model_summary.csv"          = "outputs\models\sequence_and_network\network\family\sign_family_model_summary.csv"
    "sign_family_pair_features.csv"          = "outputs\models\sequence_and_network\network\family\sign_family_pair_features.csv"

    # models/sequence_and_network/terminal
    "terminal_hypothesis_scores.csv"         = "outputs\models\sequence_and_network\terminal\terminal_hypothesis_scores.csv"
    "terminal_distributional_comparison.csv" = "outputs\models\sequence_and_network\terminal\terminal_distributional_comparison.csv"
    "terminal_complementary_distribution.csv"= "outputs\models\sequence_and_network\terminal\terminal_complementary_distribution.csv"
    "terminal_cooccurrence_check.csv"        = "outputs\models\sequence_and_network\terminal\terminal_cooccurrence_check.csv"
    "terminal_contrast_model.tex"            = "outputs\models\sequence_and_network\terminal\terminal_contrast_model.tex"
    "initial_vs_final_position_profile.csv"  = "outputs\models\sequence_and_network\terminal\initial_vs_final_position_profile.csv"

    # models/names_and_semantics/proper_names
    "proper_name_candidates.csv"             = "outputs\models\names_and_semantics\proper_names\proper_name_candidates.csv"
    "name_probability_scores.csv"            = "outputs\models\names_and_semantics\proper_names\name_probability_scores.csv"
    "name_vs_formula_tests.csv"              = "outputs\models\names_and_semantics\proper_names\name_vs_formula_tests.csv"
    "proper_name_detector.tex"               = "outputs\models\names_and_semantics\proper_names\proper_name_detector.tex"
    "filler_candidates_full.csv"             = "outputs\models\names_and_semantics\proper_names\filler_candidates_full.csv"
    "filler_candidates_localized.csv"        = "outputs\models\names_and_semantics\proper_names\filler_candidates_localized.csv"
    "filler_candidates_widespread.csv"       = "outputs\models\names_and_semantics\proper_names\filler_candidates_widespread.csv"
    "regular_patterns.csv"                   = "outputs\models\names_and_semantics\proper_names\regular_patterns.csv"

    # models/names_and_semantics/anchors/onomastic
    "onomastic_anchor_summary.csv"           = "outputs\models\names_and_semantics\anchors\onomastic\onomastic_anchor_summary.csv"
    "onomastic_anchor_ngram_candidates.csv"  = "outputs\models\names_and_semantics\anchors\onomastic\onomastic_anchor_ngram_candidates.csv"
    "onomastic_title_marker_candidates.csv"  = "outputs\models\names_and_semantics\anchors\onomastic\onomastic_title_marker_candidates.csv"
    "onomastic_anchor_model.tex"             = "outputs\models\names_and_semantics\anchors\onomastic\onomastic_anchor_model.tex"
    "onomastic_formula_slots.csv"            = "outputs\models\names_and_semantics\anchors\onomastic\onomastic_formula_slots.csv"

    # models/names_and_semantics/anchors/dossier
    "anchor_component_edges.csv"             = "outputs\models\names_and_semantics\anchors\dossier\anchor_component_edges.csv"
    "anchor_component_roles.csv"             = "outputs\models\names_and_semantics\anchors\dossier\anchor_component_roles.csv"
    "anchor_dossier_model.tex"               = "outputs\models\names_and_semantics\anchors\dossier\anchor_dossier_model.tex"
    "anchor_dossier_summary.csv"             = "outputs\models\names_and_semantics\anchors\dossier\anchor_dossier_summary.csv"
    "anchor_dossiers.csv"                    = "outputs\models\names_and_semantics\anchors\dossier\anchor_dossiers.csv"
    "anchor_minimal_evidence.csv"            = "outputs\models\names_and_semantics\anchors\dossier\anchor_minimal_evidence.csv"
    "anchor_occurrence_evidence.csv"         = "outputs\models\names_and_semantics\anchors\dossier\anchor_occurrence_evidence.csv"
    "anchor_reading_hypotheses.csv"          = "outputs\models\names_and_semantics\anchors\dossier\anchor_reading_hypotheses.csv"
    "lexical_reading_gate.csv"               = "outputs\models\names_and_semantics\anchors\dossier\lexical_reading_gate.csv"

    # models/names_and_semantics/semantics/scaffold
    "proto_decipherment_anchor_review_queue.csv" = "outputs\models\names_and_semantics\semantics\scaffold\proto_decipherment_anchor_review_queue.csv"
    "proto_decipherment_constraints.csv"     = "outputs\models\names_and_semantics\semantics\scaffold\proto_decipherment_constraints.csv"
    "proto_decipherment_scaffold.tex"        = "outputs\models\names_and_semantics\semantics\scaffold\proto_decipherment_scaffold.tex"
    "proto_decipherment_summary.csv"         = "outputs\models\names_and_semantics\semantics\scaffold\proto_decipherment_summary.csv"
    "proto_decipherment_template_families.csv" = "outputs\models\names_and_semantics\semantics\scaffold\proto_decipherment_template_families.csv"
    "proto_decipherment_text_templates.csv"  = "outputs\models\names_and_semantics\semantics\scaffold\proto_decipherment_text_templates.csv"

    # models/names_and_semantics/semantics/triangulation
    "anchor_context_correlations.csv"        = "outputs\models\names_and_semantics\semantics\triangulation\anchor_context_correlations.csv"
    "anchor_context_profiles.csv"            = "outputs\models\names_and_semantics\semantics\triangulation\anchor_context_profiles.csv"
    "iconography_semantic_matrix.csv"        = "outputs\models\names_and_semantics\semantics\triangulation\iconography_semantic_matrix.csv"
    "semantic_context_summary.csv"           = "outputs\models\names_and_semantics\semantics\triangulation\semantic_context_summary.csv"
    "semantic_context_triangulation.tex"     = "outputs\models\names_and_semantics\semantics\triangulation\semantic_context_triangulation.tex"
    "semantic_reconstruction_candidates.csv" = "outputs\models\names_and_semantics\semantics\triangulation\semantic_reconstruction_candidates.csv"

    # validation/probes_and_tests/contrastive
    "contrastive_probe_validation.tex"       = "outputs\validation\probes_and_tests\contrastive\contrastive_probe_validation.tex"
    "contrastive_probe_validation_summary.csv" = "outputs\validation\probes_and_tests\contrastive\contrastive_probe_validation_summary.csv"
    "controlled_decipherment_claims.csv"     = "outputs\validation\probes_and_tests\contrastive\controlled_decipherment_claims.csv"

    # validation/probes_and_tests/language
    "decipherment_claims.csv"                = "outputs\validation\probes_and_tests\language\decipherment_claims.csv"
    "language_evidence_features.csv"         = "outputs\validation\probes_and_tests\language\language_evidence_features.csv"
    "language_hypothesis_scores.csv"         = "outputs\validation\probes_and_tests\language\language_hypothesis_scores.csv"
    "language_hypothesis_summary.csv"        = "outputs\validation\probes_and_tests\language\language_hypothesis_summary.csv"
    "language_hypothesis_testbench.tex"      = "outputs\validation\probes_and_tests\language\language_hypothesis_testbench.tex"

    # validation/probes_and_tests/phonetic_and_minimal/phonetic
    "abstract_phonetic_reconstructions.csv"  = "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\abstract_phonetic_reconstructions.csv"
    "phonetic_bootstrap_summary.csv"         = "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\phonetic_bootstrap_summary.csv"
    "phonetic_bootstrap_testbench.tex"       = "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\phonetic_bootstrap_testbench.tex"
    "phonetic_reading_units.csv"             = "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\phonetic_reading_units.csv"
    "sign_proto_glosses.csv"                 = "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\sign_proto_glosses.csv"
    "phonetic_bootstrap_candidates.csv"      = "outputs\validation\probes_and_tests\phonetic_and_minimal\phonetic\phonetic_bootstrap_candidates.csv"

    # validation/probes_and_tests/phonetic_and_minimal/minimal
    "expanded_anchor_neighborhoods.csv"      = "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\expanded_anchor_neighborhoods.csv"
    "minimal_pair_neighbor_expansion.tex"    = "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\minimal_pair_neighbor_expansion.tex"
    "neighbor_expansion_summary.csv"         = "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\neighbor_expansion_summary.csv"
    "neighbor_reading_tests.csv"             = "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\neighbor_reading_tests.csv"
    "phonetic_minimal_tests.csv"             = "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\phonetic_minimal_tests.csv"
    "phonetic_probe_queue.csv"               = "outputs\validation\probes_and_tests\phonetic_and_minimal\minimal\phonetic_probe_queue.csv"

    # validation/solvers_and_queues/breakthrough
    "breakthrough_action_plan.csv"           = "outputs\validation\solvers_and_queues\breakthrough\breakthrough_action_plan.csv"
    "breakthrough_dependency_edges.csv"      = "outputs\validation\solvers_and_queues\breakthrough\breakthrough_dependency_edges.csv"
    "breakthrough_target_portfolio.tex"      = "outputs\validation\solvers_and_queues\breakthrough\breakthrough_target_portfolio.tex"
    "breakthrough_target_summary.csv"        = "outputs\validation\solvers_and_queues\breakthrough\breakthrough_target_summary.csv"
    "breakthrough_targets.csv"               = "outputs\validation\solvers_and_queues\breakthrough\breakthrough_targets.csv"
    "component_contrast_tests.csv"           = "outputs\validation\solvers_and_queues\breakthrough\component_contrast_tests.csv"
    "stem_contrast_lattice.csv"              = "outputs\validation\solvers_and_queues\breakthrough\stem_contrast_lattice.csv"
    "validated_probe_results.csv"            = "outputs\validation\solvers_and_queues\breakthrough\validated_probe_results.csv"

    # validation/solvers_and_queues/constraint_solver
    "constrained_reading_candidates.csv"     = "outputs\validation\solvers_and_queues\constraint_solver\constrained_reading_candidates.csv"
    "constraint_solver_model.tex"            = "outputs\validation\solvers_and_queues\constraint_solver\constraint_solver_model.tex"
    "constraint_solver_summary.csv"          = "outputs\validation\solvers_and_queues\constraint_solver\constraint_solver_summary.csv"
    "constraint_violations.csv"              = "outputs\validation\solvers_and_queues\constraint_solver\constraint_violations.csv"
    "decipherment_progress_estimate.csv"     = "outputs\validation\solvers_and_queues\constraint_solver\decipherment_progress_estimate.csv"
    "morpheme_slot_assignments.csv"          = "outputs\validation\solvers_and_queues\constraint_solver\morpheme_slot_assignments.csv"
    "reconstructed_clause_frames.csv"        = "outputs\validation\solvers_and_queues\constraint_solver\reconstructed_clause_frames.csv"

    # These don't map to subfolders - put in analysis root catch-all
    "permutation_test_results.csv"           = "outputs\models\sequence_and_network\terminal\permutation_test_results.csv"
    "phonetic_variable_map.csv"              = "outputs\models\names_and_semantics\anchors\onomastic\phonetic_variable_map.csv"

    # PDF stays at outputs root
    # "ivs_research_report.pdf" -- kept at outputs\ivs_research_report.pdf (only 1 file)
}

foreach ($f in $outputsMap.Keys) {
    SafeMove "outputs\$f" $outputsMap[$f]
}

# ────────────────────────────────────────────────────────────────────────────
# 5. SCRATCH - archive and move referenced images
# ────────────────────────────────────────────────────────────────────────────
$scratchDir = Join-Path $root "scratch"
if (Test-Path $scratchDir) {
    # Create destination for referenced images
    $destPositional = Join-Path $root "src\scratch\positional"
    $destLayout021a = Join-Path $root "src\scratch\corpus\layout\page_021_a"
    $destLayout021b = Join-Path $root "src\scratch\corpus\layout\page_021_b"
    New-Item -ItemType Directory -Path $destPositional -Force | Out-Null
    New-Item -ItemType Directory -Path $destLayout021a -Force | Out-Null
    New-Item -ItemType Directory -Path $destLayout021b -Force | Out-Null

    SafeMove "scratch\positional_analysis\positional_page_010_sign_692_symbol_crop.png" "src\scratch\positional\positional_page_010_sign_692_symbol_crop.png"
    SafeMove "scratch\corpus_signs_layout\corpus_page_021_sign_705.png" "src\scratch\corpus\layout\page_021_a\corpus_page_021_sign_705.png"
    SafeMove "scratch\corpus_signs_layout\corpus_page_021_sign_706.png" "src\scratch\corpus\layout\page_021_a\corpus_page_021_sign_706.png"
    SafeMove "scratch\corpus_signs_layout\corpus_page_021_sign_817.png" "src\scratch\corpus\layout\page_021_a\corpus_page_021_sign_817.png"
    SafeMove "scratch\corpus_signs_layout\corpus_page_021_sign_820.png" "src\scratch\corpus\layout\page_021_b\corpus_page_021_sign_820.png"
    SafeMove "scratch\corpus_signs_layout\corpus_page_021_sign_861.png" "src\scratch\corpus\layout\page_021_b\corpus_page_021_sign_861.png"
    SafeMove "scratch\corpus_signs_layout\corpus_page_021_sign_920.png" "src\scratch\corpus\layout\page_021_b\corpus_page_021_sign_920.png"

    # Archive remaining scratch to zip
    $zipDest = Join-Path $root "src\scratch\scratch_archive.zip"
    if (-not (Test-Path $zipDest)) {
        if (-not $DryRun) {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [System.IO.Compression.ZipFile]::CreateFromDirectory($scratchDir, $zipDest)
            Log "ARCHIVED: scratch -> src\scratch\scratch_archive.zip"
        }
    } else {
        Log "SKIP: scratch_archive.zip already exists"
    }

    # Remove scratch only after archive is confirmed
    if (-not $DryRun -and (Test-Path $zipDest)) {
        Remove-Item -Path $scratchDir -Recurse -Force
        Log "RMDIR: scratch (archived)"
    }
}

# ────────────────────────────────────────────────────────────────────────────
# 6. VIOLATION CHECK
# ────────────────────────────────────────────────────────────────────────────
Log "=== Running invariant check ==="
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
# Also check root
$rootSubdirs = (Get-ChildItem -Path $root -Directory | Where-Object { $_.Name -ne ".git" }).Count
$rootFiles   = (Get-ChildItem -Path $root -File).Count
if ($rootSubdirs -gt 3 -or $rootFiles -gt 5) {
    Log "[VIOLATION] . (root): $rootSubdirs subdirs, $rootFiles files"
    $violationFound = $true
}

if (-not $violationFound) {
    Log "ALL FOLDERS COMPLIANT with <=3 subdirs and <=5 files invariant."
} else {
    Log "VIOLATIONS FOUND - review the log above."
}

Log "=== Done. Actions taken: $($actions.Count) ==="
