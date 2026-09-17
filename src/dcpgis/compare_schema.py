import sys

from dcpgis.cli import CLI, CLIArgument
from dcpgis.utils.inspect_data import compare_schema

COMPARE_SCHEMA_ARGS: list[CLIArgument] = [
    CLIArgument(
        name_or_flag="--test",
        required=True,
        help_msg="Path to the dataset being vetted.",
    ),
    CLIArgument(
        name_or_flag="--reference",
        required=True,
        help_msg="Path to the known-good schema to compare against: another dataset, "
        "or a CSV with name/type/length columns.",
    ),
    CLIArgument(
        name_or_flag="--test-layer",
        required=False,
        help_msg="Layer name within --test, if it points at a multi-layer source "
        "such as a File Geodatabase.",
    ),
    CLIArgument(
        name_or_flag="--reference-layer",
        required=False,
        help_msg="Layer name within --reference, if it is a multi-layer dataset.",
    ),
]


def main():
    cli = CLI(default_args=[])  # --env isn't meaningful for this utility
    cli.add_arguments(COMPARE_SCHEMA_ARGS)
    args = cli.parse_args()

    diff = compare_schema(
        test=args.test,
        reference=args.reference,
        test_layer=args.test_layer,
        reference_layer=args.reference_layer,
    )

    print(diff)
    sys.exit(0 if diff.is_match else 1)


if __name__ == "__main__":
    main()
