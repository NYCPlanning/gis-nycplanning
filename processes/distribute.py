import logging


def run(
    args
    # process, product, destination
    ):
    def announce_self():
        logging.info(
            f"Hi! This is the {__name__} module, ready to {args.process.upper()} {args.product.upper()} to {args.destination.upper()}"
        )

    announce_self()
