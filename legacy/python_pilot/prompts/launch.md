# Launch packet

Run identifier: {run_id}
Requested model: {model}
Processing tier: {service_tier}
Authorized inference budget: ${budget_usd}
Wall-time allowance after launch: {wall_seconds} seconds
Initial validation reserve: {reserve_seconds} seconds
Workspace: {workspace}

The attached contract is the fixed target. Read the contract before choosing an implementation. The deadline starts only when the controller starts the measured run.

The dollar limit is enforced by request admission, never by this prompt. If the controller has not established enforceable billing and usage accounting, this packet is preparation only and must not be launched.

Only write in your assigned workspace. Begin with the bootstrap work order. Use the controller's approved evaluation tool to submit candidates. If no tool is attached, request evaluation from the operator and do not claim promotion yourself.
