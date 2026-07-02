CANONICAL_POLICY_OUTPUT_DEVICE_POLICIES = "sensor.ems_device_policies_pyscript"
CANONICAL_POLICY_OUTPUT_DISPATCH_COMMAND = "sensor.ems_surplus_dispatch_command_pyscript"
CANONICAL_POLICY_OUTPUT_POLICY_STATE = "sensor.ems_policy_state_pyscript"

CANONICAL_DIAGNOSTICS_POLICY = "sensor.ems_policy_diagnostics_pyscript"
CANONICAL_DIAGNOSTICS_ACTUATOR_WRITER_TRACE = "sensor.ems_actuator_writer_trace"
CANONICAL_DIAGNOSTICS_DISPATCH_STATE_APPLIER_TRACE = "sensor.ems_dispatch_state_applier_trace"

CANONICAL_POLICY_OUTPUTS = {
    "device_policies": CANONICAL_POLICY_OUTPUT_DEVICE_POLICIES,
    "dispatch_command": CANONICAL_POLICY_OUTPUT_DISPATCH_COMMAND,
    "policy_state": CANONICAL_POLICY_OUTPUT_POLICY_STATE,
}

CANONICAL_DIAGNOSTICS_OUTPUTS = {
    "policy_diagnostics": CANONICAL_DIAGNOSTICS_POLICY,
    "actuator_writer_trace": CANONICAL_DIAGNOSTICS_ACTUATOR_WRITER_TRACE,
    "dispatch_state_applier_trace": CANONICAL_DIAGNOSTICS_DISPATCH_STATE_APPLIER_TRACE,
}
