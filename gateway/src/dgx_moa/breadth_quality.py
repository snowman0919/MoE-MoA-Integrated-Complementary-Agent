#!/usr/bin/env python3
"""Frozen Scientific Reasoning and General repository-agent panel."""

from __future__ import annotations

from dgx_moa import quality_matrix as BASE

Task = BASE.Task
block = BASE.block
CODING_TASKS = BASE.TASKS

TASKS = (
    Task(
        "scientific-meta-analysis",
        "meta_analysis.py",
        block(
            """
            # Fixed and random effects meta-analysis

            Implement `summarize(effects, standard_errors)`.

            Return a dict containing `fixed_effect`, `fixed_se`, `q`,
            `tau_squared`, `random_effect`, and `random_se`. Use inverse-variance
            fixed weights and the DerSimonian-Laird nonnegative between-study
            variance. Require at least two finite numeric effects, matching
            lengths, and finite positive standard errors. Booleans are invalid.
            Use only Python's standard library.
            """
        ),
        block(
            """
            def summarize(effects, standard_errors):
                raise NotImplementedError
            """
        ),
        block(
            """
            import math
            import unittest

            from meta_analysis import summarize


            class MetaAnalysisTests(unittest.TestCase):
                def test_known_two_study_result(self):
                    result = summarize([0.2, 0.5], [0.1, 0.2])
                    self.assertAlmostEqual(result["fixed_effect"], 0.26)
                    self.assertAlmostEqual(result["fixed_se"], math.sqrt(1 / 125))
                    self.assertAlmostEqual(result["q"], 1.8)
                    self.assertAlmostEqual(result["tau_squared"], 0.02)
                    self.assertAlmostEqual(result["random_effect"], 0.3)
                    self.assertAlmostEqual(result["random_se"], math.sqrt(1 / 50))

                def test_homogeneous_effects_have_zero_tau(self):
                    result = summarize([1.0, 1.0, 1.0], [0.2, 0.3, 0.4])
                    self.assertEqual(result["tau_squared"], 0)
                    self.assertAlmostEqual(result["fixed_effect"], 1)
                    self.assertAlmostEqual(result["random_effect"], 1)

                def test_validation(self):
                    invalid = [
                        ([], []),
                        ([1], [0.1]),
                        ([1, 2], [0.1]),
                        ([1, True], [0.1, 0.2]),
                        ([1, 2], [0.1, 0]),
                        ([1, math.inf], [0.1, 0.2]),
                    ]
                    for effects, errors in invalid:
                        with self.subTest(effects=effects, errors=errors):
                            with self.assertRaises((TypeError, ValueError)):
                                summarize(effects, errors)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
    Task(
        "scientific-decay-fit",
        "decay_fit.py",
        block(
            """
            # First-order decay fit

            Implement `fit_half_life(times, observations)`.

            Fit `log(observation) = intercept - rate_constant * time` with
            ordinary least squares. Return a dict with `rate_constant`,
            `half_life`, `intercept`, and `r_squared`. Require at least three
            matching finite numeric values, strictly increasing times, positive
            observations, nonzero time variance, and a strictly decaying fitted
            slope. Booleans are invalid. Use only Python's standard library.
            """
        ),
        block(
            """
            def fit_half_life(times, observations):
                raise NotImplementedError
            """
        ),
        block(
            """
            import math
            import unittest

            from decay_fit import fit_half_life


            class DecayFitTests(unittest.TestCase):
                def test_exact_half_life(self):
                    result = fit_half_life([0, 1, 2, 3], [8, 4, 2, 1])
                    self.assertAlmostEqual(result["rate_constant"], math.log(2))
                    self.assertAlmostEqual(result["half_life"], 1)
                    self.assertAlmostEqual(result["intercept"], math.log(8))
                    self.assertAlmostEqual(result["r_squared"], 1)

                def test_scaled_time(self):
                    result = fit_half_life([0, 2, 4], [10, 5, 2.5])
                    self.assertAlmostEqual(result["half_life"], 2)

                def test_validation(self):
                    invalid = [
                        ([0, 1], [2, 1]),
                        ([0, 1, 2], [1, 2]),
                        ([0, 1, 1], [4, 2, 1]),
                        ([0, 1, 2], [1, 0.5, 0]),
                        ([0, 1, 2], [1, 2, 3]),
                        ([0, True, 2], [4, 2, 1]),
                    ]
                    for times, values in invalid:
                        with self.subTest(times=times, values=values):
                            with self.assertRaises((TypeError, ValueError)):
                                fit_half_life(times, values)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
    Task(
        "general-ranked-choice",
        "ranked_choice.py",
        block(
            """
            # Deterministic instant-runoff election

            Implement `run_election(ballots)`.

            Every ballot is a complete ranking of the same nonempty string
            candidate set with no duplicates or blank names. In each round,
            count the highest-ranked active candidate. A strict majority wins.
            Otherwise eliminate the lowest count; ties eliminate the
            lexicographically greatest tied name. Return `{"winner": name,
            "rounds": [...]}` where every round records sorted `counts` and
            either `eliminated` or `winner`. Reject malformed input and use only
            Python's standard library.
            """
        ),
        block(
            """
            def run_election(ballots):
                raise NotImplementedError
            """
        ),
        block(
            """
            import unittest

            from ranked_choice import run_election


            class RankedChoiceTests(unittest.TestCase):
                def test_transfer_selects_majority_winner(self):
                    ballots = [
                        ["Ada", "Bo", "Cy"],
                        ["Ada", "Cy", "Bo"],
                        ["Bo", "Cy", "Ada"],
                        ["Cy", "Bo", "Ada"],
                        ["Cy", "Bo", "Ada"],
                    ]
                    result = run_election(ballots)
                    self.assertEqual(result["winner"], "Cy")
                    self.assertEqual(result["rounds"][0]["eliminated"], "Bo")
                    self.assertEqual(
                        result["rounds"][0]["counts"],
                        {"Ada": 2, "Bo": 1, "Cy": 2},
                    )
                    self.assertEqual(result["rounds"][1]["winner"], "Cy")

                def test_tie_eliminates_lexicographically_greatest(self):
                    result = run_election([["A", "B"], ["B", "A"]])
                    self.assertEqual(result["rounds"][0]["eliminated"], "B")
                    self.assertEqual(result["winner"], "A")

                def test_validation(self):
                    invalid = [
                        [],
                        [["A", "A"]],
                        [["A", "B"], ["A"]],
                        [["A", "B"], ["A", "C"]],
                        [["", "B"]],
                        [["A", 2]],
                    ]
                    for ballots in invalid:
                        with self.subTest(ballots=ballots):
                            with self.assertRaises((TypeError, ValueError)):
                                run_election(ballots)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
    Task(
        "general-timezone-schedule",
        "schedule.py",
        block(
            """
            # Time-zone aware common availability

            Implement `find_slots(participants, search_start, search_end,
            duration_minutes, step_minutes=30, workday=(9, 17))`.

            `participants` maps a nonempty name to `{"timezone": IANA_name,
            "busy": [(start_iso, end_iso), ...]}`. Search and busy timestamps
            must be timezone-aware ISO strings. Return sorted UTC ISO interval
            pairs that fit every participant's local workday, do not cross a
            local date, and do not overlap any half-open busy interval.
            Candidates start at `search_start` and advance by `step_minutes`.
            Require positive integer duration/step, a valid increasing search
            interval, valid zones and busy intervals, and integer workday hours
            satisfying `0 <= start < end <= 24`. Use `zoneinfo` and only the
            Python standard library.
            """
        ),
        block(
            """
            def find_slots(
                participants,
                search_start,
                search_end,
                duration_minutes,
                step_minutes=30,
                workday=(9, 17),
            ):
                raise NotImplementedError
            """
        ),
        block(
            """
            import unittest

            from schedule import find_slots


            class ScheduleTests(unittest.TestCase):
                def test_common_window_and_half_open_busy_interval(self):
                    participants = {
                        "London": {
                            "timezone": "Europe/London",
                            "busy": [
                                (
                                    "2026-01-15T15:00:00+00:00",
                                    "2026-01-15T15:30:00+00:00",
                                )
                            ],
                        },
                        "New York": {
                            "timezone": "America/New_York",
                            "busy": [],
                        },
                    }
                    result = find_slots(
                        participants,
                        "2026-01-15T14:00:00+00:00",
                        "2026-01-15T18:00:00+00:00",
                        60,
                    )
                    self.assertEqual(
                        result,
                        [
                            (
                                "2026-01-15T14:00:00+00:00",
                                "2026-01-15T15:00:00+00:00",
                            ),
                            (
                                "2026-01-15T15:30:00+00:00",
                                "2026-01-15T16:30:00+00:00",
                            ),
                            (
                                "2026-01-15T16:00:00+00:00",
                                "2026-01-15T17:00:00+00:00",
                            ),
                        ],
                    )

                def test_search_end_is_exclusive_boundary(self):
                    result = find_slots(
                        {"UTC": {"timezone": "UTC", "busy": []}},
                        "2026-01-15T09:00:00+00:00",
                        "2026-01-15T10:00:00+00:00",
                        60,
                    )
                    self.assertEqual(
                        result,
                        [
                            (
                                "2026-01-15T09:00:00+00:00",
                                "2026-01-15T10:00:00+00:00",
                            )
                        ],
                    )

                def test_validation(self):
                    valid = {"A": {"timezone": "UTC", "busy": []}}
                    invalid = [
                        ({}, "2026-01-01T09:00:00+00:00", "2026-01-01T10:00:00+00:00", 30),
                        (valid, "2026-01-01T09:00:00", "2026-01-01T10:00:00+00:00", 30),
                        (valid, "2026-01-01T10:00:00+00:00", "2026-01-01T09:00:00+00:00", 30),
                        (valid, "2026-01-01T09:00:00+00:00", "2026-01-01T10:00:00+00:00", True),
                    ]
                    for people, start, end, duration in invalid:
                        with self.subTest(people=people, start=start):
                            with self.assertRaises((TypeError, ValueError)):
                                find_slots(people, start, end, duration)
                    with self.assertRaises((TypeError, ValueError)):
                        find_slots(
                            {"A": {"timezone": "Not/AZone", "busy": []}},
                            "2026-01-01T09:00:00+00:00",
                            "2026-01-01T10:00:00+00:00",
                            30,
                        )


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    ),
)

HIDDEN_CHECKS = {
    "scientific-meta-analysis": block(
        """
        import math
        from meta_analysis import summarize

        result = summarize([-0.1, 0.0, 0.2], [0.3, 0.2, 0.4])
        assert set(result) == {
            "fixed_effect", "fixed_se", "q", "tau_squared", "random_effect", "random_se"
        }
        assert all(math.isfinite(value) for value in result.values())
        assert result["tau_squared"] >= 0
        print("hidden checks passed")
        """
    ),
    "scientific-decay-fit": block(
        """
        import math
        from decay_fit import fit_half_life

        result = fit_half_life([1, 2, 4, 7], [12, 8, 4, 1.5])
        assert result["rate_constant"] > 0
        assert result["half_life"] == math.log(2) / result["rate_constant"]
        assert 0 <= result["r_squared"] <= 1
        print("hidden checks passed")
        """
    ),
    "general-ranked-choice": block(
        """
        from ranked_choice import run_election

        ballots = [["A", "B", "C"], ["B", "A", "C"], ["C", "A", "B"]]
        result = run_election(ballots)
        assert result["rounds"][0]["eliminated"] == "C"
        assert result["winner"] == "A"
        print("hidden checks passed")
        """
    ),
    "general-timezone-schedule": block(
        """
        from schedule import find_slots

        result = find_slots(
            {
                "A": {
                    "timezone": "UTC",
                    "busy": [("2026-05-01T10:00:00+00:00", "2026-05-01T11:00:00+00:00")],
                }
            },
            "2026-05-01T09:00:00+00:00",
            "2026-05-01T12:00:00+00:00",
            60,
            step_minutes=60,
        )
        assert result == [
            ("2026-05-01T09:00:00+00:00", "2026-05-01T10:00:00+00:00"),
            ("2026-05-01T11:00:00+00:00", "2026-05-01T12:00:00+00:00"),
        ]
        print("hidden checks passed")
        """
    ),
}

def main() -> int:
    return BASE.main(TASKS, HIDDEN_CHECKS)


if __name__ == "__main__":
    raise SystemExit(main())
