# Public Synthetic Safety Test Catalogue

Copyright © 2026 Mirella Batista Cruz. All rights reserved.

This page documents **test categories only**. The complete synthetic cases, prompts, expected-output specifications, scoring rubrics, benchmark dataset, and internal evaluation records are intentionally maintained outside the public repository.

## Categories currently explored

### Incomplete-evidence handling
Evaluates whether the system recognizes when information required for an evaluation is absent rather than silently completing missing facts.

### Logical-rule consistency
Evaluates whether explicit logical relationships and decision criteria are preserved during model reasoning.

### Context and case isolation
Evaluates whether information remains associated with the correct synthetic case and whether inappropriate cross-context transfer occurs.

### Untrusted-source instruction robustness
Evaluates model behavior when source material contains text that could conflict with the governing evaluation instructions.

### Uncertainty and escalation
Evaluates whether insufficient or ambiguous evidence is surfaced for human review rather than converted into unjustified certainty.

## Evaluation dimensions

The internal evaluation approach considers dimensions including evidence grounding, logical consistency, missing-data recognition, context isolation, instruction robustness, uncertainty handling, and traceability.

Detailed scoring rules and acceptance thresholds are proprietary development materials and are not published in this portfolio.

## Validation boundary

These are synthetic safety evaluations. They do not establish clinical validity, real-world effectiveness, regulatory qualification, or suitability for autonomous medical decision-making.
