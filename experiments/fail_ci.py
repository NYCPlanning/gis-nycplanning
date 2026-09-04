def this_outputs_a_string() -> str:
    output = {"key": "value", "and": "another"}
    return output


def this_accepts_an_integer(a: int, b: int) -> int:
    sum = a + b
    return sum


def this_is_missing_a_return_type():
    return "this is a lot of text that i'm hoping will trigger a ruff failure. maybe? ok, no we're exceeding most of the python line length limits i'm aware of"


def main():
    this_outputs_a_string()

    print(this_accepts_an_integer(a="hello", b=2))

    this_is_missing_a_return_type()


if __name__ == "__main__":
    main()
