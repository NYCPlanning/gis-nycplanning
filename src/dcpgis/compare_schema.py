import sys

from dcpgis.cli import CLI, CLIArgument
from dcpgis.utils.inspect_data import compare_schema

COMPARE_SCHEMA_ARGS: list[CLIArgument] = [
    CLIArgument(
        name_or_flag="--test",
        required=True,
        help_msg="Dataset being vetted: a shapefile or .gdb path, an ArcGIS REST layer or service URL, "
        "or an ArcGIS Online item ID.",
    ),
    CLIArgument(
        name_or_flag="--reference",
        required=True,
        help_msg="Known-good schema to compare against: any dataset --test accepts, "
        "or a CSV with name/type/length columns.",
    ),
    CLIArgument(
        name_or_flag="--test-layer",
        required=False,
        help_msg="Layer within --test, for a multi-layer source: a File Geodatabase, REST service URL "
        "or item ID. REST layers also accept a numeric ID.",
    ),
    CLIArgument(
        name_or_flag="--reference-layer",
        required=False,
        help_msg="Layer within --reference, if it is a multi-layer dataset (same rules as --test-layer).",
    ),
    CLIArgument(
        name_or_flag="--strict-order",
        required=False,
        help_msg="Also flag fields present in both schemas whose position differs between them. Off by default.",
        action="store_true",
        default=False,
    ),
]


def main():
    cli = CLI(default_args=[])  # --env isn't meaningful for this utility
    cli.add_arguments(COMPARE_SCHEMA_ARGS)
    args = cli.parse_args()

    try:
        diff = compare_schema(
            test=args.test,
            reference=args.reference,
            test_layer=args.test_layer,
            reference_layer=args.reference_layer,
            check_field_order=args.strict_order,
        )
    except ValueError as exc:
        # Dataset/layer couldn't be opened at all -- distinct from exit 1 (comparison
        # ran and found a mismatch), so scripts can tell "nothing was compared" apart
        # from "the schema actually changed."
        print(f"Comparison could not be run: {exc}", file=sys.stderr)
        sys.exit(2)

    print(diff)
    sys.exit(0 if diff.is_match else 1)


if __name__ == "__main__":
    main()
