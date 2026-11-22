#!/usr/bin/env python3
"""S DEEP automation entry point: python run.py daily|weekly|dryrun"""
import sys
import pipeline as P

MODES = {"daily": P.produce, "weekly": P.weekly, "dryrun": P.dryrun}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "daily"
    if mode not in MODES:
        raise SystemExit(f"Unknown mode: {mode}. Choose one of: {', '.join(MODES)}")
    state = P.load()
    MODES[mode](state)
    if mode == "daily":
        import analytics
        rows = analytics.table(state)
        analytics.write_report(state, rows, analytics.group_stats(rows))


if __name__ == "__main__":
    main()
