"""Re-export do módulo de alvo futuro (app local e testes)."""

from workloads.shared.target import (  # noqa: F401
    META_AUX_COL,
    TARGET,
    assign_forward_target,
    temporal_train_val_test_split,
)
