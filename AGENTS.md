# Toksec

Use standard processing only. Set `service_tier = "default"` when the backend supports that field. Never enable Fast, priority, or Ultrafast processing.

The builder implements the task in its assigned workspace. It must not edit contracts, evaluators, run records, or accepted artifacts.

Keep preparation costs separate from measured builder costs. Do not launch a paid experiment without a verified way to enforce its authorized budget.

Never describe a prompt-based spending instruction as a hard budget. Never describe a shared-filesystem native subagent as an isolated builder sandbox.

Run `python3 -m unittest discover -s tests -v` after changes to the harness.
