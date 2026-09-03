"""P3 SKELETON - hardware telemetry adapters.

``huphy_udp.py``  HUPHY's 100 Hz UDP JSON telemetry ({limb}/{motor}/{pos,tgt,err,vel,tau}
                  + IMU) -> canonical ``JointState``.  Conversion is deg->rad plus an
                  EXPLICIT 12-row mapping table (``joint_map_huphy.json``: limb/motor ->
                  sim name, sign, offset).  No regex, no default: a joint that is not in
                  the table is a hard failure, not a guess.  The sign must be applied to
                  velocity and torque as well (HUPHY leg.py passes those raw).
``dummy_tx.py``   sine / script / jsonl playback transmitter with latency and jitter
                  injection, so the whole receive path can be developed and tested without
                  the robot.
"""
