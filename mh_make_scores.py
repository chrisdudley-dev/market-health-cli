import argparse, json, time
from market_health.engine import compute_scores, SECTORS_DEFAULT  # adjust import if needed

def parse_args():
    p = argparse.ArgumentParser(description="Compute market-health scores to JSON")
    p.add_argument("--out", type=str, default="scores.json")
    p.add_argument("--sectors", nargs="+", default=SECTORS_DEFAULT)
    p.add_argument("--period", type=str, default="1y")
    p.add_argument("--interval", type=str, default="1d")
    p.add_argument("--ttl", type=int, default=300, help="Min seconds between refetches per symbol")
    p.add_argument("--watch", type=int, help="Recompute and write every N seconds")
    return p.parse_args()

def _write_once(args):
    data = compute_scores(
        sectors=args.sectors,
        period=args.period,
        interval=args.interval,
        ttl_sec=args.ttl,
    )
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {args.out} with {len(data)} sectors")

def main():
    args = parse_args()
    if args.watch and args.watch > 0:
        try:
            while True:
                _write_once(args)
                time.sleep(max(1, args.watch))
        except KeyboardInterrupt:
            print("Stopped.")
    else:
        _write_once(args)

if __name__ == "__main__":
    main()
