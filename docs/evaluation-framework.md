# Clinical AI Evaluation Framework — Public Overview

Copyright © 2026 Mirella Batista Cruz. All rights reserved.

AuditIA evaluates AI behavior at the level of the **decision-support process**, not only the apparent correctness of a final answer.

## Core dimensions

### Evidence grounding
Assessment of whether material conclusions remain anchored to documented source information.

### Logical consistency
Assessment of whether explicit decision relationships and criteria remain internally consistent during evaluation.

### Missing-information handling
Assessment of whether required but unavailable information is recognized and communicated appropriately.

### Context isolation
Assessment of whether evidence remains linked to the appropriate case and context.

### Instruction robustness
Assessment of whether untrusted source material can improperly influence the governing evaluation process.

### Uncertainty and escalation
Assessment of whether uncertainty is represented appropriately and high-risk ambiguity is preserved for qualified human review.

### Traceability
Assessment of whether a reviewer can understand the relationship among governing criteria, available evidence, missing information, and the generated support output.

## Evaluation philosophy

AuditIA prioritizes:

**evidence over inference · traceability over fluency · uncertainty over false certainty · human accountability over automation**

## Proprietary boundary

The public framework intentionally excludes the complete prompt architecture, operational decision logic, detailed scoring rubric, benchmark construction method, acceptance thresholds, and unpublished test cases.

Those materials form part of the project's private development layer.

## Validation boundary

This framework is exploratory. It should not be interpreted as a validated clinical evaluation standard, regulatory framework, or evidence that AuditIA is suitable for autonomous use.
