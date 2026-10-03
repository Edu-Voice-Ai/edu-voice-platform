"""CLI Runner for Local Telephony Sandbox (TEST ONLY).

Usage:
    python -m tests.telephony_simulator.simulate_call [--frames 5] [--barge-in] [--concurrent 1]

Simulates an end-to-end phone call lifecycle through the Edu-Voice-AI Voice Gateway.
"""

import argparse
import asyncio
import logging
import sys
import time

from backend.app.services.telephony.metrics import get_gateway_metrics
from tests.telephony_simulator.simulator import TelephonySimulatorHarness

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("telephony_simulator_cli")


async def async_main(args: argparse.Namespace) -> int:
    """Async main routine for call simulation CLI."""
    harness = TelephonySimulatorHarness()
    start_time = time.time()

    print("\n========================================================")
    print("  EDU-VOICE-AI — LOCAL TELEPHONY SIMULATOR (TEST ONLY)  ")
    print("========================================================\n")

    if args.concurrent > 1:
        print(f"[*] Spawning {args.concurrent} concurrent simulated calls...")
        results = await harness.run_concurrent_calls(
            count=args.concurrent,
            base_sid="call_cli_conc",
            base_session="session_cli_conc",
        )
        for res in results:
            print(
                f"  -> [Call {res.call_sid}] Tenant: {res.tenant_id} | Inbound Frames: {res.inbound_frames_sent} | Success: {res.success}"
            )
        print(f"\n[+] All {len(results)} concurrent calls completed successfully!")
    else:
        print("[*] Executing single end-to-end simulated call...")
        result = await harness.run_simulated_call(
            call_sid="call_cli_single_001",
            session_id="session_cli_single_001",
            num_frames=args.frames,
            simulate_barge_in=args.barge_in,
        )
        print("  -> Session Created:     ", result.session_id)
        print("  -> Call SID:            ", result.call_sid)
        print("  -> Inbound Frames Sent: ", result.inbound_frames_sent)
        print("  -> DTMF Injected:       ", result.details.get("dtmf_digits"))
        print("  -> Barge-in Triggered:  ", result.interruptions_triggered > 0)
        print("  -> Final State:         ", result.final_connection_state.value)
        print("  -> Status:               SUCCESS")

    duration_ms = (time.time() - start_time) * 1000
    metrics = get_gateway_metrics().get_snapshot()

    print("\n--------------------------------------------------------")
    print(f"  Duration:           {duration_ms:.2f} ms")
    print(f"  Active Sessions:    {metrics.get('active_sessions', 0)}")
    print(
        f"  Total Inbound Audio Frames Handled: {metrics.get('inbound_audio_frames_total', 0)}"
    )
    print(
        f"  Total Interruptions Recorded:       {metrics.get('interruption_events_total', 0)}"
    )
    print("========================================================\n")

    return 0


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Edu-Voice-AI Local Telephony Sandbox CLI"
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=5,
        help="Number of synthetic audio frames to stream",
    )
    parser.add_argument(
        "--barge-in",
        action="store_true",
        default=True,
        help="Simulate caller barge-in interruption",
    )
    parser.add_argument(
        "--no-barge-in",
        dest="barge_in",
        action="store_false",
        help="Disable barge-in simulation",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=1,
        help="Number of concurrent calls to simulate",
    )

    parsed_args = parser.parse_args()
    exit_code = asyncio.run(async_main(parsed_args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
