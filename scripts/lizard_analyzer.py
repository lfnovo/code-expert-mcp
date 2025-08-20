import lizard
import sys
import argparse
from pathlib import Path
import csv


def calculate_llm_priority_score(total_ccn, max_ccn, function_count, total_nloc):
    return (
        (1.5 * total_ccn) + (2 * function_count) + (1.2 * max_ccn) + (0.05 * total_nloc)
    )


def analyze_repo(repo_path: str, output_csv: str = None, top_n: int = None):
    print(f"\n🔍 Analyzing repository: {repo_path}")

    result = lizard.analyze([repo_path])
    file_metrics = []

    total_files = 0
    total_functions = 0
    total_nloc = 0

    for file_info in result:
        if not file_info.function_list:
            continue

        total_files += 1
        total_functions += len(file_info.function_list)
        total_nloc += file_info.nloc

        total_ccn = sum(f.cyclomatic_complexity for f in file_info.function_list)
        max_ccn = max(f.cyclomatic_complexity for f in file_info.function_list)
        function_count = len(file_info.function_list)
        nloc = file_info.nloc

        score = calculate_llm_priority_score(total_ccn, max_ccn, function_count, nloc)

        file_metrics.append(
            {
                "file": file_info.filename,
                "score": round(score, 2),
                "total_ccn": total_ccn,
                "max_ccn": max_ccn,
                "function_count": function_count,
                "nloc": nloc,
            }
        )

    if not file_metrics:
        print("⚠️ No source files with functions found.")
        return

    file_metrics.sort(key=lambda x: x["score"], reverse=True)
    if top_n:
        file_metrics = file_metrics[:top_n]

    print("\n📊 Prioritized Files for LLM Mapping:\n")
    for r in file_metrics:
        print(
            f"{r['file']} → Score: {r['score']}, CCN: {r['total_ccn']}, Max CCN: {r['max_ccn']}, "
            f"Functions: {r['function_count']}, NLOC: {r['nloc']}"
        )

    if output_csv:
        csv_path = Path(output_csv)
        txt_path = csv_path.with_suffix(".txt")

        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=file_metrics[0].keys())
            writer.writeheader()
            writer.writerows(file_metrics)

        with txt_path.open("w") as f:
            for r in file_metrics:
                f.write(f"{r['file']}\n")

        print(f"\n✅ CSV with metrics saved to: {csv_path}")
        print(f"✅ Sorted file list saved to: {txt_path}")
    else:
        print("\n⚠️ No output file specified. Use --output FILE.csv to save results.")

    print(f"\n📦 Repository Summary:")
    print(f"  Total Files with Functions: {total_files}")
    print(f"  Total Functions: {total_functions}")
    print(f"  Total NLOC: {total_nloc}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze and prioritize a code repository using lizard"
    )
    parser.add_argument("repo_path", help="Path to the repository to analyze")
    parser.add_argument("--output", "-o", help="Path to output CSV file")
    parser.add_argument(
        "--top", "-t", type=int, help="Limit output to top N files by score"
    )
    args = parser.parse_args()

    repo_path = Path(args.repo_path)
    if not repo_path.exists():
        print(f"❌ Error: Path does not exist: {repo_path}")
        sys.exit(1)

    analyze_repo(str(repo_path), output_csv=args.output, top_n=args.top)


if __name__ == "__main__":
    main()
