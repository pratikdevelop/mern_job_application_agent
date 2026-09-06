import argparse
from app.services.campaign import run_campaign

parser = argparse.ArgumentParser(description="AI-powered MERN job application campaign")
parser.add_argument("--send", action="store_true", help="Enable actual sending; otherwise preview only")
parser.add_argument("--limit", type=int, default=None, help="Maximum emails this run")
parser.add_argument("--min-score", type=float, default=None, help="Minimum AI match score")
args = parser.parse_args()

result = run_campaign(send=args.send, limit=args.limit, min_score=args.min_score)
print("\nCampaign summary:", result)
