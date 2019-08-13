import logging

logger = logging.getLogger(__name__)

try:
    import torch
except ImportError:
    logger.info("You need to install pytorch to use Transfer NLP get_closest function")


def describe(x: torch.Tensor):
    print("Type: {}".format(x.type()))
    print("Shape/size: {}".format(x.shape))
    print("Values: \n{}".format(x))


if __name__ == "__main__":
    tensor = torch.rand(size=(3, 4), dtype=torch.float64)
    describe(x=tensor)
