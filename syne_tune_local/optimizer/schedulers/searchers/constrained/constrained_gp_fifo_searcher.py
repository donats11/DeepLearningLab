# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.
from typing import List, Optional, Dict, Any
import logging

from syne_tune_local.optimizer.schedulers.searchers.cost_aware.cost_aware_gp_fifo_searcher import (
    MultiModelGPFIFOSearcher,
)
from syne_tune_local.optimizer.schedulers.searchers.gp_searcher_factory import (
    constrained_gp_fifo_searcher_defaults,
    constrained_gp_fifo_searcher_factory,
)
from syne_tune_local.optimizer.schedulers.searchers.gp_searcher_utils import decode_state
from syne_tune_local.optimizer.schedulers.searchers.utils.default_arguments import (
    check_and_merge_defaults,
)
from syne_tune_local.optimizer.schedulers.searchers.bayesopt.datatypes.common import (
    TrialEvaluations,
    INTERNAL_CONSTRAINT_NAME,
)

logger = logging.getLogger(__name__)


class ConstrainedGPFIFOSearcher(MultiModelGPFIFOSearcher):
    """
    Gaussian process-based constrained hyperparameter optimization (to be used
    with :class:`~syne_tune_local.optimizer.schedulers.FIFOScheduler`).

    Additional arguments on top of parent class
    :class:`~syne_tune_local.optimizer.schedulers.searchers.cost_aware.cost_aware_gp_fifo_searcher.MultiModelGPFIFOSearcher`:

    :param constraint_attr: Name of constraint metric in ``report`` passed to
        :meth:`_update`.
    """

    def __init__(
        self,
        config_space: Dict[str, Any],
        metric: str,
        points_to_evaluate: Optional[List[dict]] = None,
        **kwargs,
    ):
        assert kwargs.get("constraint_attr") is not None, (
            "This searcher needs a constraint attribute. Please specify its "
            + "name in search_options['constraint_attr']"
        )
        super().__init__(
            config_space, metric, points_to_evaluate=points_to_evaluate, **kwargs
        )

    def _create_kwargs_int(self, kwargs):
        _kwargs = check_and_merge_defaults(
            kwargs,
            *constrained_gp_fifo_searcher_defaults(kwargs),
            dict_name="search_options",
        )
        kwargs_int = constrained_gp_fifo_searcher_factory(**_kwargs)
        self._copy_kwargs_to_kwargs_int(kwargs_int, kwargs)
        return kwargs_int

    def _copy_kwargs_to_kwargs_int(
        self, kwargs_int: Dict[str, Any], kwargs: Dict[str, Any]
    ):
        super()._copy_kwargs_to_kwargs_int(kwargs_int, kwargs)
        k = "constraint_attr"
        kwargs_int[k] = kwargs[k]

    def _call_create_internal(self, kwargs_int):
        self._constraint_attr = kwargs_int.pop("constraint_attr")
        super()._call_create_internal(kwargs_int)

    def _update(self, trial_id: str, config: Dict[str, Any], result: Dict[str, Any]):
        # We can call the superclass method, because
        # ``state_transformer.label_trial`` can be called two times
        # with parts of the metrics
        super()._update(trial_id, config, result)
        # Get constraint metric
        assert self._constraint_attr in result, (
            f"Constraint metric {self._constraint_attr} not included in "
            + "reported result. Make sure your evaluation function reports it."
        )
        constr_val = float(result[self._constraint_attr])
        metrics = {INTERNAL_CONSTRAINT_NAME: constr_val}
        self.state_transformer.label_trial(
            TrialEvaluations(trial_id=trial_id, metrics=metrics), config=config
        )
        if self.debug_log is not None:
            logger.info(f"constraint_val = {constr_val}")

    def clone_from_state(self, state):
        # Create clone with mutable state taken from 'state'
        init_state = decode_state(state["state"], self._hp_ranges_in_state())
        output_skip_optimization = state["skip_optimization"]
        output_estimator = self.state_transformer.estimator
        # Call internal constructor
        new_searcher = ConstrainedGPFIFOSearcher(
            **self._new_searcher_kwargs_for_clone(),
            output_estimator=output_estimator,
            init_state=init_state,
            output_skip_optimization=output_skip_optimization,
            constraint_attr=self._constraint_attr,
        )
        new_searcher._restore_from_state(state)
        # Invalidate self (must not be used afterwards)
        self.state_transformer = None
        return new_searcher
