import logging


def run(process, product):
    def announce_self():
        logging.info(
            f"this is the {__name__} module, ready to distribute {product.upper()}"
        )

    announce_self()
